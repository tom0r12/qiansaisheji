"""Derive measure_macro.py (local macro-structure check) from a candidate's
measure script: same flow, but the SoC uses the ASIC wrappers (banked TCMs,
multi-port shared SRAM macros, accelerator macro wrapper), the macro fixture and
behavioural stand-ins for the vendor macros.  Usage: make_macro_measure.py <expdir>"""
import sys, pathlib

exp = pathlib.Path(sys.argv[1]).resolve()
src = next(p for p in exp.glob("measure_*.py") if p.name != "measure_macro.py")
s = src.read_text().replace("\r\n", "\n")


def rep(a, b):
    global s
    assert s.count(a) == 1, a[:70]
    s = s.replace(a, b)


rep('default="build/' + exp.name + '"', 'default="build/' + exp.name + '_macro"')
name_line = [l for l in s.splitlines() if l.startswith('name = "V')][0]
rep(name_line, 'name = "Vmacro"')
rep('''filelist = work / "sources.f"''', '''# Macro structure: drop behavioural memories, add ASIC wrappers + stand-in macros.
here = Path(__file__).resolve().parent
drop = {"vendor/e203_hbirdv2/rtl/e203/general/sirv_gnrl_ram.v",
        "vendor/e203_hbirdv2/rtl/e203/general/sirv_sim_ram.v",
        shared.relative_to(ROOT).as_posix(), "rtl/qingyu_sram16.sv",
        (here / "tb/tb_qingyu_soc.sv").relative_to(ROOT).as_posix()}
files = [f for f in files if f not in drop]
macro_perf = work / "tb_macro_performance.sv"
perf_src = (here / "tb/tb_qingyu_soc_performance.sv").read_bytes().replace(b"\\r", b"")
fw = (b'   $display("QINGYU_PERF_FIRMWARE outer_cycles=%0d driver_cycles=%0d compute_cycles=%0d",\\n'
      b"    {`MEM.mem[49155],`MEM.mem[49154]}, {`MEM.mem[49153],`MEM.mem[49152]}, `MEM.mem[49156]);\\n")
assert perf_src.count(fw) == 1
macro_perf.write_bytes(perf_src.replace(fw, b'   $display("QINGYU_MACRO_TASK_WRITES_COMPLETE: physical readback follows");\\n'))
tbi = files.index((here / "tb/tb_qingyu_soc_performance.sv").relative_to(ROOT).as_posix())
files[tbi] = macro_perf.relative_to(ROOT).as_posix()
files += ["rtl/asic/qingyu_banked_sram.sv", "rtl/asic/qingyu_sram16.sv", "rtl/asic/sirv_gnrl_ram.v",
          (candidate / "asic/qingyu_shared_sram_mp.sv").relative_to(ROOT).as_posix(),
          (here / "macro/tb_qingyu_soc_macros.sv").relative_to(ROOT).as_posix(),
          (here / "macro/sram_stub_models.v").relative_to(ROOT).as_posix()]
filelist = work / "sources.f"''')
rep('''    result = summarize((out / "sim.log").read_text(errors="replace"), layer)''',
    '''    text = (out / "sim.log").read_text(errors="replace")
    if "PASS real E203 + 129 SRAM macros" not in text:
        raise RuntimeError(layer_name + ": macro readback did not pass")
    result = summarize(text.replace("PASS real E203 + 129", "PASS real E203"), layer)''')
(exp / "measure_macro.py").write_text(s)
print("wrote", exp / "measure_macro.py")
