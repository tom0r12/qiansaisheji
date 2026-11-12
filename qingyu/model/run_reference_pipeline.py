"""Reproduce official-loader preparation, frozen training calibration and validation.

Uses only the training and validation partitions. All stage logs are retained.
This local subset is not the organizer's frozen600-sample evaluation.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=Path("model/full_v2_run"))
    parser.add_argument("--training-count", type=int, default=256)
    parser.add_argument("--validation-count", type=int, default=256)
    args = parser.parse_args()
    if min(args.training_count, args.validation_count) < 12:
        parser.error("counts must allow all12 labels")
    marker = args.data_dir / ".qingyu_extraction.json"
    if marker.exists() and json.loads(marker.read_text(encoding="utf-8")).get("state") != "extracted":
        raise ValueError("dataset extraction has not completed")
    args.work.mkdir(parents=True, exist_ok=True)
    scripts = Path(__file__).resolve().parent
    repo = str(args.repo.resolve())
    # Preserve a same-volume ASCII junction on Windows. Resolving it restores
    # Unicode parent names that TensorFlow's Win32 directory glob cannot list.
    data = str(args.data_dir.absolute())
    work = args.work.resolve()
    stages = [
        ("prepare_training", ["prepare_official_audio.py", "--repo", repo, "--data-dir", data,
                              "--split", "training", "--count", str(args.training_count),
                              "--output", str(work / "audio_training.npz")]),
        ("prepare_validation", ["prepare_official_audio.py", "--repo", repo, "--data-dir", data,
                                "--split", "validation", "--count", str(args.validation_count),
                                "--output", str(work / "audio_validation.npz")]),
        ("extract_training", ["extract_kwt1.py", "--repo", repo, "--audio-npz", str(work / "audio_training.npz"),
                              "--split", "training", "--output", str(work / "float_training")]),
        ("extract_validation", ["extract_kwt1.py", "--repo", repo, "--audio-npz", str(work / "audio_validation.npz"),
                                "--split", "validation", "--output", str(work / "float_validation")]),
        ("freeze_validate_export", ["validate_extracted.py", "--training", str(work / "float_training"),
                                    "--validation", str(work / "float_validation"),
                                    "--output", str(work / "validation_vectors"),
                                    "--choose-by-layer-label", "--scope",
                                    "Official V2 full corpus; training-only calibration and disjoint local validation subset with all12labels; not organizer600"]),
    ]
    status = {"state": "running", "kind": "PINNED_KWT_TRAINING_VALIDATION_PIPELINE",
              "training_count": args.training_count, "validation_count": args.validation_count,
              "official_600_sample_evaluation": False, "stages": []}
    status_path = work / "pipeline_status.json"
    def save():
        status["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    for name, command in stages:
        status["current_stage"] = name
        save()
        print(json.dumps({"stage": name, "state": "running"}), flush=True)
        log = work / f"{name}.log"
        with log.open("w", encoding="utf-8") as output:
            process = subprocess.run([sys.executable, "-X", "utf8", str(scripts / command[0]), *command[1:]],
                                     stdout=output, stderr=subprocess.STDOUT)
        status["stages"].append({"name": name, "returncode": process.returncode, "log": str(log)})
        if process.returncode:
            status["state"] = "failed"
            save()
            raise RuntimeError(f"stage {name} failed; inspect {log}")
        save()
    report_path = work / "validation_vectors/validation_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    status.update(state="complete", report=str(report_path),
                  max_nrmse_percent=report["subset_accuracy"]["max_nrmse"] * 100)
    save()
    print(json.dumps({"state": "complete", "max_nrmse_percent": status["max_nrmse_percent"],
                      "report": str(report_path)}), flush=True)


if __name__ == "__main__":
    main()
