"""Apply pinned AudioProcessor to individually sourced WAVs for functional smoke.

The output remains non-representative. Hash splits are assigned by the pinned
code, and per-file provenance must also be retained by the caller/downloader.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--wav-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if not commit.startswith("237e4097"):
        raise ValueError("repository must be pinned237e4097")
    paths = sorted(args.wav_root.glob("*/*.wav"))
    if not paths:
        raise FileNotFoundError("no individually sourced speech WAVs found")
    sys.path.insert(0, str(repo))
    import tensorflow as tf
    from kws_streaming.train import base_parser
    from kws_streaming.models import utils as _official_utils
    from kws_streaming.models import kws_transformer, model_flags
    from kws_streaming.data import input_data
    official_parser = base_parser.base_parser()
    kws_transformer.model_parameters(official_parser)
    flags = official_parser.parse_args([])
    directory = repo / "models_data_v2_12_labels/kwt1"
    for name, value in json.loads((directory / "flags.json").read_text(encoding="utf-8")).items():
        setattr(flags, name, value)
    flags.data_dir, flags.data_url, flags.batch_size = None, "", 1
    flags.training, flags.train = False, 0
    flags = model_flags.update_flags(flags)
    wanted = flags.wanted_words.split(",")
    groups = {split: [] for split in ("training", "validation", "testing")}
    graph = tf.Graph()
    config = tf.compat.v1.ConfigProto(intra_op_parallelism_threads=1, inter_op_parallelism_threads=1)
    with graph.as_default(), tf.compat.v1.Session(graph=graph, config=config) as session:
        processor = input_data.AudioProcessor(flags)
        for path in paths:
            split = input_data.which_set(str(path), flags.validation_percentage, flags.testing_percentage)
            audio = np.asarray(processor.get_features_for_wav(str(path.resolve()), flags, session)[0], dtype=np.float32).reshape(-1)
            if audio.shape != (16000,) or not np.all(np.isfinite(audio)):
                raise ValueError("official waveform loader output is invalid")
            word = path.parent.name
            label = wanted.index(word) + 2 if word in wanted else 1
            groups[split].append({"path": str(path.relative_to(args.wav_root)), "label": label,
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "audio": audio})
    args.output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for split, records in groups.items():
        if not records:
            continue
        target = args.output / f"audio_{split}_smoke.npz"
        np.savez_compressed(target, audio=np.stack([record["audio"] for record in records]),
                            labels=np.array([record["label"] for record in records], dtype=np.int32),
                            sample_ids=np.array([record["path"] for record in records]),
                            split=np.array(split), source_commit=np.array(commit),
                            representative_dataset=np.array(False))
        summaries.append({"split": split, "file": target.name, "samples": [
            {key: value for key, value in record.items() if key != "audio"} for record in records]})
    (args.output / "wav_smoke_manifest.json").write_text(json.dumps({
        "kind": "PINNED_OFFICIAL_LOADER_INDIVIDUAL_WAV_SMOKE", "source_commit": commit,
        "representative_dataset": False, "official_accuracy_evaluation": False,
        "tensorflow": tf.__version__, "partitions": summaries}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "prepared_individual_wav_smoke", "partitions": [
        {"split": item["split"], "samples": len(item["samples"])} for item in summaries]}))


if __name__ == "__main__":
    main()
