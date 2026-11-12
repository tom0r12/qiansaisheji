"""Audit every validation task using already frozen precision-study configs.

No scales, shifts, clipping thresholds, or format choices are fitted here.
The original study, all frozen configs, and both dataset splits are hash-bound.
This is a local exploratory audit, not the official 600-task evaluation.
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

import study_precision_bandwidth as study
from reference import weight_digest

PRIORITY = ["x8_w8_y8_h0", "x8_w8_y12_h0", "x10_w10_y12_h0"]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def summarize(rows: list[dict]) -> dict:
    errors = np.array([row["nrmse_percent"] for row in rows], dtype=np.float64)
    worst = max(rows, key=lambda row: row["nrmse_percent"])
    return {
        "tasks": len(rows),
        "output_elements": sum(row["elements"] for row in rows),
        "max_nrmse_percent": float(errors.max()),
        "p95_nrmse_percent": float(np.percentile(errors, 95, method="linear")),
        "median_nrmse_percent": float(np.median(errors)),
        "mean_task_nrmse_percent": float(errors.mean()),
        "tasks_above_3_percent": int(np.count_nonzero(errors > 3.0)),
        "tasks_above_1_percent": int(np.count_nonzero(errors > 1.0)),
        "tasks_above_0_3_percent": int(np.count_nonzero(errors > 0.3)),
        "output_saturation": sum(row["output_saturation"] for row in rows),
        "tasks_with_output_saturation": sum(row["output_saturation"] > 0 for row in rows),
        "input_clipping": sum(row["input_clipping"] for row in rows),
        "tasks_with_input_clipping": sum(row["input_clipping"] > 0 for row in rows),
        "worst_task": worst,
        "meets_all_local_task_3_percent": bool(np.all(errors <= 3.0)),
    }


def task_metrics(accumulation, data, config, input_clips) -> list[dict]:
    """Reduce errors within each complete 99x256 task, never across samples."""
    count = data["X"].shape[0]
    squared_error = np.zeros(count, dtype=np.float64)
    squared_reference = np.zeros(count, dtype=np.float64)
    saturation = np.zeros(count, dtype=np.int64)
    bits = config["output_bits"]
    lower, upper = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    for j, shift in enumerate(config["shifts"]):
        raw = study.rounded(accumulation[..., j], shift)
        saturation += np.count_nonzero((raw < lower) | (raw > upper), axis=1)
        integer = np.clip(raw, lower, upper)
        scale = math.ldexp(1.0, config["x_exponent"] + config["w_exponents"][j] + shift)
        expected = data["Y"][..., j].astype(np.float64)
        squared_error += np.sum((integer.astype(np.float64) * scale - expected) ** 2, axis=1)
        squared_reference += np.sum(expected ** 2, axis=1)
    elements = 99 * 256
    values = np.sqrt(squared_error / elements) / np.maximum(np.sqrt(squared_reference / elements), 1e-8) * 100
    check(bool(np.all(np.isfinite(values))), "Nonfinite task error")
    return [{
        "layer": int(config["layer"]), "sample_index": i,
        "sample_id": str(data["sample_ids"][i]), "label": int(data["labels"][i]),
        "elements": elements, "nrmse_percent": float(values[i]),
        "error_squared_sum": float(squared_error[i]),
        "reference_squared_sum": float(squared_reference[i]),
        "output_saturation": int(saturation[i]), "input_clipping": int(input_clips[i]),
    } for i in range(count)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-run", type=Path, required=True)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policies", nargs="+", help="Default: all original policies, priority formats first")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    original_path = args.study / "result.json"
    original = json.loads(original_path.read_text(encoding="utf-8"))
    frozen_path = args.study / "frozen_config_sha256.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    check(original["completed"] and not original["validation_parameter_fit"], "Study not completed/training-frozen")
    study_source = Path(study.__file__)
    study_hash = sha(study_source)
    study_lf_hash = hashlib.sha256(study_source.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    check(original["script_sha256"] in (study_hash, study_lf_hash), "Original study implementation changed beyond CRLF conversion")
    check(len(frozen) == len(original["policies"]) * 12, "Frozen config count mismatch")
    for relative, digest in frozen.items():
        check(sha(args.study / relative) == digest, "Frozen config mismatch: " + relative)
    policies = args.policies or PRIORITY + [p for p in original["policies"] if p not in PRIORITY]
    check(len(set(policies)) == len(policies) and set(policies) <= set(original["policies"]), "Unknown/duplicate policy")
    identities = {role: set(original[role + "_sample_ids"]) for role in ("training", "validation")}
    check(not identities["training"] & identities["validation"], "Original sample sets overlap")
    expected_inputs = {(row["role"], row["layer"]): row["sha256"] for row in original["inputs"]}
    check(len(expected_inputs) == 24, "Original study input manifest incomplete")
    report = {
        "schema": "qingyu-precision-per-task-audit-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "command": sys.argv, "script_sha256": sha(Path(__file__)),
        "study_result": {"path": str(original_path.resolve()), "sha256": sha(original_path)},
        "frozen_config_manifest_sha256": sha(frozen_path), "frozen_configs_sha256": frozen,
        "study_source_identity": {"original_sha256": original["script_sha256"], "current_byte_sha256": study_hash,
                                  "current_lf_sha256": study_lf_hash,
                                  "match": "byte_exact" if study_hash == original["script_sha256"] else "CRLF_to_LF_only"},
        "dependency_sha256": {Path(study.__file__).name: sha(Path(study.__file__)),
                              "reference.py": sha(Path(__file__).with_name("reference.py"))},
        "runtime": {"python": sys.version, "numpy": np.__version__,
                    "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS")},
        "source_commit": original["source_commit"], "training_samples": original["training_samples"],
        "validation_samples": original["validation_samples"],
        "training_sample_ids": sorted(identities["training"]), "validation_sample_ids": sorted(identities["validation"]),
        "sample_sets_disjoint": True, "validation_parameter_fit": False,
        "official_600_sample_evaluation": False, "task_shape": [99, 64, 256],
        "nrmse_formula": "100*sqrt(mean((dequantized_output-reference)^2))/max(sqrt(mean(reference^2)),1e-8)",
        "percentile_method": "numpy.percentile method=linear over complete layer/sample task errors",
        "input_weight_quantizer": "RNE, symmetric signed range [-((1<<(bits-1))-1),+((1<<(bits-1))-1)]",
        "output_quantizer": "RNE right shift, signed two's-complement saturating range",
        "limits": ["Local validation: 256 independent utterances reused across 12 layer tasks; not 3072 independent utterances",
                   "Format comparisons are exploratory; choosing a format here does not turn this set into a new official holdout",
                   "No RTL, loader, PPA, classification accuracy, or official task-throughput result inferred"],
        "inputs": [], "policies": {name: {"layers": [], "tasks": []} for name in policies},
    }
    write_json(out / "audit_plan.json", {k: v for k, v in report.items() if k != "policies"} | {"policies": policies})
    for layer in range(12):
        train = None
        for role in ("training", "validation"):
            path = args.reference_run / ("float_" + role) / f"layer{layer:02d}.npz"
            digest = sha(path)
            check(digest == expected_inputs[role, layer], f"Dataset changed: {role} layer {layer}")
            data = study.load(path, role)
            ids = list(map(str, data["sample_ids"].tolist()))
            check(len(set(ids)) == len(ids) and set(ids) == identities[role], "Sample identity changed")
            check(len(ids) == original[role + "_samples"], "Sample count changed")
            check(int(data["layer"].item()) == layer, "Layer identity mismatch")
            check(str(data["source_commit"].item()) == original["source_commit"], "Model commit changed")
            check(data["Y"].shape == (len(ids), 99, 256), "Incomplete reference task")
            report["inputs"].append({"role": role, "layer": layer, "path": str(path.resolve()), "sha256": digest})
            if role == "training":
                train = weight_digest(data["W"], data["b"])
        weights = weight_digest(data["W"], data["b"])
        check(weights == train, "Validation/training weights differ")
        cache = {}
        for name in policies:
            config = json.loads((args.study / name / f"layer{layer:02d}.json").read_text(encoding="utf-8"))
            check(config["fit_role"] == "training" and config["weights_sha256"] == weights, "Unfrozen/wrong weights")
            check(config["layer"] == layer, "Config layer mismatch")
            declared = original["policies"][name]
            for key in ("input_bits", "weight_bits", "output_bits", "headroom_bits"):
                check(config[key] == declared[key], "Format identity mismatch")
            key = (config["input_bits"], config["weight_bits"], config["x_exponent"], tuple(config["w_exponents"]))
            if key not in cache:
                accumulation, clips, bound = study.encode(data, config)
                limit = (1 << (config["input_bits"] - 1)) - 1
                rounded_x = np.rint(data["X"].astype(np.float64) / math.ldexp(1.0, config["x_exponent"]))
                per_input_clips = np.count_nonzero(np.abs(rounded_x) > limit, axis=(1, 2))
                check(int(per_input_clips.sum()) == clips, "Input clipping reduction mismatch")
                _, weight_clips = study.quantize(data["W"], np.exp2(config["w_exponents"]), config["weight_bits"])
                cache[key] = accumulation, per_input_clips, bound, weight_clips
            accumulation, per_input_clips, bound, weight_clips = cache[key]
            rows = task_metrics(accumulation, data, config, per_input_clips)
            aggregate = study.evaluate(accumulation, data["Y"], config)
            expected = next(row for row in declared["validation"] if row["layer"] == layer)
            for field in ("nrmse_percent", "error_squared_sum", "reference_squared_sum"):
                check(math.isclose(aggregate[field], expected[field], rel_tol=1e-11, abs_tol=1e-12), "Original aggregate mismatch: " + field)
            for field in ("error_squared_sum", "reference_squared_sum"):
                check(math.isclose(sum(row[field] for row in rows), aggregate[field], rel_tol=1e-11, abs_tol=1e-12), "Task reduction mismatch: " + field)
            check(sum(row["output_saturation"] for row in rows) == expected["output_saturation"], "Output saturation mismatch")
            check(int(per_input_clips.sum()) == expected["input_clipping"] and bound == expected["accumulator_bound"], "Original bounds/clips mismatch")
            layer_report = summarize(rows) | {"layer": layer, "aggregate_nrmse_percent": aggregate["nrmse_percent"],
                                             "weight_clipping": weight_clips, "accumulator_bound": bound,
                                             "original_aggregate_reproduced": True}
            report["policies"][name]["layers"].append(layer_report)
            report["policies"][name]["tasks"].extend(rows)
        write_json(out / "partial_result.json", report)
        print(f"Audited layer {layer:02d}: {len(ids)} validation tasks x {len(policies)} frozen policies", flush=True)
    for name, policy in report["policies"].items():
        policy["summary"] = summarize(policy["tasks"])
        policy["summary"]["weight_clipping_across_12_weight_sets"] = sum(row["weight_clipping"] for row in policy["layers"])
        policy["labels"] = {str(label): summarize([row for row in policy["tasks"] if row["label"] == label]) for label in range(12)}
        policy["format"] = {key: original["policies"][name][key] for key in ("input_bits", "weight_bits", "output_bits", "headroom_bits", "ideal_packed_words")}
        csv_path = out / (name + "_tasks.csv")
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(policy["tasks"][0]))
            writer.writeheader()
            writer.writerows(policy["tasks"])
        policy["tasks_csv_sha256"] = sha(csv_path)
        print(name, json.dumps(policy["summary"]), flush=True)
    for relative, digest in frozen.items():
        check(sha(args.study / relative) == digest, "Frozen config modified during audit")
    check(sha(original_path) == report["study_result"]["sha256"], "Original result modified during audit")
    report["completed"] = True
    report["completed_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(out / "result.json", report)
    write_json(out / "summary.json", {"policies": {name: policy["summary"] for name, policy in report["policies"].items()},
                                      "result_sha256": sha(out / "result.json"), "completed": True})


if __name__ == "__main__":
    main()
