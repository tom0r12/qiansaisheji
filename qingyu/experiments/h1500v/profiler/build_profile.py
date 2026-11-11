"""Build the h1500v SoC sim with a profiling testbench and dump the 43k-cycle breakdown."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "build/h1500v_poll"
WORK = ROOT / "build/profile"
TB_OUT = ROOT / "experiments/h1500v/profiler/tb_profile.sv"
IMAGES = ROOT / "reports/soc_performance_20261104_224417"
TOOLS = ROOT / "tools/verilator/mingw64"

DECL = """`ifdef QINGYU_PROFILE
 integer st_cnt[0:7];
 integer bus_cnt[0:5];
 integer cmd_fires=0, cmd_gap_total=0, last_cmd_tick=-1;
 integer mem_cmd_cycles=0, load_nocmd=0, live_nocmd=0;
 integer pi;
 initial begin
  for (pi=0;pi<8;pi=pi+1) st_cnt[pi]=0;
  for (pi=0;pi<6;pi=pi+1) bus_cnt[pi]=0;
 end
`endif
"""

COUNT = """`ifdef QINGYU_PROFILE
   st_cnt[`DBACC.engine_state] = st_cnt[`DBACC.engine_state] + 1;
   bus_cnt[`DBACC.bus_state] = bus_cnt[`DBACC.bus_state] + 1;
   if (`DBACC.command_fire) begin
    cmd_fires = cmd_fires + 1;
    if (last_cmd_tick >= 0) cmd_gap_total = cmd_gap_total + (ticks - last_cmd_tick);
    last_cmd_tick = ticks;
   end
   if (`MEM.icb_cmd_valid && `MEM.icb_cmd_ready) mem_cmd_cycles = mem_cmd_cycles + 1;
   else if (ticks < live_tick) load_nocmd = load_nocmd + 1;
   else live_nocmd = live_nocmd + 1;
`endif
"""

REPORT = """`ifdef QINGYU_PROFILE
     $display("QINGYU_PROFILE st_idle=%0d st_meta_req=%0d st_meta_cap=%0d st_row_init=%0d st_mac_req=%0d st_mac_cap=%0d st_store=%0d st_drain=%0d",
       st_cnt[0],st_cnt[1],st_cnt[2],st_cnt[3],st_cnt[4],st_cnt[5],st_cnt[6],st_cnt[7]);
     $display("QINGYU_PROFILE bus_idle=%0d bus_lo=%0d bus_lo_cap=%0d bus_hi=%0d bus_hi_cap=%0d bus_out_req=%0d cmd_fires=%0d cmd_gap_total=%0d mem_cmd_cycles=%0d load_nocmd=%0d live_nocmd=%0d",
       bus_cnt[0],bus_cnt[1],bus_cnt[2],bus_cnt[3],bus_cnt[4],bus_cnt[5],cmd_fires,cmd_gap_total,mem_cmd_cycles,load_nocmd,live_nocmd);
`endif
"""


def instrument():
    src = (BASE / "weight_perf.sv").read_text(encoding="utf-8")
    anchor = " integer ticks=0, start_tick=-1, live_tick=-1, load_end=-1, end_tick=-1;"
    assert anchor in src
    src = src.replace(anchor, anchor + "\n" + DECL)
    anchor2 = "  if (active) begin\n"
    assert anchor2 in src
    src = src.replace(anchor2, anchor2 + COUNT, 1)
    anchor3 = '$display("QINGYU_PERF_WINDOW'
    idx = src.index(anchor3)
    end_of_call = src.index(');\n', idx) + 3
    src = src[:end_of_call] + REPORT + src[end_of_call:]
    TB_OUT.parent.mkdir(parents=True, exist_ok=True)
    TB_OUT.write_text(src, encoding="utf-8")
    print("wrote", TB_OUT, len(src))


def run(command, log, cwd=ROOT):
    env = dict(os.environ, VERILATOR_ROOT=(TOOLS / "share/verilator").as_posix())
    env["PATH"] = os.pathsep.join((str(TOOLS / "bin"), "D:/Git/usr/bin", env["PATH"]))
    with log.open("w") as out:
        status = subprocess.run([str(c) for c in command], cwd=cwd, env=env,
                                stdout=out, stderr=subprocess.STDOUT).returncode
    if status:
        raise RuntimeError(str(log) + "\n" + log.read_text(errors="replace")[-2500:])


def build():
    WORK.mkdir(parents=True, exist_ok=True)
    files = (BASE / "sources.f").read_text().splitlines()
    tb_line = "build/h1500v_poll/weight_perf.sv"
    assert tb_line in files, "instrumented tb missing from source list"
    files[files.index(tb_line)] = TB_OUT.relative_to(ROOT).as_posix()
    filelist = WORK / "sources.f"
    filelist.write_text("\n".join(files) + "\n")
    obj = WORK / "obj"
    obj.mkdir(exist_ok=True)
    includes = ["-Ivendor/e203_hbirdv2/rtl/e203/" + p for p in ("core", "perips", "perips/apb_i2c")]
    run([TOOLS / "bin/verilator_bin.exe", "--cc", "--main", "--exe", "--timing", "--autoflush",
         "--timescale-override", "1ns/1ps", "--top-module", "tb_qingyu_soc_performance",
         "--prefix", "Vprofile", "--Mdir", obj.relative_to(ROOT).as_posix(), "-Wno-fatal",
         "-DDISABLE_SV_ASSERTION=1", "-DQINGYU_PROFILE", *includes,
         "-CFLAGS", "-std=gnu++20 -O1", "--output-split", "10000", "-f", filelist],
        WORK / "generate.log")
    run(["D:/mingw/mingw64/bin/mingw32-make.exe", "-C", obj, "-f", "Vprofile.mk", "-j6",
         "CXX=" + (TOOLS / "bin/g++.exe").as_posix(), "LINK=" + (TOOLS / "bin/g++.exe").as_posix(),
         "AR=" + (TOOLS / "bin/ar.exe").as_posix(), "PYTHON3=" + Path(sys.executable).as_posix(),
         "PERL=D:/Git/usr/bin/perl.exe", "VERILATOR_ROOT=" + (TOOLS / "share/verilator").as_posix()],
        WORK / "make.log")
    for dll in ("libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll"):
        shutil.copyfile(TOOLS / "bin" / dll, obj / dll)


def measure(layer):
    name = f"layer{layer:02d}"
    out = WORK / name
    out.mkdir(exist_ok=True)
    fw = BASE / name / "firmware64.hex"
    sim = subprocess.run(
        [str(WORK / "obj/Vprofile.exe"), "+FIRMWARE=" + str(fw),
         "+SHARED=" + str(IMAGES / name / "shared.hex"),
         "+EXPECTED=" + str(IMAGES / name / "expected.hex")],
        cwd=out, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    (out / "sim.log").write_text(sim.stdout, encoding="utf-8")
    if sim.returncode:
        raise RuntimeError(f"{name} sim failed\n{sim.stdout[-2000:]}")
    rows = {}
    for line in sim.stdout.splitlines():
        if line.startswith("QINGYU_PERF_WINDOW"):
            for token in line.split()[1:]:
                k, _, v = token.partition("=")
                if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
                    rows[k] = int(v)
        elif line.startswith("QINGYU_PROFILE"):
            for token in line.split()[1:]:
                k, _, v = token.partition("=")
                if v.isdigit():
                    rows[k] = int(v)
    return name, rows


def main():
    instrument()
    build()
    results = {}
    for layer in range(12):
        name, rows = measure(layer)
        results[name] = rows
        print(name, rows.get("cycles"), "st:", [rows.get(f"st_{k}") for k in
              ("idle", "meta_req", "meta_cap", "row_init", "mac_req", "mac_cap", "store", "drain")], flush=True)
    (WORK / "profile.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("WROTE", WORK / "profile.json")


if __name__ == "__main__":
    main()
