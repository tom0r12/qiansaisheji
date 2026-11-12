"""Build OUT16 task images and reusable frozen configs via the standard model.

Training data alone determine the INT16 output shifts. Configs also support
arbitrary later samples with prepare_layer.py convert --expect-output-bits 16.
A match of these fixed engineering tasks is not an official accuracy result.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "model"))
from reference import (NrmseAccumulator, calibrate_layer, decode_layer, encode_layer,
                       output_words, qlinear_int, unpack_int16_words, write_hex_words)
from prepare_layer import load_case

ST = 0x40000 // 4


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def convert_layer(source: Path, training: Path, validation: Path,
                  destination: Path, layer: int) -> dict:
    name = f"layer{layer:02d}"
    shared_path, expected_path = source / name / "shared.hex", source / name / "expected.hex"
    mem = np.array([int(word, 16) for word in shared_path.read_text().split()], dtype=np.uint64)
    exp32 = np.array([int(word, 16) for word in expected_path.read_text().split()], dtype=np.uint64)
    x = unpack_int16_words(mem[ST:ST + 3168]).reshape(99, 64)
    w = unpack_int16_words(mem[ST + 0x4000 // 4:ST + 0x4000 // 4 + 8192]).reshape(64, 256)
    bw = mem[ST + 0xc000 // 4:ST + 0xc000 // 4 + 512]
    b = (bw[0::2] | (bw[1::2] << np.uint64(32))).view(np.int64)
    sw = mem[ST + 0xc800 // 4:ST + 0xc800 // 4 + 64]
    sh32 = np.frombuffer(sw.astype("<u4").tobytes(), dtype=np.uint8).astype(np.int64)
    actual32 = qlinear_int(x, w, b, sh32)
    if not np.array_equal(output_words(actual32.output), exp32):
        raise ValueError(name + ": INT32 recompute does not match expected.hex")

    training_path, validation_path = training / (name + ".npz"), validation / (name + ".npz")
    tr, va = load_case(training_path, "training"), load_case(validation_path, "validation")
    cfg32 = calibrate_layer(tr["X"], tr["W"], tr["b"], layer, role="training")
    if not np.array_equal(cfg32.shifts, sh32):
        raise ValueError(name + ": training calibration does not reproduce the image shifts")
    _, qw, qb, _ = encode_layer(tr["X"], tr["W"], tr["b"], cfg32)
    if not (np.array_equal(qw, w) and np.array_equal(qb, b)):
        raise ValueError(name + ": quantized weights/bias differ from the image")
    cfg16 = calibrate_layer(tr["X"], tr["W"], tr["b"], layer, role="training", output_bits=16)
    if (cfg16.x_exponent != cfg32.x_exponent or cfg16.w_exponents != cfg32.w_exponents
            or cfg16.weights_sha256 != cfg32.weights_sha256):
        raise ValueError(name + ": output-width conversion changed input or weight encoding")
    y16 = qlinear_int(x, w, b, cfg16.shifts, output_bits=cfg16.output_bits)

    nr = {}
    for tag, cfg in (("int32", cfg32), ("int16", cfg16)):
        vx, vw, vb, shifts = encode_layer(va["X"], va["W"], va["b"], cfg)
        result = qlinear_int(vx, vw, vb, shifts, output_bits=cfg.output_bits)
        yf = va.get("Y", va["X"].astype(np.float64) @ va["W"].astype(np.float64) + va["b"])
        metric = NrmseAccumulator()
        metric.update(layer, yf, decode_layer(result.output, cfg))
        nr[tag] = {"nrmse_percent": metric.summary()["max_nrmse"] * 100,
                   "saturated": result.saturation_count}

    new = mem.copy()
    sh16 = np.asarray(cfg16.shifts, dtype=np.uint8)
    new[ST + 0xc800 // 4:ST + 0xc800 // 4 + 64] = np.frombuffer(sh16.tobytes(), dtype="<u4")
    out = destination / name
    out.mkdir(parents=True, exist_ok=True)
    write_hex_words(out / "shared.hex", new)
    write_hex_words(out / "expected.hex", output_words(y16.output, output_bits=16))
    config_path = out / "config.json"
    config_path.write_text(json.dumps(cfg16.as_dict(), indent=2) + "\n", encoding="utf-8")
    return {
        "layer": layer, "output_bits": 16, "format_version": cfg16.format_version,
        "config": f"{name}/config.json", "config_sha256": sha256(config_path),
        "shift16_min": int(sh16.min()), "shift16_max": int(sh16.max()),
        "shift_delta_mean": float((sh16.astype(np.int64) - sh32).mean()),
        "task_saturated": y16.saturation_count, "validation": nr,
        "source_sha256": {"shared.hex": sha256(shared_path), "expected.hex": sha256(expected_path),
                          "training_npz": sha256(training_path), "validation_npz": sha256(validation_path)},
        "sha256": {name: sha256(out / name) for name in ("shared.hex", "expected.hex", "config.json")},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?", type=Path, default=Path("reports/soc_performance_q16"))
    parser.add_argument("--source", type=Path, default=Path("reports/soc_performance_20261104_224417"))
    parser.add_argument("--training", type=Path, default=Path("model/full_v2_run/float_training"))
    parser.add_argument("--validation", type=Path, default=Path("model/full_v2_run/float_validation"))
    parser.add_argument("--layers", default="all", help="all, or comma-separated ids for development checks")
    args = parser.parse_args()
    layers = list(range(12)) if args.layers == "all" else [int(x) for x in args.layers.split(",")]
    if not layers or len(set(layers)) != len(layers) or any(x not in range(12) for x in layers):
        parser.error("layers must be unique indices from 0 to 11")
    source, training, validation, destination = [
        (ROOT / p).resolve() for p in (args.source, args.training, args.validation, args.destination)]
    rows = []
    for layer in layers:
        row = convert_layer(source, training, validation, destination, layer)
        rows.append(row)
        print(f"layer{layer:02d} frozen INT16 config; validation NRMSE={row['validation']['int16']['nrmse_percent']:.6f}%",
              flush=True)
    report = {
        "source": str(source), "output_bits": 16, "official_accuracy_evaluation": False,
        "all_12_layers": set(layers) == set(range(12)), "layers": rows,
        "max_validation_nrmse_percent": {
            tag: max(row["validation"][tag]["nrmse_percent"] for row in rows) for tag in ("int32", "int16")},
    }
    (destination / "q16_images.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("MAX", report["max_validation_nrmse_percent"])


if __name__ == "__main__":
    main()
