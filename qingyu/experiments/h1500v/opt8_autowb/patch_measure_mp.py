import sys, pathlib
p = pathlib.Path(sys.argv[1])
s = p.read_bytes().decode().replace("\r\n", "\n")


def rep(old, new):
    global s
    assert s.count(old) == 1, old[:70]
    s = s.replace(old, new)


rep('"""Measure opt4 candidates', '"""Measure the opt5 multi-port shared-SRAM candidate (built on opt4 combo4)')
rep('default="experiments/h1500v/opt4_combo4/rtl"', 'default="experiments/h1500v/opt5_mp/rtl"')
rep('default="build/opt4_combo4"', 'default="build/opt5_mp"')
rep('name = "Vopt4c4"', 'name = "Vopt5mp"')
start = s.index("if args.check_weight:")
end = s.index("for old, new in [")
s = s[:start] + '''# The opt5 monitor checks the weight transfer itself (all five ports).
tb = "tb/tb_qingyu_soc_performance.sv"
files[files.index(tb)] = (Path(__file__).resolve().parent / tb).relative_to(ROOT).as_posix()
''' + s[end:]
rep('''for old, new in [("build/dual_row_study/qingyu_accel.sv", accel), ("rtl/qingyu_fio.sv", fio),''',
    '''shared = candidate / "qingyu_shared_sram_mp.sv"
top = candidate / "qingyu_e203_soc_top.v"
for old, new in [("build/dual_row_study/qingyu_accel.sv", accel), ("rtl/qingyu_fio.sv", fio),
                 ("rtl/qingyu_shared_sram.sv", shared), ("generated/qingyu_e203_soc_top.v", top),''')
rep("hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in (accel, fio, driver, main, filelist)}",
    "hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in (accel, fio, shared, top, driver, main, filelist)}")
rep("rtl_hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in (accel, fio, filelist)}",
    "rtl_hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in (accel, fio, shared, top, filelist)}")
p.write_bytes(s.encode())
print("measure patched")
