"""Trace FC1 vectors using the PINNED official KWT code and checkpoint.

This tool requires the official repository at commit 237e4097, TensorFlow and
TensorFlow Addons. It has not been run when those dependencies are unavailable.
Input NPZ: audio[S,16000] containing waveforms prepared by the official pinned
dataset loader, optional sample_ids[S], optional split scalar. This tool does
not replace the official sample splitting, waveform normalization, unknown or
silence generation. No training or weight modification is performed.
"""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

PINNED_COMMIT = "237e4097"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="official keyword-transformer checkout")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--audio-npz", type=Path)
    inputs.add_argument("--silence-smoke", action="store_true",
                        help="generated zero waveform for checkpoint/shape smoke only, no dataset accuracy")
    parser.add_argument("--split", choices=["training", "validation", "testing"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0, help="explicit sample limit, 0 uses every supplied sample")
    args = parser.parse_args()
    repo = args.repo.resolve()
    actual_commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if not actual_commit.startswith(PINNED_COMMIT):
        raise ValueError(f"checkout must be {PINNED_COMMIT}; actual HEAD is {actual_commit}")
    model_dir = repo / "models_data_v2_12_labels" / "kwt1"
    checkpoint = model_dir / "best_weights"
    checkpoint_files = [Path(str(checkpoint) + ".index")] + sorted(model_dir.glob("best_weights.data-*"))
    if len(checkpoint_files) < 2 or not all(path.is_file() for path in checkpoint_files):
        raise FileNotFoundError("best_weights index/data checkpoint files are required")
    if args.silence_smoke:
        if args.split is not None:
            parser.error("generated smoke audio cannot be declared a dataset split")
        split = "functional_smoke"
        audio = np.zeros((1, 16000), dtype=np.float32)
        sample_ids = np.array(["generated-zero-waveform-functional-smoke"])
        labels = np.array([0], dtype=np.int32)
    else:
        if args.split is None:
            parser.error("--audio-npz requires an explicit --split")
        split = args.split
        with np.load(args.audio_npz, allow_pickle=False) as archive:
            audio = np.asarray(archive["audio"], dtype=np.float32)
            sample_ids = archive["sample_ids"] if "sample_ids" in archive else np.array([f"supplied-{i}" for i in range(len(audio))])
            labels = np.asarray(archive["labels"], dtype=np.int32) if "labels" in archive else np.full(len(audio), -1, dtype=np.int32)
            if "split" in archive and str(archive["split"].item()) != split:
                raise ValueError("input split metadata does not match --split")
    if audio.ndim != 2 or audio.shape[1] != 16000 or not len(audio) or not np.all(np.isfinite(audio)):
        raise ValueError("audio must be nonempty finite float waveforms with shape [S,16000]")
    if sample_ids.shape != (len(audio),):
        raise ValueError("sample_ids must have one entry per waveform")
    if labels.shape != (len(audio),):
        raise ValueError("labels must have one entry per waveform")
    if args.limit < 0:
        raise ValueError("limit must be nonnegative")
    if args.limit:
        audio, sample_ids, labels = audio[:args.limit], sample_ids[:args.limit], labels[:args.limit]
    try:
        import tensorflow as tf
        import tensorflow_addons as tfa
    except ImportError as exc:
        raise RuntimeError("Install compatible TensorFlow/TensorFlow Addons in an isolated model environment; no extraction was performed") from exc
    sys.path.insert(0, str(repo))
    from kws_streaming.train import base_parser
    # Import official utils first: its model registry imports kws_transformer;
    # entering through kws_transformer itself causes an upstream circular import.
    from kws_streaming.models import utils as _official_utils
    from kws_streaming.models import kws_transformer, model_flags

    # Use the pinned official defaults and saved flags, then disable training
    # augmentation explicitly. The official layer classes perform preprocessing.
    official_parser = base_parser.base_parser()
    kws_transformer.model_parameters(official_parser)
    flags = official_parser.parse_args([])
    saved_flags = json.loads((model_dir / "flags.json").read_text(encoding="utf-8"))
    for name, value in saved_flags.items():
        setattr(flags, name, value)
    for name, value in {"batch_size": 1, "training": False, "train": 0,
                        "use_spec_augment": 0, "use_spec_cutout": 0,
                        "sp_time_shift_ms": 0.0, "sp_resample": 0.0,
                        "dropout1": 0.0}.items():
        setattr(flags, name, value)
    flags = model_flags.update_flags(flags)
    if (flags.num_layers, flags.d_model, flags.mlp_dim, flags.heads) != (12, 64, 256, 1):
        raise ValueError("saved KWT-1 dimensions do not match the contest")
    if flags.attention_type != "time" or bool(flags.prenorm) or bool(flags.distill_teacher_json):
        raise ValueError("expected time-domain PostNorm KWT-1 without distillation token")
    full = kws_transformer.model(flags)
    status = full.load_weights(str(checkpoint))
    if hasattr(status, "assert_existing_objects_matched"):
        status.assert_existing_objects_matched()
        status.expect_partial()  # checkpoint may also contain optimizer state
    transformers = [layer for layer in full.layers if hasattr(layer, "enc_layers")]
    if len(transformers) != 1:
        raise ValueError("could not uniquely identify the official time transformer")
    transformer = transformers[0]
    if transformer.distill_emb is not None:
        raise ValueError("unexpected distillation token")
    # Importing the pinned data loader disables eager execution. Build one
    # probe model and evaluate via Keras instead of assuming Tensor.numpy().
    features = transformer.input
    if tuple(features.shape) != (1, 98, 40):
        raise ValueError(f"official feature shape is {features.shape}, expected [1,98,40]")
    patches = transformer.patch_proj(features)
    token = tf.broadcast_to(transformer.class_emb, [1, 1, 64])
    hidden = tf.concat([token, patches], axis=1) + transformer.pos_emb
    input_probes, output_probes = [], []
    for block in transformer.enc_layers:
        attention, _ = block.att(hidden)
        input_fc1 = block.layernorm1(hidden + block.dropout1(attention, training=False))
        output_fc1 = block.ffn.layers[0](input_fc1)
        input_probes.append(input_fc1)
        output_probes.append(output_fc1)
        hidden, _ = block(hidden, training=False)
    official_class = transformer(features, training=False)
    probe = tf.keras.Model(full.inputs, input_probes + output_probes + [hidden[:, 0, :], official_class])
    xs: list[list[np.ndarray]] = [[] for _ in range(12)]
    ys: list[list[np.ndarray]] = [[] for _ in range(12)]
    weights, biases = [], []
    for block in transformer.enc_layers:
        w, b = block.ffn.layers[0].get_weights()
        if w.shape != (64, 256) or b.shape != (256,):
            raise ValueError("FC1 checkpoint weight dimensions are incorrect")
        weights.append(w)
        biases.append(b)
    max_dense_difference = 0.0
    for sample_index, waveform in enumerate(audio):
        values = probe.predict_on_batch(waveform[None, :])
        for layer in range(12):
            x = np.asarray(values[layer][0], dtype=np.float32)
            y = np.asarray(values[12 + layer][0], dtype=np.float32)
            if x.shape != (99, 64) or y.shape != (99, 256):
                raise ValueError("FC1 input/output dimensions differ from the contest")
            independent = x @ weights[layer] + biases[layer]
            difference = float(np.max(np.abs(independent - y)))
            max_dense_difference = max(max_dense_difference, difference)
            if not np.allclose(independent, y, rtol=3e-5, atol=2e-5):
                raise ValueError("traced Dense output disagrees with independent X@W+b")
            xs[layer].append(x)
            ys[layer].append(y)
        if not np.allclose(values[24], values[25], rtol=3e-5, atol=2e-5):
            raise ValueError("manual input tracing changed official transformer output")
        print(f"extracted sample {sample_index + 1}/{len(audio)}", flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    for layer in range(12):
        np.savez_compressed(args.output / f"layer{layer:02d}.npz",
                            X=np.stack(xs[layer]), W=weights[layer], b=biases[layer],
                            Y=np.stack(ys[layer]), sample_ids=sample_ids,
                            labels=labels,
                            split=np.array(split), layer=np.array(layer),
                            source_commit=np.array(actual_commit))
    manifest = {"kind": "OFFICIAL_CODE_FC1_EXTRACTION_ON_SYNTHETIC_SILENCE" if args.silence_smoke else "OFFICIAL_CODE_FC1_EXTRACTION_ON_SUPPLIED_AUDIO",
                "official_accuracy_evaluation": False,
                "official_dataset_selection_verified": False,
                "source_commit": actual_commit, "split": split,
                "samples": len(audio), "audio_npz_sha256": sha256(args.audio_npz) if args.audio_npz else None,
                "synthetic_audio": bool(args.silence_smoke),
                "sample_ids": sample_ids.astype(str).tolist(),
                "label_counts": {str(int(label)): int(np.count_nonzero(labels == label)) for label in np.unique(labels)},
                "checkpoint": {path.name: sha256(path) for path in checkpoint_files},
                "tensorflow": tf.__version__, "tensorflow_addons": tfa.__version__,
                "max_dense_check_absolute_difference": max_dense_difference,
                "note": "Dataset partition/label mapping/waveform preparation must come from the pinned official loader; this script does not certify the supplied selection."}
    (args.output / "extraction_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "extracted", "samples": len(audio), "layers": 12,
                      "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
