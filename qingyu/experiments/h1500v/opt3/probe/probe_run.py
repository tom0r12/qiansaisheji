"""Run CPU-access-cost probe firmware variants against the existing wbank2 model."""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / "build/opt3/ccprobe"
IMAGES = ROOT / "reports/soc_performance_20261104_224417/layer01"
EXE = ROOT / "build/wbank2/obj/Vwbank2.exe"
CC = "C:/Efinity/efinity-riscv-ide-2025.1/toolchain/bin/riscv-none-embed-"
MAIN = ROOT / "experiments/h1500v/opt3/probe/probe_main.c"
DRIVER = ROOT / "experiments/h1500v/wbank2/rtl/qingyu_accel.c"
LAYER = int(sys.argv[1]) if len(sys.argv) > 1 else 1
MODES = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else [0, 1, 2, 3, 4, 8]

WORK.mkdir(parents=True, exist_ok=True)
rows = {}
for mode in MODES:
    out = WORK / f"m{mode}"
    out.mkdir(exist_ok=True)
    def run(cmd, log):
        with (out / log).open("w") as f:
            p = subprocess.run([str(c) for c in cmd], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
        if p.returncode:
            raise RuntimeError((out / log).read_text(errors="replace")[-1500:])
    run([CC + "gcc.exe", f"-DQINGYU_TEST_LAYER={LAYER}", f"-DPROBE_MODE={mode}",
         "-DQINGYU_BLOCK_COPY", "-DQINGYU_READ_AHEAD", "-DQINGYU_FAST_TASK", "-DQINGYU_DOUBLE_BUFFER",
         "-march=rv32imac", "-mabi=ilp32", "-ffreestanding", "-fno-builtin", "-msmall-data-limit=0",
         "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra", "-Werror", "-nostdlib",
         "-nostartfiles", "-O3", "-flto", "-funroll-loops", "-Isw", "-Tsw/linker.ld", "-Wl,--gc-sections",
         "sw/startup.S", MAIN, DRIVER, "sw/runtime.c", "-lgcc", "-o", out / "fw.elf"], "cc.log")
    run([CC + "objcopy.exe", "-O", "binary", out / "fw.elf", out / "fw.bin"], "objcopy.log")
    raw = (out / "fw.bin").read_bytes().ljust(65536, b"\0")
    (out / "firmware64.hex").write_bytes("".join(
        f"{int.from_bytes(raw[j:j+8], 'little'):016x}\n" for j in range(0, len(raw), 8)).encode())
    p = subprocess.run([str(EXE), "+FIRMWARE=firmware64.hex", "+SHARED=" + (IMAGES / "shared.hex").as_posix(),
                        "+EXPECTED=" + (IMAGES / "expected.hex").as_posix()],
                       cwd=out, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    (out / "sim.log").write_text(p.stdout, encoding="utf-8")
    if p.returncode:
        raise RuntimeError(f"mode {mode} failed\n" + p.stdout[-1800:])
    fw = re.search(r"QINGYU_PERF_FIRMWARE outer_cycles=(\d+) driver_cycles=(\d+) compute_cycles=(\d+)", p.stdout)
    rows[mode] = dict(outer=int(fw[1]), driver=int(fw[2]), probe=int(fw[3]))
    print(f"mode {mode}: outer={rows[mode]['outer']} driver={rows[mode]['driver']} probe={rows[mode]['probe']}", flush=True)
base = rows[0]["outer"]
for mode in MODES:
    print(f"mode {mode}: +{rows[mode]['outer'] - base} outer cycles, probe_self={rows[mode]['probe']}")
