"""Calibrate training float NPZ, or convert with a frozen per-layer config.

NPZ keys: X[..., K], W[K,N], b[N], optional Y of shape [...,N].
For RTL export X is one [ROWS,K] matrix; multi-sample data exports sample folders.
"""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
try:
    from .reference import (LayerConfig, NrmseAccumulator, calibrate_layer,
                            decode_layer, encode_layer, export_layer_vectors, qlinear_int)
except ImportError:
    from reference import (LayerConfig, NrmseAccumulator, calibrate_layer,
                           decode_layer, encode_layer, export_layer_vectors, qlinear_int)


def load_case(path: Path, role: str) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    if not {"X", "W", "b"}.issubset(arrays):
        raise ValueError("NPZ must contain X, W and b")
    if "split" in arrays and str(arrays["split"].item()) != role:
        raise ValueError("NPZ split metadata does not match the declared data role")
    return arrays


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    calibrate = actions.add_parser("calibrate")
    calibrate.add_argument("--input", type=Path, required=True)
    calibrate.add_argument("--output", type=Path, required=True)
    calibrate.add_argument("--layer", type=int, required=True)
    calibrate.add_argument("--split", choices=["training"], required=True)
    calibrate.add_argument("--output-bits", type=int, choices=[16, 32], default=32)
    calibrate.add_argument("--output-headroom-bits", type=int, default=0,
                           help="fixed extra shift after training-only nonsaturating calibration")
    convert = actions.add_parser("convert")
    convert.add_argument("--input", type=Path, required=True)
    convert.add_argument("--config", type=Path, required=True)
    convert.add_argument("--output", type=Path, required=True)
    convert.add_argument("--split", choices=["training", "validation", "testing"], required=True)
    convert.add_argument("--lanes", type=int, default=4)
    convert.add_argument("--expect-output-bits", type=int, choices=[16, 32],
                         help="fail if the frozen format does not match the RTL build")
    args = parser.parse_args()
    arrays = load_case(args.input, args.split)
    x, w, b = arrays["X"], arrays["W"], arrays["b"]
    if args.action == "calibrate":
        config = calibrate_layer(x, w, b, args.layer, role=args.split, output_bits=args.output_bits,
                                 output_headroom_bits=args.output_headroom_bits)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(config.as_dict(), indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"result": "frozen_training_configuration", "path": str(args.output.resolve())}))
        return
    config = LayerConfig.from_dict(json.loads(args.config.read_text(encoding="utf-8")))
    if args.expect_output_bits is not None and config.output_bits != args.expect_output_bits:
        raise ValueError("frozen output_bits does not match the requested RTL output width")
    qx, qw, qb, shifts = encode_layer(x, w, b, config)
    result = qlinear_int(qx, qw, qb, shifts, output_bits=config.output_bits)
    decoded = decode_layer(result.output, config)
    reference = arrays.get("Y", np.asarray(x, dtype=np.float64) @ np.asarray(w, dtype=np.float64) + b)
    metric = NrmseAccumulator()
    metric.update(config.layer, reference, decoded)
    args.output.mkdir(parents=True, exist_ok=True)
    samples_x = qx.reshape((-1,) + qx.shape[-2:])
    samples_y = result.output.reshape((-1,) + result.output.shape[-2:])
    records = []
    for index, (one_x, one_y) in enumerate(zip(samples_x, samples_y)):
        target = args.output if len(samples_x) == 1 else args.output / f"sample{index:04d}"
        records.append(export_layer_vectors(target, one_x, qw, qb, shifts, one_y, lanes=args.lanes,
                                            output_bits=config.output_bits))
    report = {"kind": "SUPPLIED_FLOAT_NPZ", "official_accuracy_evaluation": False,
              "split": args.split, "layer": config.layer, "output_bits": config.output_bits,
              "format_version": config.format_version,
              "output_headroom_bits": config.output_headroom_bits,
              "reference_kind": "supplied_Y" if "Y" in arrays else "local_float64_matmul",
              "source_npz_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
              "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
              "saturation_count": result.saturation_count, "accuracy": metric.summary(),
              "samples": records}
    (args.output / "conversion_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    np.savez_compressed(args.output / "decoded.npz", decoded=decoded, reference=reference)
    print(json.dumps({"result": "converted_with_frozen_configuration", "layer": config.layer,
                      "max_nrmse": report["accuracy"]["max_nrmse"],
                      "saturation_count": result.saturation_count, "samples": len(records)}))


if __name__ == "__main__":
    main()
