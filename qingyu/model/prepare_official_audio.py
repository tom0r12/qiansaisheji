"""Export waveforms through the PINNED official Speech Commands loader.

Requires an already-extracted Speech Commands V2 directory. Never downloads
the dataset automatically. Labels/splits/unknown/silence come from the pinned
AudioProcessor; augmentation arguments are disabled for numerical calibration
or evaluation. Full dataset selection is still the caller's responsibility.
"""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--split", choices=["training", "validation", "testing"], required=True)
    parser.add_argument("--count", type=int, default=256)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.count <= 0 or args.offset < 0:
        parser.error("count must be positive and offset nonnegative")
    repo = args.repo.resolve()
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if not commit.startswith("237e4097"):
        raise ValueError("official repository must be pinned to commit237e4097")
    if not args.data_dir.is_dir():
        raise FileNotFoundError("data directory does not exist; no automatic download is performed")
    sys.path.insert(0, str(repo))
    import tensorflow as tf
    from kws_streaming.train import base_parser
    from kws_streaming.models import utils as _official_utils
    from kws_streaming.models import kws_transformer, model_flags
    from kws_streaming.data import input_data
    model_dir = repo / "models_data_v2_12_labels/kwt1"
    official_parser = base_parser.base_parser()
    kws_transformer.model_parameters(official_parser)
    flags = official_parser.parse_args([])
    for name, value in json.loads((model_dir / "flags.json").read_text(encoding="utf-8")).items():
        setattr(flags, name, value)
    flags.data_url = ""  # explicitly prohibit implicit 2+GB download/extraction
    flags.data_dir = str(args.data_dir.resolve())
    flags.batch_size = 1
    flags.training = False
    flags.train = 0
    flags.pick_deterministically = True
    flags = model_flags.update_flags(flags)
    np.random.seed(0)
    graph = tf.Graph()
    configuration = tf.compat.v1.ConfigProto(intra_op_parallelism_threads=1, inter_op_parallelism_threads=1)
    with graph.as_default(), tf.compat.v1.Session(graph=graph, config=configuration) as session:
        processor = input_data.AudioProcessor(flags)
        if processor.words_list != (model_dir / "labels.txt").read_text(encoding="utf-8").splitlines():
            raise ValueError("official data labels do not match checkpoint labels.txt")
        candidates = processor.data_index[args.split]
        if args.offset + args.count > len(candidates):
            raise ValueError(f"requested count exceeds selected partition size {len(candidates)}")
        selected = candidates[args.offset:args.offset + args.count]
        audio, labels = processor.get_data(args.count, args.offset, flags,
                                           background_frequency=0.0,
                                           background_volume_range=0.0,
                                           time_shift=0, mode=args.split,
                                           resample_offset=0.0,
                                           volume_augmentation_offset=0.0,
                                           sess=session)
    if audio.shape != (args.count, 16000) or not np.all(np.isfinite(audio)):
        raise ValueError("official loader did not return finite raw one-second audio")
    records = []
    for index, sample in enumerate(selected, start=args.offset):
        path = Path(sample["file"])
        actual_split = input_data.which_set(str(path), flags.validation_percentage, flags.testing_percentage)
        if sample["label"] != input_data.SILENCE_LABEL and actual_split != args.split:
            raise ValueError("loader sample differs from pinned hash partition")
        relative = str(path.relative_to(args.data_dir.resolve()))
        identifier = f"{args.split}:generated-silence:{index}" if sample["label"] == input_data.SILENCE_LABEL else f"wav:{relative}"
        record = {"partition_index": index, "sample_id": identifier, "label": sample["label"],
                  "file": relative,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        records.append(record)
    ids = np.array([item["sample_id"] for item in records])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, audio=np.asarray(audio, dtype=np.float32),
                        labels=np.asarray(labels, dtype=np.int32), sample_ids=ids,
                        split=np.array(args.split), source_commit=np.array(commit))
    manifest = {"kind": "PINNED_OFFICIAL_LOADER_AUDIO", "source_commit": commit,
                "split": args.split, "count": args.count, "offset": args.offset,
                "augmentation": "disabled", "tensorflow": tf.__version__,
                "official_600_sample_evaluation": False, "samples": records,
                "npz_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}
    manifest_path = args.output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "prepared_official_loader_audio", "samples": args.count,
                      "split": args.split, "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
