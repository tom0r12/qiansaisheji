"""Freeze a multi-port candidate (opt10 line) into the server sign-off scripts.

Usage: python package_final.py <experiment dir> <tag>     e.g.  opt10_ilv opt10
Templates (opt4 sign-off set in output/eda): run_h1500v_opt4.sh,
run_h1500v_opt4_formal_final.sh, run_h1500v_soc_opt3.sh,
run_h1500v_energy_opt4.sh, run_opt4_chain.sh.
Changes vs opt4:
- RTL accel/FIO + generated SoC top (5-port shared SRAM wiring);
- macro/qingyu_shared_sram_mp.sv (32 word-interleaved banks, 64 RAMSP4096X16 as
  before) appended to sources_macro.f; macro fixture loads/reads the shared
  image through port 0 of that memory;
- performance TB: multi-port monitor (weight-transfer checks built in);
- the five single-port FIO protocol unit TBs are not run (their beat-exact
  checks describe the replaced single-port engine); tb_batch_buffers stays;
- SoC synthesis copies the new top + shared-SRAM wrapper into its inputs;
- energy: macro activity map uses the per-bank shared-SRAM instance paths.
"""
import base64, gzip, hashlib, io, json, re, sys, tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXP = (ROOT / "experiments/h1500v" / sys.argv[1]).resolve()
TAG = sys.argv[2]
EDA = ROOT.parent / "output/eda"
BUILD = ROOT / "build" / EXP.name

h = lambda b: hashlib.sha256(b).hexdigest()
lf = lambda p: Path(p).read_bytes().replace(b"\r", b"")
res = json.loads((BUILD / "result.json").read_text())
assert res["outputs"] == 304128 and len(res["layers"]) == 12 and all(l["passed"] for l in res["layers"]), \
    "run all 12 layers first"

tpl = (EDA / "run_h1500v_opt4.sh").read_bytes()
prefix, body = tpl.split(b"<<'PAYLOAD'\n", 1)
enc, suffix = body.split(b"\nPAYLOAD\n", 1)
old = gzip.decompress(base64.b64decode(enc)) if base64.b64decode(enc)[:2] == b"\x1f\x8b" else base64.b64decode(enc)
files = {}
with tarfile.open(fileobj=io.BytesIO(old)) as t:
    for m in t.getmembers():
        if m.isfile():
            files[m.name] = t.extractfile(m).read()
old_accel, old_fio = files["rtl/qingyu_accel.sv"], files["rtl/qingyu_fio.sv"]

HDR = b"`define QINGYU_READ_AHEAD\n`define QINGYU_PIPE_MAC\n`define QINGYU_DOUBLE_BUFFER\n`define QINGYU_FAST_TASK\n"
accel = lf(EXP / "rtl/qingyu_accel.sv")
fio = HDR + lf(EXP / "rtl/qingyu_fio.sv")
top = lf(EXP / "rtl/qingyu_e203_soc_top.v")
shared = lf(EXP / "rtl/asic/qingyu_shared_sram_mp.sv")
files["rtl/qingyu_accel.sv"], files["rtl/qingyu_fio.sv"] = accel, fio
files["generated/qingyu_e203_soc_top.v"] = top
files["macro_mp/qingyu_shared_sram_mp.sv"] = shared
files["tb_qingyu_soc_macros.sv"] = lf(EXP / "macro/tb_qingyu_soc_macros.sv")
for n in ("qingyu_accel.c", "qingyu_accel.h", "soc_perf_main.c"):
    files["driver/" + n] = lf(EXP / "rtl" / n)
for i in range(12):
    files["layer%02d/firmware64.hex" % i] = (BUILD / ("layer%02d/firmware64.hex" % i)).read_bytes()
files["local_cycles.tsv"] = "".join("layer%02d %d\n" % (l["layer"], l["cycles"]) for l in res["layers"]).encode()
for n in ("tb_block_copy.sv", "tb_weight_stream.sv", "tb_load_chain.sv", "tb_stage256.sv", "tb_h1500_transfer.sv"):
    files.pop(n, None)


def rep(name, a, b, n=1):
    s = files[name]
    assert s.count(a) == n, (name, a[:60], s.count(a))
    files[name] = s.replace(a, b)


rep("formality.sh", h(old_accel).encode() + b"  inputs/qingyu_accel.sv", h(accel).encode() + b"  inputs/qingyu_accel.sv")
rep("formality.sh", h(old_fio).encode() + b"  inputs/qingyu_fio.sv", h(fio).encode() + b"  inputs/qingyu_fio.sv")

perf = lf(EXP / "tb/tb_qingyu_soc_performance.sv")
fw = (b'   $display("QINGYU_PERF_FIRMWARE outer_cycles=%0d driver_cycles=%0d compute_cycles=%0d",\n'
      b"    {`MEM.mem[49155],`MEM.mem[49154]}, {`MEM.mem[49153],`MEM.mem[49152]}, `MEM.mem[49156]);\n")
assert perf.count(fw) == 1 and b"QINGYU_WEIGHT_TRANSFER" in perf
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


old_payload_hash = re.search(rb"echo '([0-9a-f]{64})  payload.tgz'", prefix + suffix)
assert old_payload_hash
if old_payload_hash.group(1) in suffix:
    srep(old_payload_hash.group(1), h(packed).encode())
else:
    assert prefix.count(old_payload_hash.group(1)) == 1
    prefix = prefix.replace(old_payload_hash.group(1), h(packed).encode())
srep(b"cp ../generated/qingyu_e203_soc_top.v generated/\n",
     b"cp ../generated/qingyu_e203_soc_top.v generated/\n"
     b"cp ../macro_mp/qingyu_shared_sram_mp.sv macro/\n"
     b"cp ../tb_qingyu_soc_macros.sv macro/tb_qingyu_soc_macros.sv\n"
     b"grep -qx 'macro/qingyu_shared_sram_mp.sv' sources_macro.f || echo 'macro/qingyu_shared_sram_mp.sv' >> sources_macro.f\n"
     b"echo 'QINGYU_" + TAG.upper().encode() + b": 5-port shared SRAM (32 word-interleaved banks) wired in'\n")
start = suffix.index(b"vcs -full64 -sverilog -timescale=1ns/1ps +define+QINGYU_BLOCK_COPY +define+QINGYU_READ_AHEAD +define+QINGYU_DOUBLE_BUFFER +define+ARM_UD_MODEL -top tb_block_copy")
end = suffix.index(b"done\n", start) + len(b"done\n")
suffix = suffix[:start] + (b"echo 'QINGYU_" + TAG.upper().encode() +
                           b": single-port FIO protocol unit TBs retired (multi-port FIO); SoC runs below cover it'\n") + suffix[end:]
main = prefix + b"<<'PAYLOAD'\n" + base64.encodebytes(packed).rstrip() + b"\nPAYLOAD\n" + suffix
out = {}
out["run_h1500v_%s.sh" % TAG] = main

# final Formality: new RTL hashes
ff = (EDA / "run_h1500v_opt4_formal_final.sh").read_bytes()
for a, b in ((h(old_accel), h(accel)), (h(old_fio), h(fio))):
    assert ff.count(a.encode()) == 1
    ff = ff.replace(a.encode(), b.encode())
out["run_h1500v_%s_formal_final.sh" % TAG] = ff

# SoC synthesis: new top + shared-SRAM wrapper from the final directory (mp/)
soc = (EDA / "run_h1500v_soc_opt3.sh").read_bytes()
a = b'cp "$area/soc.tcl" "$area/pre.tcl" "$area/supplement.sh" "$area/local_cycles.tsv" "$run/"\ncd "$run"\n'
assert soc.count(a) == 1
soc = soc.replace(a, a + (
    b"# Multi-port shared SRAM: generated top + macro wrapper of this candidate.\n"
    b"cat > mp.sha256 <<'HASH'\n" +
    h(top).encode() + b"  " + b"$AREA_MP/qingyu_e203_soc_top.v\n" +
    h(shared).encode() + b"  " + b"$AREA_MP/qingyu_shared_sram_mp.sv\nHASH\n"
    b'sed -i "s#\\$AREA_MP#$area/mp#" mp.sha256\n'
    b"sha256sum -c mp.sha256\n"
    b'cp "$area/mp/qingyu_e203_soc_top.v" inputs/generated/qingyu_e203_soc_top.v\n'
    b'cp "$area/mp/qingyu_shared_sram_mp.sv" inputs/macro/qingyu_shared_sram_mp.sv\n'
    b"grep -qx 'macro/qingyu_shared_sram_mp.sv' inputs/sources_macro.f || echo 'macro/qingyu_shared_sram_mp.sv' >> inputs/sources_macro.f\n"))
out["run_h1500v_soc_%s.sh" % TAG] = soc

# energy: shared-SRAM macro instance paths are per bank now
en = (EDA / "run_h1500v_energy_opt4.sh").read_bytes()
a = b"s = s.replace(old, new)\n# opt4:"
assert en.count(a) == 1
en = en.replace(a, b"""s = s.replace(old, new)
# multi-port shared SRAM: 32 banks x 2 slices under u_shared.g_bank[k].u_bank
g_old = "groups = [('u_shared.u_storage', 32, 2)]"
if s.count(g_old) != 1:
    sys.exit('supplement.sh: shared-SRAM group line not found')
s = s.replace(g_old, "groups = []")
m_old = "add('u_fio.u_accel.metadata_ram.g128.macro_ram', 7)"
if s.count(m_old) != 1:
    sys.exit('supplement.sh: metadata RAM line not found')
s = s.replace(m_old, m_old + "\\nfor k in range(32):\\n    for t in range(2):\\n        add('u_shared.g_bank[{}].u_bank.banks[0].slices[{}].macro_ram'.format(k, t), 12)")
# opt4:""")
out["run_h1500v_energy_%s.sh" % TAG] = en

ch = (EDA / "run_opt4_chain.sh").read_bytes()
for a, b in ((b"run_h1500v_opt4.sh", b"run_h1500v_%s.sh" % TAG.encode()),
             (b"run_h1500v_opt4_formal_final.sh", b"run_h1500v_%s_formal_final.sh" % TAG.encode()),
             (b"run_h1500v_soc_opt3.sh", b"run_h1500v_soc_%s.sh" % TAG.encode()),
             (b"run_h1500v_energy_opt4.sh", b"run_h1500v_energy_%s.sh" % TAG.encode()),
             (b"opt4_chain", b"%s_chain" % TAG.encode()),
             (b"h1500vp_opt4_final", b"h1500vp_%s_final" % TAG.encode()),
             (b"# opt4 full sign-off chain", b"# %s full sign-off chain" % TAG.encode())):
    assert a in ch, a
    ch = ch.replace(a, b)
a = b'printf \'%s\\n\' "main=$main"'
assert ch.count(a) == 1
ch = ch.replace(a, b'mkdir -p "$fin/mp"\ncp "$main/inputs/generated/qingyu_e203_soc_top.v" "$main/inputs/macro/qingyu_shared_sram_mp.sv" "$fin/mp/"\n' + a)
out["run_%s_chain.sh" % TAG] = ch

for n, b in out.items():
    (EDA / n).write_bytes(b)
    print("%-40s %7d  %s" % (n, len(b), h(b)))
print("accel", h(accel)); print("fio  ", h(fio)); print("top  ", h(top)); print("sram ", h(shared))
