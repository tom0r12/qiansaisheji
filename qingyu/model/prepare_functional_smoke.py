"""Quantize extracted KWT vectors for FUNCTIONAL SMOKE ONLY.

Scales are fitted to the smoke inputs themselves, never claimed as training
calibration. The generated config has a deliberately unsupported submission
format/role so prepare_layer.py cannot accidentally use it as a frozen model.
"""

import argparse
import json
from pathlib import Path
import numpy as np
try:
    from .reference import (LayerConfig, power2_scale_exponent, weight_digest,
                            encode_layer, accumulate, requantize, qlinear_int,
                            decode_layer, export_layer_vectors)
except ImportError:
    from reference import (LayerConfig, power2_scale_exponent, weight_digest,
                           encode_layer, accumulate, requantize, qlinear_int,
                           decode_layer, export_layer_vectors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for layer in range(12):
        source = args.input / f"layer{layer:02d}.npz"
        with np.load(source, allow_pickle=False) as archive:
            x, w, b, y = [np.asarray(archive[name], dtype=np.float64) for name in ("X", "W", "b", "Y")]
            source_split = str(archive["split"].item())
        config = LayerConfig(layer, power2_scale_exponent(float(np.max(np.abs(x)))),
                             [power2_scale_exponent(float(value)) for value in np.max(np.abs(w), axis=0)],
                             [0] * w.shape[1], weight_digest(w, b),
                             calibration_role="functional_smoke_only",
                             format_version="qingyu-fixed-v1-functional-smoke")
        qx, qw, qb, _ = encode_layer(x, w, b, config)
        accumulators = accumulate(qx, qw, qb)
        shifts = []
        for j in range(w.shape[1]):
            for shift in range(48):
                _, count = requantize(accumulators[..., j, None], [shift])
                if count == 0:
                    shifts.append(shift)
                    break
        config = LayerConfig(config.layer, config.x_exponent, config.w_exponents,
                             shifts, config.weights_sha256,
                             calibration_role=config.calibration_role,
                             format_version=config.format_version)
        qy = qlinear_int(qx, qw, qb, shifts)
        decoded = decode_layer(qy.output, config)
        directory = args.output / f"layer{layer:02d}"
        directory.mkdir(parents=True, exist_ok=True)
        sx = qx.reshape((-1,) + qx.shape[-2:])
        sy = qy.output.reshape((-1,) + qy.output.shape[-2:])
        exports = []
        for sample, (one_x, one_y) in enumerate(zip(sx, sy)):
            target = directory if len(sx) == 1 else directory / f"sample{sample:04d}"
            exports.append(export_layer_vectors(target, one_x, qw, qb, shifts, one_y))
        (directory / "SMOKE_ONLY_config.json").write_text(json.dumps(config.as_dict(), indent=2) + "\n", encoding="utf-8")
        nrmse = float(np.sqrt(np.mean((decoded - y) ** 2)) / max(np.sqrt(np.mean(y ** 2)), 1e-8))
        records.append({"layer": layer, "source_split": source_split, "samples": len(sx),
                        "input_shape": list(x.shape), "weight_shape": list(w.shape),
                        "output_shape": list(y.shape), "smoke_only_nrmse": nrmse,
                        "saturation_count": qy.saturation_count, "exports": exports})
    report = {"kind": "REAL_KWT_CHECKPOINT_FUNCTIONAL_ONLY_QUANTIZED_SMOKE",
              "official_accuracy_evaluation": False, "training_calibration": False,
              "submission_configuration": False,
              "warning": "Ranges fitted to these same smoke inputs. This is only an RTL/format check, not validation accuracy or a submission numerical configuration.",
              "layers": records}
    (args.output / "SMOKE_ONLY_manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "functional_only_quantized_smoke", "layers": len(records),
                      "training_calibration": False, "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
