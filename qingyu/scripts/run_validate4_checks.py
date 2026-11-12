"""Compare opt15's validation API with unmodified opt14 and independent errors.

Runs on a host C compiler; no EDA, MMIO, official accuracy or PPA claim.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/h1500v/opt14_ybank2/rtl"
CANDIDATE = ROOT / "experiments/h1500v/opt15_validate4/rtl"
TEST = ROOT / "tb/test_validate4.c"
SYMBOLS = ("init", "reset", "validate", "run", "run_prepared")
DEFINES = ("QINGYU_OUT16", "QINGYU_FAST_TASK", "QINGYU_BLOCK_COPY",
           "QINGYU_DOUBLE_BUFFER", "QINGYU_READ_AHEAD")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    compiler = shutil.which(args.cc)
    if not compiler:
        parser.error(f"{args.cc} not found; run in WSL with GCC or specify --cc")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    work = ROOT / "build/validate4_checks" / stamp
    work.mkdir(parents=True)
    flags = ["-std=c11", "-D_DEFAULT_SOURCE", "-O3", "-funroll-loops",
             "-fstrict-aliasing", "-Wall", "-Wextra", "-Werror"]
    flags += ["-D" + define for define in DEFINES]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g"]
    sources = [BASE / "qingyu_accel.c", BASE / "qingyu_accel.h",
               CANDIDATE / "qingyu_accel.c", CANDIDATE / "qingyu_accel.h", TEST]
    result = dict(passed=False, scope="host validation API and error-code equivalence",
                  compiler=compiler, flags=flags, commands=[],
                  sources_sha256={str(p.relative_to(ROOT)): sha(p) for p in sources})
    result["compiler_version"] = subprocess.check_output(
        [compiler, "--version"], text=True).splitlines()[0]
    report = work / "result.json"
    report.write_text(json.dumps(result, indent=2))

    def run(command, name):
        command = list(map(str, command))
        result["commands"].append(command)
        report.write_text(json.dumps(result, indent=2))
        completed = subprocess.run(command, cwd=ROOT, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   timeout=180)
        (work / name).write_text(completed.stdout)
        if completed.returncode:
            raise RuntimeError(f"{name}: exit {completed.returncode}\n{completed.stdout[-5000:]}")
        return completed.stdout

    renamed = [f"-Dqingyu_{symbol}=baseline_{symbol}" for symbol in SYMBOLS]
    run([compiler, *flags, *renamed, "-I" + str(BASE), "-c", BASE / "qingyu_accel.c",
         "-o", work / "baseline.o"], "baseline_compile.log")
    run([compiler, *flags, "-I" + str(CANDIDATE), "-c", CANDIDATE / "qingyu_accel.c",
         "-o", work / "candidate.o"], "candidate_compile.log")
    executable = work / "validate4_test"
    run([compiler, *flags, "-I" + str(CANDIDATE), TEST, work / "baseline.o",
         work / "candidate.o", "-o", executable], "link.log")
    output = run([executable], "test.log")
    match = re.fullmatch(r"PASS validate4 checks=(\d+) baseline_equivalent=1 io_calls=0\s*", output)
    if not match:
        raise RuntimeError("Missing exact PASS marker")
    result.update(passed=True, checks=int(match[1]), baseline_equivalent=True,
                  sanitizer_enabled=args.sanitize,
                  tests=["all 256 shift byte values in all 256 columns and four alignments",
                         "signed 48-bit bias boundaries in every column",
                         "10000 mixed parameter sets",
                         "all structural error codes and precedence over malformed data",
                         "guard pages and no MMIO during validation"])
    report.write_text(json.dumps(result, indent=2))
    print(output.strip())
    print(report)


if __name__ == "__main__":
    main()
