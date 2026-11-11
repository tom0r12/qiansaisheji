"""Measure one candidate using F's complete E203 test fixture and input images."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from weight_monitor import instrument

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from run_soc_performance import summarize

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("candidate", help="directory containing qingyu_fio.sv and optional accelerator/driver")
parser.add_argument("output", help="isolated build directory under qingyu")
parser.add_argument("--define", action="append", default=[])
parser.add_argument("--check-weight", action="store_true", help="check 512 descriptors and 8192 packed weight transfers per layer")
parser.add_argument("--weight-commands", type=int, default=512)
args = parser.parse_args()
candidate = (ROOT / args.candidate).resolve()
work = (ROOT / args.output).resolve()
work.mkdir(parents=True, exist_ok=True)
reference = ROOT / "build/dual_row_study"
images = ROOT / "reports/soc_performance_20261104_224417"
tools = ROOT / "tools/verilator/mingw64"
env = dict(os.environ, VERILATOR_ROOT=(tools / "share/verilator").as_posix())
env["PATH"] = os.pathsep.join((str(tools / "bin"), "D:/Git/usr/bin", env["PATH"]))

def run(command, log, cwd=ROOT):
    with log.open("w") as out:
        status = subprocess.run(command, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT).returncode
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
files = (reference / "sources.f").read_text().splitlines()
if args.check_weight:
    tb = "tb/tb_qingyu_soc_performance.sv"
    monitor = work / "weight_perf.sv"
    monitor.write_bytes(instrument((ROOT / tb).read_bytes()).replace(b"fixture.dut.u_fio.icb_cmd_addr==32'hf0000038", b"(fixture.dut.u_fio.icb_cmd_addr==32'hf0000038 || fixture.dut.u_fio.icb_cmd_addr==32'hf0000084)").replace(b"weight_commands!=512", ("weight_commands!=%d"%args.weight_commands).encode()))
    files[files.index(tb)] = monitor.relative_to(ROOT).as_posix()
for old, new in [("build/dual_row_study/qingyu_accel.sv", accel), ("rtl/qingyu_fio.sv", fio)]:
    files[files.index(old)] = new.relative_to(ROOT).as_posix()
filelist = work / "sources.f"
filelist.write_text("\n".join(files) + "\n")
obj = work / "obj"
obj.mkdir(exist_ok=True)
name = "Vg16"
includes = ["-Ivendor/e203_hbirdv2/rtl/e203/" + p for p in ("core", "perips", "perips/apb_i2c")]
run([tools / "bin/verilator_bin.exe", "--cc", "--main", "--exe", "--timing", "--autoflush",
     "--timescale-override", "1ns/1ps", "--top-module", "tb_qingyu_soc_performance",
     "--prefix", name, "--Mdir", obj.relative_to(ROOT).as_posix(), "-Wno-fatal",
     "-DDISABLE_SV_ASSERTION=1", *["-D" + x for x in args.define], *includes,
     "-CFLAGS", "-std=gnu++20 -O1", "--output-split", "10000", "-f", filelist], work / "generate.log")
run(["D:/mingw/mingw64/bin/mingw32-make.exe", "-C", obj, "-f", name + ".mk", "-j6",
     "CXX=" + (tools / "bin/g++.exe").as_posix(), "LINK=" + (tools / "bin/g++.exe").as_posix(),
     "AR=" + (tools / "bin/ar.exe").as_posix(), "PYTHON3=" + Path(sys.executable).as_posix(),
     "PERL=D:/Git/usr/bin/perl.exe", "VERILATOR_ROOT=" + env["VERILATOR_ROOT"]], work / "make.log")
for dll in ("libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll"):
    shutil.copyfile(tools / "bin" / dll, obj / dll)

def measure(layer):
    layer_name = f"layer{layer:02d}"
    out = work / layer_name
    out.mkdir(exist_ok=True)
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
    fw.write_bytes("".join(f"{int.from_bytes(raw[j:j+8], 'little'):016x}\n" for j in range(0, len(raw), 8)).encode())
    src = images / layer_name
    run([obj / (name + ".exe"), "+FIRMWARE=" + fw.name, "+SHARED=" + (src / "shared.hex").as_posix(),
         "+EXPECTED=" + (src / "expected.hex").as_posix()], out / "sim.log", out)
    result = summarize((out / "sim.log").read_text(), layer)
    print(layer_name, result["cycles"], flush=True)
    return result

with concurrent.futures.ThreadPoolExecutor(4) as pool:
    layers = list(pool.map(measure, range(12)))
avg = sum(row["cycles"] for row in layers) / len(layers)
result = dict(layers=layers, avg_cycles=avg, assumed_mhz=150, avg_ms=avg / 150000,
              tasks_per_second=150000000 / avg, outputs=sum(x["outputs"] for x in layers),
              sha256={p.relative_to(ROOT).as_posix(): digest(p) for p in [fio, accel, driver, main, filelist]},
              defines=args.define)
(work / "result.json").write_text(json.dumps(result, indent=2))
print(f"{result['avg_ms']:.6f} ms   {result['tasks_per_second']:.4f} tasks/s   {result['outputs']} outputs")
