"""Measure the outfifo (deep output read-ahead FIFO) candidate on an isolated build.

Same fixture as experiments/h1500v/wbank2/measure_wbank2.py: the complete E203
SoC test harness, the frozen 12-layer input images and the independent
304,128-output checker.  The testbench additionally reports output write-back
occupancy counters (QINGYU_COPY) so the copy engine's cycles/word can be read
straight out of the log.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from run_soc_performance import summarize

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("candidate", nargs="?", default="experiments/h1500v/outfifo/rtl",
                    help="directory with qingyu_accel.sv/qingyu_fio.sv/qingyu_accel.c/soc_perf_main.c")
parser.add_argument("output", nargs="?", default="build/outfifo", help="isolated build directory")
parser.add_argument("--layers", default="all", help="all or comma separated layer ids")
parser.add_argument("--define", action="append", default=[])
parser.add_argument("--tb", default="experiments/h1500v/outfifo/tb_outfifo.sv",
                    help="instrumented testbench (relative to the project root)")
parser.add_argument("--name", default="Voutfifo", help="Verilator prefix / output executable name")
parser.add_argument("--skip-build", action="store_true")
parser.add_argument("--skip-sim", action="store_true", help="reuse existing per-layer sim.log")
args = parser.parse_args()

candidate = (ROOT / args.candidate).resolve()
work = (ROOT / args.output).resolve()
work.mkdir(parents=True, exist_ok=True)
reference = ROOT / "build/dual_row_study"
images = ROOT / "reports/soc_performance_20261104_224417"
tools = ROOT / "tools/verilator/mingw64"
env = dict(os.environ, VERILATOR_ROOT=(tools / "share/verilator").as_posix())
env["PATH"] = os.pathsep.join((str(tools / "bin"), "D:/Git/usr/bin", env["PATH"]))
layers = list(range(12)) if args.layers == "all" else [int(x) for x in args.layers.split(",")]


def run(command, log, cwd=ROOT):
    with log.open("w") as out:
        status = subprocess.run([str(c) for c in command], cwd=cwd, env=env,
                                stdout=out, stderr=subprocess.STDOUT).returncode
    if status:
        raise RuntimeError(str(log) + "\n" + log.read_text(errors="replace")[-2500:])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


accel = candidate / "qingyu_accel.sv"
if not accel.is_file():
    accel = reference / accel.name
driver = candidate / "qingyu_accel.c"
if not driver.is_file():
    driver = ROOT / "sw/qingyu_accel.c"
main = candidate / "soc_perf_main.c"
if not main.is_file():
    main = ROOT / "sw/soc_perf_main.c"
fio = candidate / "qingyu_fio.sv"
if not fio.is_file():
    fio = ROOT / "rtl/qingyu_fio.sv"

files = (reference / "sources.f").read_text().splitlines()
tb = args.tb
for old, new in [("build/dual_row_study/qingyu_accel.sv", accel), ("rtl/qingyu_fio.sv", fio),
                 ("tb/tb_qingyu_soc_performance.sv", (ROOT / tb).resolve())]:
    files[files.index(old)] = new.relative_to(ROOT).as_posix()
filelist = work / "sources.f"
filelist.write_text("\n".join(files) + "\n")
hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in (accel, fio, driver, main, filelist)}
rtl_hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in (accel, fio, filelist)}
manifest = work / "build_manifest.json"
obj = work / "obj"
obj.mkdir(exist_ok=True)
name = args.name
binary = obj / (name + ".exe")
if args.skip_build:
    if not binary.is_file() or json.loads(manifest.read_text())["rtl_sha256"] != rtl_hashes:
        raise RuntimeError("RTL sources changed; omit --skip-build")
else:
    includes = ["-Ivendor/e203_hbirdv2/rtl/e203/" + p for p in ("core", "perips", "perips/apb_i2c")]
    run([tools / "bin/verilator_bin.exe", "--cc", "--main", "--exe", "--timing", "--autoflush",
         "--timescale-override", "1ns/1ps", "--top-module", "tb_qingyu_soc_performance",
         "--prefix", name, "--Mdir", obj.relative_to(ROOT).as_posix(), "-Wno-fatal",
         "-DDISABLE_SV_ASSERTION=1", *["-D" + x for x in args.define], *includes,
         "-CFLAGS", "-std=gnu++20 -O1", "--output-split", "10000", "-f", filelist],
        work / "generate.log")
    run(["D:/mingw/mingw64/bin/mingw32-make.exe", "-C", obj.relative_to(ROOT).as_posix(),
         "-f", name + ".mk", "-j6",
         "CXX=" + (tools / "bin/g++.exe").as_posix(), "LINK=" + (tools / "bin/g++.exe").as_posix(),
         "AR=" + (tools / "bin/ar.exe").as_posix(), "PYTHON3=" + Path(sys.executable).as_posix(),
         "PERL=D:/Git/usr/bin/perl.exe", "VERILATOR_ROOT=" + env["VERILATOR_ROOT"]],
        work / "make.log")
    for dll in ("libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll"):
        shutil.copyfile(tools / "bin" / dll, obj / dll)
    manifest.write_text(json.dumps({"sha256": hashes, "rtl_sha256": rtl_hashes}, indent=2))


def measure(layer):
    layer_name = f"layer{layer:02d}"
    out = work / layer_name
    out.mkdir(exist_ok=True)
    if not args.skip_sim:
        cc = "C:/Efinity/efinity-riscv-ide-2025.1/toolchain/bin/riscv-none-embed-"
        run([cc + "gcc.exe", f"-DQINGYU_TEST_LAYER={layer}", "-DQINGYU_BLOCK_COPY", "-DQINGYU_READ_AHEAD",
             "-DQINGYU_FAST_TASK", "-DQINGYU_DOUBLE_BUFFER", *["-D" + x for x in args.define],
             "-march=rv32imac", "-mabi=ilp32", "-ffreestanding", "-fno-builtin", "-msmall-data-limit=0",
             "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra", "-Werror", "-nostdlib",
             "-nostartfiles", "-O3", "-flto", "-funroll-loops", "-Isw", "-Tsw/linker.ld", "-Wl,--gc-sections",
             "sw/startup.S", main, driver, "sw/runtime.c", "-lgcc", "-o", out / "fw.elf"], out / "cc.log")
        run([cc + "objcopy.exe", "-O", "binary", out / "fw.elf", out / "fw.bin"], out / "objcopy.log")
        raw = (out / "fw.bin").read_bytes()
        if len(raw) > 65536:
            raise ValueError("firmware exceeds ITCM")
        raw = raw.ljust(65536, b"\0")
        fw = out / "firmware64.hex"
        fw.write_bytes("".join(f"{int.from_bytes(raw[j:j+8], 'little'):016x}\n"
                               for j in range(0, len(raw), 8)).encode())
        src = images / layer_name
        run([binary, "+FIRMWARE=" + fw.name, "+SHARED=" + (src / "shared.hex").as_posix(),
             "+EXPECTED=" + (src / "expected.hex").as_posix()], out / "sim.log", out)
    text = (out / "sim.log").read_text(errors="replace")
    result = summarize(text, layer)
    copy = {}
    for line in text.splitlines():
        if line.startswith("QINGYU_COPY") or line.startswith("QINGYU_OUT"):
            copy.update({k: int(v) for k, v in (t.partition("=")[::2] for t in line.split()[1:]) if v.isdigit()})
    result["copy"] = copy
    print(layer_name, result["cycles"], copy.get("copy_cycles"), copy.get("pops"), flush=True)
    return result


with concurrent.futures.ThreadPoolExecutor(4) as pool:
    rows = list(pool.map(measure, layers))
avg = sum(row["cycles"] for row in rows) / len(rows)
copies = [row["copy"] for row in rows if row.get("copy")]
result = dict(layers=rows, avg_cycles=avg, assumed_mhz=150, avg_ms=avg / 150000,
              tasks_per_second=150000000 / avg, outputs=sum(x["outputs"] for x in rows),
              sha256=hashes, defines=args.define)
if copies:
    keys = sorted(copies[0])
    result["copy_mean"] = {k: sum(c[k] for c in copies) / len(copies) for k in keys}
    result["copy_total"] = {k: sum(c[k] for c in copies) for k in keys}
(work / "result.json").write_text(json.dumps(result, indent=2))
print(f"{result['avg_ms']:.6f} ms   {result['tasks_per_second']:.4f} tasks/s   {result['outputs']} outputs")
if copies:
    m = result["copy_mean"]
    print("copy: cycles/layer=%.0f pops=%.0f batches=%.0f wr_cmd=%.0f starve=%.0f chain=%.0f "
          "issue=%.0f fifo_mean=%.2f hist=%s" % (
              m["copy_cycles"], m["pops"], m["batches"], m["wr_cmd"], m["starve"], m["chain"],
              m["issue_copy"], m["fifo_sum"] / max(m["copy_cycles"], 1),
              [m.get("hist%d" % i, 0) for i in range(5)]))
