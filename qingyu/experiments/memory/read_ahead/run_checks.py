"""Run the independent four-state read-ahead protocol/storage regression."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[17, 271, 818, 90210, 20261111, 1, 73, 4093, 65537, 314159])
    args = parser.parse_args()
    for program in ("iverilog", "vvp"):
        if not shutil.which(program):
            raise SystemExit(f"Required four-state simulator executable not found: {program}")
    output = HERE / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    sources = [HERE / "qingyu_shared_read_ahead.sv", HERE / "tb_read_ahead.sv", Path(__file__)]
    hashes = {p.name: sha(p) for p in sources}
    report = {
        "schema": "qingyu-read-ahead-independent-check-v1", "passed": False,
        "source_sha256_before": hashes, "runs": [],
        "scope": "Standalone controller ICB protocol, four-state synchronous RAM and functional correctness",
        "limits": ["No official fabric integration or vendor macro timing measured",
                   "No area, power, energy, STA or full-task throughput claim",
                   "All RAM words initialized before reading; RAM Q is poisoned after every write",
                   "Reference memory changes only on accepted ICB writes; no DUT internal state inspected"],
    }
    result = output / "result.json"

    def save():
        result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    save()
    executable = output / "read_ahead.vvp"
    command = ["iverilog", "-g2012", "-Wall", "-s", "tb_read_ahead", "-o", str(executable),
               str(sources[0]), str(sources[1])]
    report["compile_command"] = command
    report["iverilog_version"] = subprocess.run(["iverilog", "-V"], text=True, capture_output=True).stdout.splitlines()[:2]
    with (output / "compile.log").open("w", encoding="utf-8") as log:
        completed = subprocess.run(command, cwd=HERE, stdout=log, stderr=subprocess.STDOUT)
    report["compile_returncode"] = completed.returncode
    save()
    if completed.returncode:
        raise SystemExit(f"Compile failed; see {output / 'compile.log'}")
    for seed in args.seeds:
        log_path = output / f"seed_{seed}.log"
        timed_out = False
        with log_path.open("w", encoding="utf-8") as log:
            try:
                completed = subprocess.run(["vvp", str(executable), f"+SEED={seed}"], cwd=HERE,
                                           stdout=log, stderr=subprocess.STDOUT, timeout=60)
                returncode = completed.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                returncode = None
        text = log_path.read_text(encoding="utf-8")
        line = next((line for line in text.splitlines() if line.startswith("PASS read_ahead ")), None)
        passed = returncode == 0 and line is not None
        metrics = {name: int(value) for name, value in re.findall(r"(\w+)=(\d+)", line or "")}
        report["runs"].append({"seed": seed, "passed": passed, "timed_out": timed_out,
                               "returncode": returncode, "log": log_path.name, "metrics": metrics})
        save()
        print(f"seed={seed} {'PASS' if passed else 'FAIL'}", flush=True)
        if not passed:
            print(text, flush=True)
            raise SystemExit(f"Regression stopped on first failure: {result}")
    report["source_sha256_after"] = {p.name: sha(p) for p in sources}
    if report["source_sha256_after"] != hashes:
        save()
        raise SystemExit("Sources changed during regression; results are not frozen")
    report["passed"] = True
    report["meaning_of_passed"] = "All requested seeds passed independent protocol/memory checks; not a PPA or SoC acceptance"
    save()
    print(result, flush=True)


if __name__ == "__main__":
    main()
