"""Predeclared training-only centered fixed-point formats; local task audit.

X feature centers are absorbed into the bias. Y integer zero points are also
folded into the integer bias, so hardware still performs one linear MAC layer,
RNE shift and saturation. Decoding is only (residual + zero_point) * scale.
No validation fitting, model retraining, RTL change or PPA claim is performed.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys

import numpy as np

import study_precision_bandwidth as basic
from check_precision_tasks import check, sha, summarize, write_json
from reference import weight_digest, round_shift_rne

# Declared before any dataset read; no later validation-directed expansion.
POLICIES = [(8, 8, 7), (8, 8, 6), (7, 8, 7), (8, 7, 7), (7, 7, 7), (7, 7, 6)]
REASONS = ["INT8 operands, compact 7-bit output quality baseline",
           "Isolate 6-bit output effect while retaining INT8 operands",
           "Isolate one-bit input reduction",
           "Isolate one-bit weight reduction (weights dominate input payload)",
           "Balanced 7-bit operand/output representation",
           "Combine balanced operands with 6-bit output"]


def name(policy):
    return "x%d_w%d_y%d_center" % policy


def signed_width(low: int, high: int) -> int:
    return max(1, max(0, int(high)).bit_length() + 1,
               max(0, -int(low) - 1).bit_length() + 1)


def extrema(value) -> dict:
    low, high = int(np.min(value)), int(np.max(value))
    return {"min": low, "max": high, "required_signed_bits": signed_width(low, high)}


def quantized_operands(data, config):
    center = np.asarray(config["x_centers"], dtype=np.float64)
    sx = math.ldexp(1.0, config["x_exponent"])
    sw = np.exp2(np.asarray(config["w_exponents"], dtype=np.float64))
    x, x_clips = basic.quantize(data["X"].astype(np.float64) - center, sx, config["input_bits"])
    w, w_clips = basic.quantize(data["W"], sw, config["weight_bits"])
    # This is a frozen model parameter, computed only from training weights and
    # centers during fitting; validation must use exactly these stored integers.
    b = np.asarray(config["base_bias_integer"], dtype=np.int64)
    a, bound = basic.exact_accumulation(x, w, b, config["input_bits"])
    qmax = (1 << (config["input_bits"] - 1)) - 1
    raw_x = np.rint((data["X"].astype(np.float64) - center) / sx)
    clips = np.count_nonzero(np.abs(raw_x) > qmax, axis=(1, 2))
    check(int(clips.sum()) == x_clips, "Input clipping count mismatch")
    return a, clips, {"input": extrema(x), "weight": extrema(w), "base_bias": extrema(b),
                      "base_accumulator_bound": bound, "weight_clipping": w_clips}


def centered_output_parameters(a, bits):
    """Smallest shift covering TRAINING extrema with an integer output origin.

    Bias folding happens before RNE. Bounds are checked with that exact order,
    including ties whose parity changes under an odd integer zero point.
    """
    matrix = a.reshape(-1, 256)
    lows, highs = np.min(matrix, axis=0), np.max(matrix, axis=0)
    lower, upper = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    shifts, points = [], []
    for lo, hi in zip(lows, highs):
        for shift in range(48):
            midpoint = (int(lo) + int(hi)) // (2 << shift)
            # Fixed tie-break order, independent of validation observations.
            candidates = [midpoint + 1, midpoint, midpoint + 2, midpoint - 1]
            found = False
            for point in candidates:
                residual = np.array([int(lo) - (point << shift), int(hi) - (point << shift)], dtype=np.int64)
                rounded = basic.rounded(residual, shift)
                if bool(np.all((rounded >= lower) & (rounded <= upper))):
                    shifts.append(shift)
                    points.append(point)
                    found = True
                    break
            if found:
                break
        else:
            raise OverflowError("Centered output cannot fit supported shift")
    return shifts, points


def fit_base(data, input_bits, weight_bits):
    flat = data["X"].astype(np.float64).reshape(-1, 64)
    centers = (flat.min(axis=0) + flat.max(axis=0)) / 2
    sx_exp = basic.exponent(np.max(np.abs(flat - centers)), input_bits)
    w_exp = [basic.exponent(value, weight_bits) for value in np.max(np.abs(data["W"]), axis=0)]
    sx = math.ldexp(1.0, sx_exp)
    sw = np.exp2(w_exp)
    adjusted_bias = data["b"].astype(np.float64) + centers @ data["W"].astype(np.float64)
    bias = np.rint(adjusted_bias / (sx * sw))
    check(bool(np.all(np.abs(bias) < (1 << 47))), "Centered bias exceeds signed48")
    return {"input_bits": input_bits, "weight_bits": weight_bits,
            "x_center_policy": "per-feature training min/max midpoint, float64",
            "x_centers": centers.tolist(), "x_exponent": sx_exp, "w_exponents": w_exp,
            "base_bias_integer": bias.astype(np.int64).tolist(),
            "weights_sha256": weight_digest(data["W"], data["b"]), "fit_role": "training"}


def metrics(a, data, config, input_clips, operand_stats):
    n = len(data["sample_ids"])
    error, reference = np.zeros(n), np.zeros(n)
    saturation = np.zeros(n, dtype=np.int64)
    bits = config["output_bits"]
    lower, upper = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    output_low, output_high, raw_low, raw_high = 0, 0, 0, 0
    restored_low, restored_high = 0, 0
    output_hash = hashlib.sha256()
    reconstructed_hash = hashlib.sha256()
    for j, (shift, point) in enumerate(zip(config["shifts"], config["output_zero_points"])):
        folded = a[..., j] - (int(point) << int(shift))
        integer = basic.rounded(folded, shift)
        saturation += np.count_nonzero((integer < lower) | (integer > upper), axis=1)
        raw_low, raw_high = min(raw_low, int(integer.min())), max(raw_high, int(integer.max()))
        q = np.clip(integer, lower, upper)
        output_low, output_high = min(output_low, int(q.min())), max(output_high, int(q.max()))
        restored = q + point
        restored_low, restored_high = min(restored_low, int(restored.min())), max(restored_high, int(restored.max()))
        scale = math.ldexp(1.0, config["output_exponents"][j])
        decoded = restored.astype(np.float64) * scale
        expected = data["Y"][..., j].astype(np.float64)
        error += np.sum((decoded - expected) ** 2, axis=1)
        reference += np.sum(expected ** 2, axis=1)
        # Defined channel-major order; each channel has sample-major rows.
        output_hash.update(q.astype("<i8").tobytes(order="C"))
        reconstructed_hash.update(decoded.astype("<f8").tobytes(order="C"))
    nrmses = np.sqrt(error / 25344) / np.maximum(np.sqrt(reference / 25344), 1e-8) * 100
    check(bool(np.all(np.isfinite(nrmses))), "Nonfinite task error")
    rows = [{"layer": config["layer"], "sample_index": i, "sample_id": str(data["sample_ids"][i]),
             "label": int(data["labels"][i]), "elements": 25344, "nrmse_percent": float(nrmses[i]),
             "error_squared_sum": float(error[i]), "reference_squared_sum": float(reference[i]),
             "output_saturation": int(saturation[i]), "input_clipping": int(input_clips[i])} for i in range(n)]
    stats = dict(operand_stats)
    stats.update(output={"min": output_low, "max": output_high, "required_signed_bits": signed_width(output_low, output_high)},
                 pre_saturation_output={"min": raw_low, "max": raw_high, "required_signed_bits": signed_width(raw_low, raw_high)},
                 restored_output_integer={"min": restored_low, "max": restored_high,
                                          "required_signed_bits": signed_width(restored_low, restored_high)},
                 folded_bias=extrema(config["folded_bias_integer"]),
                 zero_points=extrema(config["output_zero_points"]), output_exponents=extrema(config["output_exponents"]),
                 folded_accumulator_bound=config["folded_accumulator_bound"],
                 encoded_int64_channel_major_sha256=output_hash.hexdigest(),
                 decoded_float64_channel_major_sha256=reconstructed_hash.hexdigest())
    return rows, stats


def verify_integer_path(a, data, config):
    """Independent scalar hardware path: folded bias and every signed48 MAC."""
    sx = math.ldexp(1.0, config["x_exponent"])
    x, _ = basic.quantize(data["X"].astype(np.float64) - np.asarray(config["x_centers"]), sx, config["input_bits"])
    w, _ = basic.quantize(data["W"], np.exp2(config["w_exponents"]), config["weight_bits"])
    generator = np.random.default_rng(481506)
    for _ in range(16):
        sample = int(generator.integers(len(x)))
        row = int(generator.integers(99))
        channel = int(generator.integers(256))
        accumulator = int(config["folded_bias_integer"][channel])
        for k in range(64):
            accumulator += int(x[sample, row, k]) * int(w[k, channel])
            check(-(1 << 47) <= accumulator < (1 << 47), "Scalar partial signed48 overflow")
        shift = config["shifts"][channel]
        point = config["output_zero_points"][channel]
        expected = int(a[sample, row, channel]) - (point << shift)
        check(accumulator == expected, "Folded-bias hardware path mismatch")
        check(round_shift_rne(accumulator, shift) == int(basic.rounded(np.array([expected]), shift)[0]), "Scalar RNE mismatch")


def metadata(policy):
    xb, wb, yb = policy
    payload = {"X_words": math.ceil(99 * 64 * xb / 32), "W_words": math.ceil(64 * 256 * wb / 32),
               "output_words": math.ceil(99 * 256 * yb / 32)}
    fields = {"accelerator_bias48_aligned64": 256 * 8, "accelerator_shift8": 256,
              "decoder_zero_point_signed32": 256 * 4, "decoder_output_exponent_signed16": 256 * 2,
              "input_encoder_center_float64": 64 * 8, "input_encoder_exponent_signed16": 2,
              "weight_encoder_exponents_signed16": 256 * 2}
    hardware_words = (fields["accelerator_bias48_aligned64"] + fields["accelerator_shift8"]) // 4
    complete_words = sum(math.ceil(value / 4) for value in fields.values())
    return {"ideal_packed_payload": payload, "metadata_bytes_by_field": fields,
            "accelerator_metadata_words_legacy_layout": hardware_words,
            "all_metadata_words_each_field_word_aligned": complete_words,
            "initial_plus_output_words_including_all_metadata": sum(payload.values()) + complete_words,
            "initial_private_read_output_words_including_all_metadata_twice": 2 * (payload["X_words"] + payload["W_words"] + complete_words) + payload["output_words"],
            "limits": ["No runtime loader/bit unpack RTL exists for these formats",
                       "All encoder/decoder metadata counted conservatively even if some is host-side",
                       "Output restoration performs only add and power-of-two scale, never a dot product",
                       "No free cache reuse between tasks assumed in word totals"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-run", type=Path, required=True)
    parser.add_argument("--identity-study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    identity_path = args.identity_study / "result.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    input_hashes = {(row["role"], row["layer"]): row["sha256"] for row in identity["inputs"]}
    sets = {role: set(identity[role + "_sample_ids"]) for role in ("training", "validation")}
    check(not sets["training"] & sets["validation"], "Training/validation identity overlap")
    report = {"schema": "qingyu-centered-precision-study-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
              "script_sha256": sha(Path(__file__)), "command": sys.argv,
              "identity_study_sha256": sha(identity_path), "source_commit": identity["source_commit"],
              "dependency_sha256": {"study_precision_bandwidth.py": sha(Path(basic.__file__)),
                                    "check_precision_tasks.py": sha(Path(__file__).with_name("check_precision_tasks.py")),
                                    "reference.py": sha(Path(__file__).with_name("reference.py"))},
              "runtime": {"python": sys.version, "numpy": np.__version__, "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS")},
              "validation_parameter_fit": False, "official_600_sample_evaluation": False,
              "selection_scope": "Predeclared exploratory format comparison; validation is not a fresh final-selection holdout",
              "training_sample_ids": sorted(sets["training"]), "validation_sample_ids": sorted(sets["validation"]),
              "sample_sets_disjoint": True, "task_shape": [99, 64, 256],
              "numerical_contract": {"input": "RNE((X-center_feature)/2**x_exp), symmetric signed saturation",
                                     "weight": "RNE(W/2**w_exp_channel), symmetric signed saturation",
                                     "base_bias": "RNE((b+center_feature dot W)/(2**(x_exp+w_exp_channel)))",
                                     "folded_bias": "base_bias_integer - (output_zero_point << shift)",
                                     "hardware": "signed48 MAC(input_integer,weight_integer,folded_bias); RNE shift; saturate residual",
                                     "decode": "(residual+output_zero_point)*2**output_exponent_channel",
                                     "decoder_matrix_computation": False},
              "open_requirements": ["Custom centered format integration with official loader/scoring must be validated",
                                    "No production RTL, timing, area or energy measurement",
                                    "256 utterances across 12 layers are 3072 tasks, not 3072 independent utterances"],
              "inputs": [], "policies": {name(p): {"reason": reason, "input_bits": p[0], "weight_bits": p[1], "output_bits": p[2],
                                                    "transport": metadata(p), "training": [], "validation": [], "tasks": []}
                                          for p, reason in zip(POLICIES, REASONS)}}
    write_json(out / "declared_policies.json", report)

    def load_layer(role, layer):
        path = args.reference_run / ("float_" + role) / f"layer{layer:02d}.npz"
        digest = sha(path)
        check(digest == input_hashes[role, layer], "Changed dataset " + str(path))
        data = basic.load(path, role)
        ids = list(map(str, data["sample_ids"]))
        check(len(set(ids)) == len(ids) and set(ids) == sets[role], "Sample identity changed")
        check(int(data["layer"].item()) == layer and str(data["source_commit"].item()) == identity["source_commit"], "Model/layer identity changed")
        report["inputs"].append({"role": role, "layer": layer, "path": str(path.resolve()), "sha256": digest})
        return data

    # Freeze ALL twelve layers and ALL policies before any validation array read.
    for layer in range(12):
        data = load_layer("training", layer)
        cache = {}
        for policy in POLICIES:
            xb, wb, yb = policy
            if (xb, wb) not in cache:
                base = fit_base(data, xb, wb)
                a, clips, stats = quantized_operands(data, base)
                cache[xb, wb] = base, a, clips, stats
            base, a, clips, stats = cache[xb, wb]
            config = dict(base) | {"layer": layer, "output_bits": yb}
            shifts, points = centered_output_parameters(a, yb)
            config.update(shifts=shifts, output_zero_points=points,
                          output_exponents=[base["x_exponent"] + we + shift for we, shift in zip(base["w_exponents"], shifts)],
                          folded_bias_integer=[b - (p << s) for b, p, s in zip(base["base_bias_integer"], points, shifts)])
            check(max(abs(v) for v in config["folded_bias_integer"]) < (1 << 47), "Folded bias overflows")
            check(all(-(1 << 31) <= value < (1 << 31) for value in points), "Zero point exceeds declared signed32 metadata")
            check(all(-(1 << 15) <= value < (1 << 15) for value in config["output_exponents"] + base["w_exponents"] + [base["x_exponent"]]), "Exponent exceeds metadata")
            sw = np.exp2(base["w_exponents"])
            w, _ = basic.quantize(data["W"], sw, wb)
            bound = np.abs(np.asarray(config["folded_bias_integer"], dtype=np.int64)) + ((1 << (xb - 1)) - 1) * np.sum(np.abs(w), axis=0)
            check(bool(np.all(bound < (1 << 47))), "Folded partial accumulator bound exceeded")
            config["folded_accumulator_bound"] = int(bound.max())
            verify_integer_path(a, data, config)
            directory = out / name(policy)
            directory.mkdir(exist_ok=True)
            write_json(directory / f"layer{layer:02d}.json", config)
            rows, value_stats = metrics(a, data, config, clips, stats)
            summary = summarize(rows)
            check(summary["output_saturation"] == 0, "Training output range calibration failed")
            report["policies"][name(policy)]["training"].append(summary | {"layer": layer, "value_statistics": value_stats})
        print("Frozen centered training layer", layer, flush=True)
    frozen = {p.relative_to(out).as_posix(): sha(p) for p in out.glob("*/layer*.json")}
    write_json(out / "frozen_config_sha256.json", frozen)
    report["all_configs_frozen_before_validation_utc"] = datetime.now(timezone.utc).isoformat()
    report["frozen_config_manifest_sha256"] = sha(out / "frozen_config_sha256.json")
    for layer in range(12):
        data = load_layer("validation", layer)
        cache = {}
        for policy in POLICIES:
            config = json.loads((out / name(policy) / f"layer{layer:02d}.json").read_text(encoding="utf-8"))
            check(config["weights_sha256"] == weight_digest(data["W"], data["b"]), "Validation weights/bias changed")
            key = policy[:2]
            if key not in cache:
                cache[key] = quantized_operands(data, config)
            a, clips, stats = cache[key]
            verify_integer_path(a, data, config)
            rows, value_stats = metrics(a, data, config, clips, stats)
            report["policies"][name(policy)]["validation"].append(summarize(rows) | {"layer": layer, "value_statistics": value_stats})
            report["policies"][name(policy)]["tasks"].extend(rows)
        write_json(out / "partial_result.json", report)
        print("Audited centered validation layer", layer, flush=True)
    check(frozen == {p.relative_to(out).as_posix(): sha(p) for p in out.glob("*/layer*.json")}, "Frozen configs changed")
    for policy in report["policies"].values():
        policy["summary"] = summarize(policy["tasks"])
        policy["summary"]["weight_clipping_across_12_weight_sets"] = sum(layer["value_statistics"]["weight_clipping"] for layer in policy["validation"])
    for policy_name, policy in report["policies"].items():
        path = out / (policy_name + "_tasks.csv")
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(policy["tasks"][0]))
            writer.writeheader()
            writer.writerows(policy["tasks"])
        policy["tasks_csv_sha256"] = sha(path)
        print(policy_name, json.dumps(policy["summary"]), flush=True)
    report["completed"] = True
    report["completed_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(out / "result.json", report)
    write_json(out / "summary.json", {"completed": True, "result_sha256": sha(out / "result.json"),
                                      "policies": {key: value["summary"] for key, value in report["policies"].items()}})


if __name__ == "__main__":
    main()
