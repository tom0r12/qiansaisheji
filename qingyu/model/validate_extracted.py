"""Freeze on training FC1 vectors; evaluate a disjoint validation subset.

No testing split is accepted. Vector export is limited to the first validation
sample per layer unless --export-samples requests more. Dataset scope and class
coverage must be supplied through manifests and must be assessed separately.
"""

import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
try:
    from .reference import (calibrate_layer, encode_layer, qlinear_int,
                            decode_layer, NrmseAccumulator, export_layer_vectors)
except ImportError:
    from reference import (calibrate_layer, encode_layer, qlinear_int,
                           decode_layer, NrmseAccumulator, export_layer_vectors)


def load(path, role):
    with np.load(path, allow_pickle=False) as archive:
        values = {key: archive[key] for key in archive.files}
    if str(values["split"].item()) != role:
        raise ValueError(f"{path} is not declared as {role}")
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--export-samples", type=int, default=1)
    parser.add_argument("--scope", required=True, help="human-readable dataset/class-coverage limitation")
    parser.add_argument("--choose-by-layer-label", action="store_true",
                        help="export one validation task per layer, selecting label=layer")
    parser.add_argument("--output-bits", type=int, choices=[16, 32], default=32)
    parser.add_argument("--output-headroom-bits", type=int, default=0,
                        help="one globally fixed extra shift, calibrated from training only")
    parser.add_argument("--lanes", type=int, default=4)
    args = parser.parse_args()
    if args.export_samples < 0:
        parser.error("export-samples cannot be negative")
    if args.choose_by_layer_label and args.export_samples != 1:
        parser.error("choose-by-layer-label requires export-samples=1")
    args.output.mkdir(parents=True, exist_ok=True)
    metric = NrmseAccumulator()
    records = []
    train_ids, val_ids = None, None
    for layer in range(12):
        training = load(args.training / f"layer{layer:02d}.npz", "training")
        validation = load(args.validation / f"layer{layer:02d}.npz", "validation")
        current_train = set(training["sample_ids"].astype(str).tolist())
        current_val = set(validation["sample_ids"].astype(str).tolist())
        if current_train & current_val:
            raise ValueError("training and validation sample identifiers overlap")
        if train_ids is not None and (train_ids != current_train or val_ids != current_val):
            raise ValueError("sample sets differ across layers")
        train_ids, val_ids = current_train, current_val
        training_labels = np.asarray(training.get("labels", []), dtype=np.int32)
        validation_labels = np.asarray(validation.get("labels", []), dtype=np.int32)
        if args.choose_by_layer_label and (set(training_labels.tolist()) != set(range(12)) or set(validation_labels.tolist()) != set(range(12))):
            raise ValueError("all12 labels must be present in training and validation for the selected tasks")
        config = calibrate_layer(training["X"], training["W"], training["b"], layer,
                                 role="training", output_bits=args.output_bits,
                                 output_headroom_bits=args.output_headroom_bits)
        directory = args.output / f"layer{layer:02d}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "frozen_training_config.json").write_text(json.dumps(config.as_dict(), indent=2) + "\n", encoding="utf-8")
        qx, qw, qb, shifts = encode_layer(validation["X"], validation["W"], validation["b"], config)
        result = qlinear_int(qx, qw, qb, shifts, output_bits=config.output_bits)
        decoded = decode_layer(result.output, config)
        metric.update(layer, validation["Y"], decoded)
        clipping = int(np.count_nonzero(np.abs(np.rint(validation["X"] / (2.0 ** config.x_exponent))) > 32767))
        selected = [int(np.flatnonzero(validation_labels == layer)[0])] if args.choose_by_layer_label else list(range(min(args.export_samples, qx.shape[0])))
        count = len(selected)
        chosen_tasks = []
        for sample in selected:
            target = directory if count == 1 else directory / f"sample{sample:04d}"
            export_layer_vectors(target, qx[sample], qw, qb, shifts, result.output[sample],
                                 lanes=args.lanes, output_bits=config.output_bits)
            sample_ref, sample_got = validation["Y"][sample], decoded[sample]
            task_nrmse = float(np.sqrt(np.mean((sample_got - sample_ref) ** 2)) /
                               max(np.sqrt(np.mean(sample_ref ** 2)), 1e-8))
            chosen_tasks.append({"sample_index": sample, "sample_id": str(validation["sample_ids"][sample]),
                                 "label": int(validation_labels[sample]) if validation_labels.size else None,
                                 "nrmse": task_nrmse,
                                 "integer_case_sha256": hashlib.sha256((target / "integer_case.npz").read_bytes()).hexdigest()})
        records.append({"layer": layer, "input_clipping_count": clipping,
                        "config_sha256": hashlib.sha256((directory / "frozen_training_config.json").read_bytes()).hexdigest(),
                        "output_saturation_count": result.saturation_count,
                        "exported_validation_samples": count, "chosen_tasks": chosen_tasks})
        print(f"validated layer {layer}", flush=True)
    report = {"kind": "FROZEN_TRAINING_DISJOINT_VALIDATION_SUBSET",
              "output_bits": args.output_bits, "lanes": args.lanes,
              "output_headroom_bits": args.output_headroom_bits,
              "scope": args.scope, "official_600_sample_evaluation": False,
              "source_commit": str(training["source_commit"].item()),
              "training_sample_ids": sorted(train_ids), "validation_sample_ids": sorted(val_ids),
              "training_samples": len(train_ids), "validation_samples": len(val_ids),
              "training_label_counts": {str(int(label)): int(np.count_nonzero(training_labels == label)) for label in np.unique(training_labels)},
              "validation_label_counts": {str(int(label)): int(np.count_nonzero(validation_labels == label)) for label in np.unique(validation_labels)},
              "sample_sets_disjoint": True, "numerical_configuration_fit_role": "training",
              "subset_accuracy": metric.summary(require_all_layers=True), "layer_diagnostics": records}
    (args.output / "validation_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "frozen_training_validation_subset", "training_samples": len(train_ids),
                      "validation_samples": len(val_ids),
                      "max_nrmse_percent": report["subset_accuracy"]["max_nrmse"] * 100,
                      "official_600_sample_evaluation": False}))


if __name__ == "__main__":
    main()
