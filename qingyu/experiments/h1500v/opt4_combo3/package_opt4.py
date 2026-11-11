"""Freeze opt4_combo3 into the server VCS/DC/STA/Formality flow (run_h1500v_opt4.sh).

Template: output/eda/run_h1500v_opt3.sh (opt3, same macro counts 41/8/0).
Changes vs opt3c:
- RTL: combo3 accel/FIO (background staging engine + OUT16). The FIO keeps the
  four h1500v header defines; QINGYU_OUT16 is passed explicitly to DC (area.tcl),
  Formality (defines.v) and the SoC VCS run, so the six unit TBs keep testing the
  INT32 path they were written for.
- Firmware (12 layers) from build/opt4_combo3; local_cycles.tsv from its result.json.
- Task data: make_q16_server.py converts the frozen INT32 images on the server and
  checks every file against development SHA-256 values.
- Performance TBs: opt4 versions (per-word live-written check; result counting).
- Macro fixture readback loop 25344 -> 12672 words (sed + check).
"""
import base64, gzip, hashlib, io, json, re, sys, tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXP = Path(__file__).resolve().parent
EDA = ROOT.parent / "output/eda"
BUILD = ROOT / "build/opt4_combo3"
sys.path.insert(0, str(ROOT / "experiments/g16"))
from weight_monitor import instrument  # noqa: E402

h = lambda b: hashlib.sha256(b).hexdigest()
lf = lambda p: Path(p).read_bytes().replace(b"\r", b"")
res = json.loads((BUILD / "result.json").read_text())
assert res["outputs"] == 304128 and len(res["layers"]) == 12 and all(l["passed"] for l in res["layers"])

tpl = (EDA / "run_h1500v_opt3.sh").read_bytes()
prefix, body = tpl.split(b"<<'PAYLOAD'\n", 1)
enc, suffix = body.split(b"\nPAYLOAD\n", 1)
old = base64.b64decode(enc)
files = {}
with tarfile.open(fileobj=io.BytesIO(old)) as t:
    for m in t.getmembers():
        if m.isfile():
            files[m.name] = t.extractfile(m).read()


def rep(name, a, b, n=1):
    s = files[name]
    assert s.count(a) == n, (name, a[:60], s.count(a))
    files[name] = s.replace(a, b)


HDR = b"`define QINGYU_READ_AHEAD\n`define QINGYU_PIPE_MAC\n`define QINGYU_DOUBLE_BUFFER\n`define QINGYU_FAST_TASK\n"
accel = lf(EXP / "rtl/qingyu_accel.sv")
fio = HDR + lf(EXP / "rtl/qingyu_fio.sv")
files["rtl/qingyu_accel.sv"], files["rtl/qingyu_fio.sv"] = accel, fio
for n in ("qingyu_accel.c", "qingyu_accel.h", "soc_perf_main.c"):
    files["driver/" + n] = lf(EXP / "rtl" / n)
for i in range(12):
    files["layer%02d/firmware64.hex" % i] = (BUILD / ("layer%02d/firmware64.hex" % i)).read_bytes()
files["local_cycles.tsv"] = "".join("layer%02d %d\n" % (l["layer"], l["cycles"]) for l in res["layers"]).encode()
files["make_q16_server.py"] = lf(EXP / "make_q16_server.py")

# Formality: new RTL hashes and the OUT16 define
rep("formality.sh", b"423d91f0345914cf23de0af520787c4176e78fb886e6b43a9b53b10fdac953ee  inputs/qingyu_accel.sv",
    h(accel).encode() + b"  inputs/qingyu_accel.sv")
rep("formality.sh", b"93a61b3c1c2b08af4a6b64d79e4185c086d7fb32937ec077d07c61edf0bd2b98  inputs/qingyu_fio.sv",
    h(fio).encode() + b"  inputs/qingyu_fio.sv")
rep("formality.sh", b"`define QINGYU_DOUBLE_BUFFER\nDEFINES", b"`define QINGYU_DOUBLE_BUFFER\n`define QINGYU_OUT16\nDEFINES")
# DC: synthesize the OUT16 configuration
rep("area.tcl", b"-define {SYNTHESIS QINGYU_FAST_TASK QINGYU_BLOCK_COPY}", b"-define {SYNTHESIS QINGYU_FAST_TASK QINGYU_BLOCK_COPY QINGYU_OUT16}")

# Performance TBs = opt4 TB + the same weight monitor the local measurement used
tb = (EXP / "tb/tb_qingyu_soc_performance.sv").read_bytes()
perf = instrument(tb).replace(b"weight_commands!=512", b"weight_commands!=16").replace(
    b"fixture.dut.u_fio.take_block && fixture.dut.u_fio.weight_cmd)",
    b"fixture.dut.u_fio.take_block && fixture.dut.u_fio.weight_cmd && fixture.dut.u_fio.icb_cmd_ready)").replace(
    b"fixture.dut.u_fio.icb_cmd_addr==32'hf0000038) begin",
    b"(fixture.dut.u_fio.icb_cmd_addr==32'hf0000038 || fixture.dut.u_fio.icb_cmd_addr==32'hf0000084)) begin")
assert perf.count(b"icb_cmd_ready)") >= 1 and perf.count(b"32'hf0000084") == 1
fw = (b'   $display("QINGYU_PERF_FIRMWARE outer_cycles=%0d driver_cycles=%0d compute_cycles=%0d",\n'
      b"    {`MEM.mem[49155],`MEM.mem[49154]}, {`MEM.mem[49153],`MEM.mem[49152]}, `MEM.mem[49156]);\n")
assert perf.count(fw) == 1
files["tb_qingyu_soc_performance.sv"] = perf
files["tb_qingyu_soc_macro_performance.sv"] = perf.replace(
    fw, b'   $display("QINGYU_MACRO_TASK_WRITES_COMPLETE: physical readback follows");\n')

buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w") as t:
    for n in sorted(files):
        ti = tarfile.TarInfo(n); ti.size = len(files[n]); ti.mtime = 0
        t.addfile(ti, io.BytesIO(files[n]))
packed = gzip.compress(buf.getvalue(), mtime=0)

def srep(a, b, n=1):
    global suffix
    assert suffix.count(a) == n, (a[:70], suffix.count(a))
    suffix = suffix.replace(a, b)

srep(h(old).encode(), h(packed).encode())
srep(b"sed -i 's/PASS real E203 + 89 SRAM macros/PASS real E203 + 129 SRAM macros/' macro/tb_qingyu_soc_macros.sv\n",
     b"sed -i 's/PASS real E203 + 89 SRAM macros/PASS real E203 + 129 SRAM macros/' macro/tb_qingyu_soc_macros.sv\n"
     b"sed -i 's/for(integer j=0;j<25344;j=j+1) begin/for(integer j=0;j<12672;j=j+1) begin/' macro/tb_qingyu_soc_macros.sv\n"
     b"grep -q 'for(integer j=0;j<12672;j=j+1) begin' macro/tb_qingyu_soc_macros.sv || { echo 'QINGYU_OPT4: macro readback patch failed'; exit 1; }\n"
     b"echo 'QINGYU_OPT4: converting the 12 frozen task images to INT16 outputs'\n"
     b"python3 ../make_q16_server.py || { echo 'QINGYU_OPT4: INT16 image conversion failed'; exit 1; }\n")
srep(b'+define+DISABLE_SV_ASSERTION=1 "$includes" -top tb_qingyu_soc_performance',
     b'+define+DISABLE_SV_ASSERTION=1 +define+QINGYU_OUT16 "$includes" -top tb_qingyu_soc_performance')
srep(b"mapping FIO and 33 private macros", b"mapping FIO and 49 private macros")
out = prefix + b"<<'PAYLOAD'\n" + base64.encodebytes(packed).rstrip() + b"\nPAYLOAD\n" + suffix
dst = EDA / "run_h1500v_opt4.sh"
dst.write_bytes(out)
print("wrote", dst, len(out), h(out))
print("accel", h(accel)); print("fio", h(fio))
