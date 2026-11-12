"""Compile independent Winograd integer/protocol tests and strict RTL lint."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def linux_path(path):
    path = path.resolve()
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def main():
    here = Path(__file__).resolve().parent
    root = here.parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seeds", type=int, nargs="+", default=[104729, 130363, 155921])
    parser.add_argument("--iverilog", default=shutil.which("iverilog") or "G:/iverilog/bin/iverilog.exe")
    parser.add_argument("--vvp", default=shutil.which("vvp") or "G:/iverilog/bin/vvp.exe")
    parser.add_argument("--wsl-distro", default="Ubuntu")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = (args.output or root / "build" / "winograd_int8" / stamp).resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = sorted(path for path in here.iterdir() if path.suffix in (".sv", ".py", ".json", ".md") and path.name != "SOURCE_SHA256.json")
    before = {path.name: sha(path) for path in sources}
    report = {"schema": "qingyu-winograd-int8-checks-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
              "sources_sha256": before, "source_directory": here.relative_to(root).as_posix(),
              "full_soc_tested": False, "formal_equivalence_tool_run": False, "ppa_measured": False,
              "commands": [], "simulations": [], "lint": [], "completed": False}

    def run(command, log_name):
        with (out / log_name).open("w", encoding="utf-8") as log:
            result = subprocess.run(list(map(str, command)), cwd=root, stdout=log, stderr=subprocess.STDOUT)
        report["commands"].append({"argv": list(map(str, command)), "cwd": str(root), "log": log_name, "returncode": result.returncode})
        (out / "partial_result.json").write_text(json.dumps(report, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError("Command failed; see " + str(out / log_name))
        return (out / log_name).read_text(encoding="utf-8", errors="replace")

    rtl = [here / "winograd_int8_factor32.sv", here / "winograd_int8_dot64.sv"]
    simulation = out / "sim.vvp"
    run([args.iverilog, "-g2012", "-Wall", "-s", "tb_winograd_int8", "-o", simulation,
         *[path.relative_to(root).as_posix() for path in rtl], (here / "tb_winograd_int8.sv").relative_to(root).as_posix()], "compile.log")
    for seed in args.seeds:
        output = run([args.vvp, simulation, f"+SEED={seed}"], f"seed_{seed}.log")
        match = re.search(r"^PASS (.+)$", output, re.M)
        if not match:
            raise RuntimeError("No PASS marker for seed " + str(seed))
        values = {key: int(value) for key, value in re.findall(r"(\w+)=(\d+)", match.group(1))}
        if values["cases"] != 2910 or values["response_latency"] != 33 or values["frame_ii"] != 32 or values["resets"] != 10:
            raise RuntimeError("Coverage/timing result mismatch")
        if min(values["stall_factor"], values["stall_dot"], values["inputwait_factor"], values["inputwait_dot"]) <= 0:
            raise RuntimeError("Missing backpressure coverage")
        report["simulations"].append({"seed": seed, "passed": True, **values})
        print("PASS seed", seed, values, flush=True)
    for label, top, path, extra in [("factor", "winograd_int8_factor32", rtl[0], []),
                                    ("dot16", "winograd_int8_dot64", rtl[1], []),
                                    ("dot48", "winograd_int8_dot64", rtl[1], ["-GBIAS_W=48"])]:
        if os.name == "nt":
            command = ["wsl.exe", "-d", args.wsl_distro, "--", "verilator", "--lint-only", "-Wall", "--top-module", top, *extra, linux_path(path)]
        else:
            command = ["verilator", "--lint-only", "-Wall", "--top-module", top, *extra, path]
        output = run(command, "lint_" + label + ".log")
        if "%Warning" in output or "%Error" in output:
            raise RuntimeError("Unexpected unwaived RTL lint diagnostic")
        report["lint"].append({"configuration": label, "passed": True, "warnings": 0, "errors": 0})
    if before != {path.name: sha(path) for path in sources}:
        raise RuntimeError("Source changed during verification")
    report["completed"] = True
    report["completed_utc"] = datetime.now(timezone.utc).isoformat()
    report["logs_sha256"] = {path.name: sha(path) for path in out.glob("*.log")}
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print("RESULT", out / "result.json", flush=True)


if __name__ == "__main__":
    main()
