"""Export frozen INT8 tiles and direct64-product integer golden results.

No fitting or Winograd formula is used by the golden model. The default
validation sample9 is declared before data access and includes the original
INT8 study's worst local task; every one of12 layers and16 tiles is exported.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "model"))
from reference import accumulate, round_shift_rne, weight_digest
from study_precision_bandwidth import quantize


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_hex(path, words):
    path.write_text("".join(f"{int(word) & 0xffffffff:08x}\n" for word in words))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-run", type=Path, default=ROOT / "build/model_reference_20261111_201956_613")
    parser.add_argument("--study", type=Path, default=ROOT / "build/precision_bandwidth_20261111")
    parser.add_argument("--sample-index", type=int, default=9)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    identity_path = args.study / "result.json"
    identity = json.loads(identity_path.read_text())
    frozen = json.loads((args.study / "frozen_config_sha256.json").read_text())
    if set(identity["training_sample_ids"]) & set(identity["validation_sample_ids"]):
        raise ValueError("Training/validation identities overlap")
    report = {"schema": "qingyu-winograd-array8-vectors-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
              "script_sha256": sha(Path(__file__)), "identity_study_sha256": sha(identity_path),
              "reference_model_sha256": sha(ROOT / "model/reference.py"),
              "frozen_configuration": "x8_w8_y8_h0", "validation_sample_index": args.sample_index,
              "validation_parameter_fit": False, "official_evaluation": False,
              "golden": "reference.accumulate direct64 sequential integer MAC, scalar round_shift_rne, signed8 saturation",
              "input_words_per_tile": 1868, "output_words_per_tile": 396, "accumulators_per_tile": 1584,
              "cases": [], "inputs": []}
    (out / "export_plan.json").write_text(json.dumps(report, indent=2) + "\n")

    def export(x, w, bias, shifts, description):
        x, w, bias, shifts = [np.asarray(value, dtype=np.int64) for value in (x, w, bias, shifts)]
        if x.shape != (99,64) or w.shape != (64,16) or bias.shape != (16,) or shifts.shape != (16,):
            raise ValueError("Wrong tile dimensions")
        if np.any((x < -128) | (x > 127)) or np.any((w < -128) | (w > 127)):
            raise ValueError("Not signed8")
        if np.any((bias < -32768) | (bias > 32767)) or np.any((shifts < 0) | (shifts > 47)):
            raise ValueError("Unsupported metadata")
        a = accumulate(x, w, bias)
        if np.any((a < -(1<<23)) | (a >= (1<<23))):
            raise ValueError("Accumulator exceeds prototype width")
        y = np.empty((99,16), dtype=np.int64)
        for r in range(99):
            for c in range(16):
                y[r,c] = max(-128, min(127, round_shift_rne(int(a[r,c]), int(shifts[c]))))
        words = []
        for rp in range(50):
            for kp in range(32):
                values = [x[2*rp,2*kp], x[2*rp,2*kp+1],
                          x[2*rp+1,2*kp] if 2*rp+1 < 99 else 0,
                          x[2*rp+1,2*kp+1] if 2*rp+1 < 99 else 0]
                words.append(sum((int(v)&255) << (8*i) for i,v in enumerate(values)))
        for kp in range(32):
            for cp in range(8):
                values = [w[2*kp,2*cp], w[2*kp+1,2*cp], w[2*kp,2*cp+1], w[2*kp+1,2*cp+1]]
                words.append(sum((int(v)&255) << (8*i) for i,v in enumerate(values)))
        words.extend((int(bias[2*i]) & 65535) | ((int(bias[2*i+1]) & 65535) << 16) for i in range(8))
        words.extend(sum(int(shifts[4*i+j]) << (8*j) for j in range(4)) for i in range(4))
        output = [sum((int(y[r,4*p+j]) & 255) << (8*j) for j in range(4)) for r in range(99) for p in range(4)]
        if len(words) != 1868 or len(output) != 396:
            raise AssertionError("Packing length mismatch")
        index = len(report["cases"])
        files = {"input": f"case{index:04d}_input.hex", "output": f"case{index:04d}_output.hex", "accumulator": f"case{index:04d}_acc.hex"}
        write_hex(out / files["input"], words)
        write_hex(out / files["output"], output)
        write_hex(out / files["accumulator"], a.reshape(-1))
        report["cases"].append({"index": index, **description, "files": files,
                                "sha256": {key: sha(out / value) for key,value in files.items()},
                                "integer_input_sha256": hashlib.sha256(x.astype("i1").tobytes()).hexdigest(),
                                "integer_weight_sha256": hashlib.sha256(w.astype("i1").tobytes()).hexdigest(),
                                "integer_bias_sha256": hashlib.sha256(bias.astype("<i2").tobytes()).hexdigest(),
                                "shift_sha256": hashlib.sha256(shifts.astype("u1").tobytes()).hexdigest(),
                                "accumulator_min": int(a.min()), "accumulator_max": int(a.max())})

    for layer in range(12):
        relative = f"x8_w8_y8_h0/layer{layer:02d}.json"
        config_path = args.study / relative
        if sha(config_path) != frozen[relative]:
            raise ValueError("Frozen config changed")
        config = json.loads(config_path.read_text())
        path = args.reference_run / "float_validation" / f"layer{layer:02d}.npz"
        expected_sha = next(row["sha256"] for row in identity["inputs"] if row["role"] == "validation" and row["layer"] == layer)
        if sha(path) != expected_sha:
            raise ValueError("Validation dataset changed")
        with np.load(path, allow_pickle=False) as archive:
            if str(archive["split"].item()) != "validation" or str(archive["source_commit"].item()) != identity["source_commit"]:
                raise ValueError("Wrong data provenance")
            sample_id = str(archive["sample_ids"][args.sample_index])
            if sample_id not in identity["validation_sample_ids"]:
                raise ValueError("Sample identity changed")
            wf, bf = archive["W"], archive["b"]
            if weight_digest(wf,bf) != config["weights_sha256"]:
                raise ValueError("Weight identity changed")
            sx = math.ldexp(1.0, config["x_exponent"])
            sw = np.exp2(config["w_exponents"])
            x, x_clips = quantize(archive["X"][args.sample_index], sx, 8)
            w, w_clips = quantize(wf, sw, 8)
            bias = np.rint(bf.astype(np.float64)/(sx*sw)).astype(np.int64)
        report["inputs"].append({"layer": layer, "validation_sha256": expected_sha, "config_sha256": frozen[relative],
                                 "sample_id": sample_id, "input_clipping": x_clips, "weight_clipping": w_clips})
        for tile in range(16):
            sl = slice(tile*16, tile*16+16)
            export(x, w[:,sl], bias[sl], np.asarray(config["shifts"])[sl],
                   {"kind": "frozen_validation", "layer": layer, "tile": tile, "sample_id": sample_id})
        print("Exported direct-model layer", layer, flush=True)
    # Declared synthetic boundaries exercise accumulator equality before output
    # saturation, so a saturated INT8 result cannot hide an arithmetic defect.
    rng = np.random.default_rng(6412816)
    for xv,wv in [(-128,-128),(-128,127),(127,-128),(127,127),(0,0)]:
        export(np.full((99,64),xv),np.full((64,16),wv),
               np.array([-32768,32767,-1,0]*4), np.array([0,1,7,15,23,24,47,2]*2),
               {"kind":"full_range_constant", "x":xv,"w":wv})
    export(np.zeros((99,64)),np.zeros((64,16)),
           np.array([-32768,-259,-257,-255,-5,-3,-1,0,1,3,5,253,255,257,32767,127]),
           np.array([0,1,1,1,1,1,1,0,1,1,1,1,1,1,15,47]), {"kind":"RNE_ties_and_saturation"})
    for index in range(16):
        export(rng.integers(-128,128,(99,64)),rng.integers(-128,128,(64,16)),
               rng.integers(-32768,32768,16),rng.integers(0,25,16),{"kind":"random_signed8","random_index":index})
    report["completed"] = True
    report["real_tiles"] = 192
    report["synthetic_tiles"] = len(report["cases"])-192
    report["completed_utc"] = datetime.now(timezone.utc).isoformat()
    (out / "manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    print("MANIFEST",out/"manifest.json",flush=True)


if __name__ == "__main__":
    main()
