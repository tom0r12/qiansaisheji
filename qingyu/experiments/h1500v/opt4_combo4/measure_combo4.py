"""Measure opt4 candidates (opt3 + interleaved staging / INT16 output).

Uses the opt4 testbench copy: instead of requiring every staging copy to finish
before the first live read, it checks per word that each live word was copied
in this window before any engine reads it. Weight checking is always on.

Same fixture as experiments/h1500v/wbank2/measure_wbank2.py: the complete E203 SoC
test harness, the frozen 12-layer input images and the independent 304,128-output
checker.  The candidate directory defaults to this experiment.
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
sys.path.insert(0, str(ROOT / "experiments/g16"))
from run_soc_performance import summarize
from weight_monitor import instrument

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("candidate", nargs="?", default="experiments/h1500v/opt4_combo4/rtl",
                    help="directory with qingyu_accel.sv/qingyu_fio.sv/qingyu_accel.c/soc_perf_main.c")
parser.add_argument("output", nargs="?", default="build/opt4_combo4", help="isolated build directory")
parser.add_argument("--layers", default="all", help="all or comma separated layer ids")
parser.add_argument("--define", action="append", default=[])
parser.add_argument("--images", default="reports/soc_performance_q16", help="INT16 task images (make_q16_images.py)")
parser.add_argument("--check-weight", action="store_true", default=True)
parser.add_argument("--trace-io", action="store_true", help="extra FIO occupancy counters in the monitor")
parser.add_argument("--weight-commands", type=int, default=16)
parser.add_argument("--main", default=None, help="override soc_perf_main.c (firmware-only variant)")
parser.add_argument("--skip-build", action="store_true")
args = parser.parse_args()
if "QINGYU_OUT16" not in args.define:
    args.define.append("QINGYU_OUT16")

candidate = (ROOT / args.candidate).resolve()
work = (ROOT / args.output).resolve()
work.mkdir(parents=True, exist_ok=True)
reference = ROOT / "build/dual_row_study"
images = ROOT / args.images
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
if args.main:
    main = (ROOT / args.main).resolve()
if not main.is_file():
    main = ROOT / "sw/soc_perf_main.c"
fio = candidate / "qingyu_fio.sv"
if not fio.is_file():
    fio = ROOT / "rtl/qingyu_fio.sv"

files = (reference / "sources.f").read_text().splitlines()
if args.check_weight:
    tb = "tb/tb_qingyu_soc_performance.sv"
    monitor = work / "weight_perf.sv"
    monitor.write_bytes(instrument((Path(__file__).resolve().parent / "tb/tb_qingyu_soc_performance.sv").read_bytes()).replace(
        b"fixture.dut.u_fio.icb_cmd_addr==32'hf0000038",
        b"(fixture.dut.u_fio.icb_cmd_addr==32'hf0000038 || fixture.dut.u_fio.icb_cmd_addr==32'hf0000084)").replace(
        b"weight_commands!=512", ("weight_commands!=%d" % args.weight_commands).encode()).replace(
        # count accepted commands only (opt4 holds a weight command until its pair is staged)
        b"fixture.dut.u_fio.take_block && fixture.dut.u_fio.weight_cmd)",
        b"fixture.dut.u_fio.take_block && fixture.dut.u_fio.weight_cmd && fixture.dut.u_fio.icb_cmd_ready)"))
    if args.trace_io:
        text = monitor.read_bytes()
        text = text.replace(
            b" integer weight_commands=0, weight_reads=0, weight_writes=0;",
            b" integer weight_commands=0, weight_reads=0, weight_writes=0;\n"
            b" integer wl_busy_cycles=0, wl_idle_cycles=0, busy_run=0;\n"
            b" integer meta_copies=0, meta_words=0, meta_reads=0;")
        text = text.replace(
            b"  if (active) begin\n",
            b"  if (active) begin\n"
            b"   if (fixture.dut.u_fio.wl_busy) wl_busy_cycles++;\n"
            b"   if (fixture.dut.u_fio.wl_busy && !fixture.dut.u_fio.u_accel.busy) wl_idle_cycles++;\n"
            b"   if (fixture.dut.u_fio.u_accel.busy && !fixture.dut.u_fio.u_accel.producer_stall) busy_run++;\n"
            b"   if (fixture.dut.u_fio.meta_busy) meta_copies++;\n"
            b"   if (fixture.dut.u_fio.meta_wr_en) meta_words++;\n"
            b"   if (fixture.dut.u_fio.meta_rd_req) meta_reads++;\n",
            1)
        text = text.replace(
            b'     $display("QINGYU_PERF_END',
            b'     $display("QINGYU_W2 wl_busy_cycles=%0d wl_idle_cycles=%0d busy_run=%0d meta_copies=%0d meta_words=%0d meta_reads=%0d",'
            b'wl_busy_cycles,wl_idle_cycles,busy_run,meta_copies,meta_words,meta_reads);\n'
            b'     $display("QINGYU_PERF_END')
        monitor.write_bytes(text)
    files[files.index(tb)] = monitor.relative_to(ROOT).as_posix()
for old, new in [("build/dual_row_study/qingyu_accel.sv", accel), ("rtl/qingyu_fio.sv", fio),
                 ("tb/tb_qingyu_soc.sv", Path(__file__).resolve().parent / "tb/tb_qingyu_soc.sv")]:
    files[files.index(old)] = new.relative_to(ROOT).as_posix()
filelist = work / "sources.f"
filelist.write_text("\n".join(files) + "\n")
hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in (accel, fio, driver, main, filelist)}
rtl_hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in (accel, fio, filelist)}
manifest = work / "build_manifest.json"
obj = work / "obj"
obj.mkdir(exist_ok=True)
name = "Vopt4c4"
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
    cc = "C:/Efinity/efinity-riscv-ide-2025.1/toolchain/bin/riscv-none-embed-"
    run([cc + "gcc.exe", f"-DQINGYU_TEST_LAYER={layer}", "-DQINGYU_BLOCK_COPY", "-DQINGYU_READ_AHEAD",
         "-DQINGYU_FAST_TASK", "-DQINGYU_DOUBLE_BUFFER", *["-D" + x for x in args.define],
         "-march=rv32imac", "-mabi=ilp32", "-ffreestanding", "-fno-builtin", "-msmall-data-limit=0",
         "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra", "-Werror", "-nostdlib",
         "-nostartfiles", "-O3", "-flto", "-funroll-loops", "-I" + candidate.as_posix(), "-Isw", "-Tsw/linker.ld", "-Wl,--gc-sections",
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
    result = summarize((out / "sim.log").read_text(errors="replace"), layer)
    print(layer_name, result["cycles"], flush=True)
    return result


with concurrent.futures.ThreadPoolExecutor(4) as pool:
    rows = list(pool.map(measure, layers))
avg = sum(row["cycles"] for row in rows) / len(rows)
result = dict(layers=rows, avg_cycles=avg, assumed_mhz=150, avg_ms=avg / 150000,
              tasks_per_second=150000000 / avg, outputs=sum(x["outputs"] for x in rows),
              sha256=hashes, defines=args.define)
(work / "result.json").write_text(json.dumps(result, indent=2))
print(f"{result['avg_ms']:.6f} ms   {result['tasks_per_second']:.4f} tasks/s   {result['outputs']} outputs")
