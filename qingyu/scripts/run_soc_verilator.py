"""Compile and run the existing full E203 SoC testbench using native Verilator.

The same firmware, shared-memory image and element-by-element RTL checker as
the Icarus flow are used. --timing retains the testbench and model delays.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def execute(command, log_path, environment, timeout):
    start = time.monotonic()
    with log_path.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen([str(value) for value in command], cwd=ROOT,
                                   env=environment, stdout=stream, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            print(f"TIMEOUT after {timeout}s; see {log_path}", flush=True)
            raise SystemExit(124)
    seconds = time.monotonic() - start
    print(f"{log_path.stem}: exit={code}, seconds={seconds:.2f}", flush=True)
    if code:
        print(log_path.read_text(encoding="utf-8", errors="replace")[-7000:])
        raise SystemExit(code)
    return seconds


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_rtl(args, environment, tools, verilator, cxx, make, build):
    """Reuse the real directed/full-matrix SV checker without the CPU."""
    source_paths = [ROOT / "rtl/qingyu_sram16.sv", ROOT / "rtl/qingyu_accel.sv",
                    ROOT / "tb/tb_qingyu_accel.sv"]
    hashes = {path.relative_to(ROOT).as_posix(): sha256(path) for path in source_paths}
    model_dir = build / "verilator_accel"
    model_dir.mkdir(exist_ok=True)
    model_name = "Vqingyu_accel_native"
    if not args.skip_build:
        generate = [verilator, "--cc", "--main", "--exe", "--timing", "--autoflush",
                    "--timescale-override", "1ns/1ps", "--top-module", "tb_qingyu_accel",
                    "--prefix", model_name, "--Mdir", "build/verilator_accel",
                    "-Wno-fatal", "-CFLAGS", "-std=gnu++20 -O1", "--output-split", "10000"]
        generate += [path.relative_to(ROOT).as_posix() for path in source_paths]
        execute(generate, build / "verilator_rtl_generate.log", environment, max(300, args.timeout))
        command = [make, "-C", "build/verilator_accel", "-f", model_name + ".mk",
                   "-j", str(args.jobs), "CXX=" + cxx.as_posix(), "LINK=" + cxx.as_posix(),
                   "AR=" + (tools / "bin/ar.exe").as_posix(),
                   "PYTHON3=" + Path(sys.executable).as_posix(), "PERL=D:/Git/usr/bin/perl.exe",
                   "VERILATOR_ROOT=" + environment["VERILATOR_ROOT"]]
        execute(command, build / "verilator_rtl_make.log", environment, max(300, args.timeout))
        (model_dir / "build_manifest.json").write_text(json.dumps({"rtl_sha256": hashes,
            "timing_controls_enabled": True, "command": [str(x) for x in generate]}, indent=2) + "\n")
    else:
        manifest = json.loads((model_dir / "build_manifest.json").read_text())
        if manifest["rtl_sha256"] != hashes:
            raise SystemExit("Accelerator RTL/TB changed; rebuild native RTL checker")
    if args.build_only:
        return
    binary = model_dir / (model_name + ".exe")
    if not binary.is_file():
        binary = model_dir / model_name
    if not binary.is_file():
        raise SystemExit("Native accelerator checker executable missing")
    vector_root = (ROOT / args.vectors).resolve()
    layers = list(range(12)) if args.all_layers else [args.layer]
    directories = [vector_root / f"layer{layer:02d}" for layer in layers]
    for directory in directories:
        for filename in ("x_words.hex", "w_tile_words.hex", "meta_words.hex", "y_tile_words.hex"):
            if not (directory / filename).is_file():
                raise SystemExit(f"Missing vector input: {directory / filename}")
    report = {"test": "native full-size accelerator RTL vector regression", "passed": False,
              "vector_root": str(vector_root), "rtl_sha256": hashes, "layers": [],
              "timing_controls_enabled": True,
              "limits": ["functional SRAM models", "not official evaluation harness",
                         "vector provenance follows source manifests", "not a timing or power signoff"]}
    report_path = ROOT / "reports/rtl_verilator_result.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    for layer, directory in zip(layers, directories):
        vector_hashes = {filename: sha256(directory / filename) for filename in
                         ("x_words.hex", "w_tile_words.hex", "meta_words.hex", "y_tile_words.hex")}
        log = build / f"run_rtl_verilator_layer{layer:02d}.log"
        seconds = execute([binary, "+VECTORS=" + directory.as_posix()], log, environment, args.timeout)
        text = log.read_text(encoding="utf-8", errors="replace")
        if "PASS external full matrix" not in text or "PASS qingyu_accel directed tests" not in text:
            raise SystemExit(f"Layer {layer} ended without both checker PASS markers")
        if vector_hashes != {filename: sha256(directory / filename) for filename in vector_hashes}:
            raise SystemExit(f"Layer {layer} vectors changed during the run; repeat with frozen files")
        report["layers"].append({"layer": layer, "passed": True, "seconds": seconds,
                                 "outputs_checked": 25344, "log": str(log.relative_to(ROOT)),
                                 "vector_sha256": vector_hashes})
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    report["passed"] = True
    report["total_outputs_checked"] = 25344 * len(layers)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS native RTL layers={len(layers)}, outputs={report['total_outputs_checked']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", type=int, default=0)
    parser.add_argument("--vectors", default="tb/vectors")
    parser.add_argument("--gcc", help="RISC-V firmware GCC, forwarded to run_soc.py")
    parser.add_argument("--skip-prepare", action="store_true",
                        help="reuse matching existing firmware/shared.hex/file list")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=300,
                        help="runtime timeout; build stages allow at least 300s")
    parser.add_argument("--verilator", type=Path)
    parser.add_argument("--cxx", type=Path)
    parser.add_argument("--make", type=Path)
    parser.add_argument("--rtl-only", action="store_true",
                        help="run full-size standalone accelerator SV checker")
    parser.add_argument("--all-layers", action="store_true",
                        help="with --rtl-only, check layer00 through layer11")
    args = parser.parse_args()
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    tools = ROOT / "tools/verilator/mingw64"
    verilator = args.verilator or tools / "bin/verilator_bin.exe"
    cxx = args.cxx or tools / "bin/g++.exe"
    make = args.make or Path(r"D:\mingw\mingw64\bin\mingw32-make.exe")
    for executable in (verilator, cxx, make):
        if not executable.is_file():
            raise SystemExit(f"Required native tool not found: {executable}")
    environment = os.environ.copy()
    environment["VERILATOR_ROOT"] = (tools / "share/verilator").as_posix()
    environment["PATH"] = str(tools / "bin") + os.pathsep + r"D:\Git\usr\bin" + os.pathsep + environment.get("PATH", "")
    if not 0 <= args.layer < 12 or args.jobs < 1:
        raise SystemExit("layer must be 0..11 and jobs must be positive")
    if args.rtl_only:
        return run_rtl(args, environment, tools, verilator, cxx, make, build)
    if args.all_layers:
        raise SystemExit("--all-layers currently requires --rtl-only")
    if not args.skip_prepare:
        prepare = [sys.executable, ROOT / "scripts/run_soc.py", "--build-only",
                   "--layer", str(args.layer), "--vectors", args.vectors]
        if args.gcc:
            prepare += ["--gcc", args.gcc]
        execute(prepare, build / "verilator_prepare.log", environment, max(300, args.timeout))
    files = build / "soc_files.f"
    if not files.is_file():
        raise SystemExit("Missing build/soc_files.f; run preparation first")
    model_dir = build / "verilator_soc"
    model_dir.mkdir(exist_ok=True)
    model_name = "Vqingyu_soc"
    native_model = model_dir / (model_name + ".exe")
    source_paths = [ROOT / line.strip() for line in files.read_text().splitlines() if line.strip()]
    rtl_hashes = {path.relative_to(ROOT).as_posix(): sha256(path) for path in source_paths}
    if not args.skip_build:
        execute([verilator, "--version"], build / "verilator_version.log", environment, 30)
        generate = [verilator, "--cc", "--main", "--exe", "--timing", "--autoflush",
                    "--timescale-override", "1ns/1ps", "--top-module", "tb_qingyu_soc",
                    "--prefix", model_name, "--Mdir", "build/verilator_soc",
                    "-Wno-fatal", "-DDISABLE_SV_ASSERTION=1",
                    "-Ivendor/e203_hbirdv2/rtl/e203/core",
                    "-Ivendor/e203_hbirdv2/rtl/e203/perips",
                    "-Ivendor/e203_hbirdv2/rtl/e203/perips/apb_i2c",
                    "-CFLAGS", "-std=gnu++20 -O1", "--output-split", "10000",
                    "-f", "build/soc_files.f"]
        execute(generate, build / "verilator_generate.log", environment, max(300, args.timeout))
        make_command = [make, "-C", "build/verilator_soc", "-f", model_name + ".mk",
                        "-j", str(args.jobs), "CXX=" + cxx.as_posix(),
                        "LINK=" + cxx.as_posix(), "AR=" + (tools / "bin/ar.exe").as_posix(),
                        "PYTHON3=" + Path(sys.executable).as_posix(),
                        "PERL=" + r"D:/Git/usr/bin/perl.exe",
                        "VERILATOR_ROOT=" + environment["VERILATOR_ROOT"]]
        execute(make_command, build / "verilator_make.log", environment, max(300, args.timeout))
        (model_dir / "build_manifest.json").write_text(json.dumps({
            "rtl_sha256": rtl_hashes,
            "verilator": (build / "verilator_version.log").read_text().strip(),
            "timing_controls_enabled": True, "command": [str(x) for x in generate],
        }, indent=2) + "\n")
    else:
        manifest_path = model_dir / "build_manifest.json"
        if not manifest_path.is_file():
            raise SystemExit("Missing model build manifest; compile the native model first")
        manifest = json.loads(manifest_path.read_text())
        if manifest["rtl_sha256"] != rtl_hashes:
            raise SystemExit("RTL changed since the native model was built; rebuild required")
    if args.build_only:
        return
    if not native_model.is_file():
        # Some native make versions omit .exe from the target pathname.
        alternative = model_dir / model_name
        if not alternative.is_file():
            raise SystemExit("Native model executable not found after build")
        native_model = alternative
    vector_root = (ROOT / args.vectors).resolve()
    expected = vector_root / f"layer{args.layer:02d}/y_row_words.hex"
    inputs = [build / "firmware64.hex", build / "shared.hex", expected]
    input_hashes = {str(path): sha256(path) for path in inputs}
    log = build / "run_soc_verilator.log"
    seconds = execute([native_model, "+FIRMWARE=build/firmware64.hex",
                       "+SHARED=build/shared.hex", "+EXPECTED=" + expected.as_posix()],
                      log, environment, args.timeout)
    text = log.read_text(encoding="utf-8", errors="replace")
    if "PASS real E203" not in text:
        raise SystemExit("Native simulation ended without the SoC output checker PASS marker")
    if input_hashes != {str(path): sha256(path) for path in inputs}:
        raise SystemExit("SoC input images changed during execution; repeat with frozen files")
    report = {"test": "full E203 SoC firmware integration with native Verilator",
              "passed": True, "layer": args.layer, "vectors": str(vector_root),
              "outputs_checked": 99 * 256, "seconds": seconds,
              "timing_controls_enabled": True, "log": str(log.relative_to(ROOT)),
              "rtl_sha256": rtl_hashes, "input_sha256": input_hashes,
              "limits": ["functional SRAM models", "not official evaluation harness",
                         "no formal timing/power result", "data provenance follows vector manifest"]}
    (ROOT / "reports/soc_verilator_result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(text[-2000:])


if __name__ == "__main__":
    main()
