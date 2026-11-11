"""Generate deterministic SYNTHETIC engineering vectors, never an accuracy claim."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
try:
    from .reference import qlinear_int, export_layer_vectors
except ImportError:
    from reference import qlinear_int, export_layer_vectors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("tb/vectors"))
    parser.add_argument("--layers", type=int, default=12)
    parser.add_argument("--rows", type=int, default=99)
    parser.add_argument("--k", type=int, default=64)
    parser.add_argument("--outputs", type=int, default=256)
    parser.add_argument("--lanes", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261026)
    args = parser.parse_args()
    if not 1 <= args.layers <= 12 or min(args.rows, args.k, args.outputs, args.lanes) < 1:
        parser.error("positive dimensions and 1..12 layers required")
    rng = np.random.default_rng(args.seed)
    manifest = {"kind": "SYNTHETIC_ENGINEERING_VECTORS", "official_accuracy_evaluation": False,
                "seed": args.seed, "format": "qingyu-fixed-v1", "layers": []}
    args.output.mkdir(parents=True, exist_ok=True)
    for layer in range(args.layers):
        x = rng.integers(-30000, 30001, (args.rows, args.k), dtype=np.int16)
        w = rng.integers(-30000, 30001, (args.k, args.outputs), dtype=np.int16)
        b = rng.integers(-(1 << 20), 1 << 20, args.outputs, dtype=np.int64)
        shifts = ((np.arange(args.outputs) + layer) % 8).astype(np.int64)
        # Include realistic fixed-point range stress, both signs and saturation.
        if args.outputs >= 4:
            b[0], b[1] = (1 << 43) + 3, -(1 << 43) - 3
            shifts[0] = shifts[1] = 12
        if args.rows >= 2:
            x[0, :] = 0
            x[1, :] = np.where(np.arange(args.k) % 2, -32767, 32767)
        result = qlinear_int(x, w, b, shifts)
        path = args.output / f"layer{layer:02d}"
        record = export_layer_vectors(path, x, w, b, shifts, result.output, lanes=args.lanes)
        record.update(layer=layer, directory=path.name, saturation_count=result.saturation_count)
        manifest["layers"].append(record)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "generated", "kind": manifest["kind"],
                      "layers": len(manifest["layers"]), "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
