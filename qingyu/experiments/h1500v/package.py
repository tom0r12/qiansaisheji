"""Freeze the tested h1500v candidate into a server VCS/DC/STA/Formality flow.

Derived from experiments/h1500/package.py. Differences:
- source snapshot is build/h1500v_poll (local Verilator, 12 layers, 304,128 outputs)
- template is output/eda/run_h1500_v2.sh, so the h1500-specific test/patches stay
- the area gate is raised from 0.3 mm2 (self-imposed) to the official 2.25 mm2 cap,
  so the flow continues into five-corner STA and Formality at ~0.32 mm2
"""
import base64
import gzip
import hashlib
import io
import json
import tarfile
import time
from pathlib import Path

root = Path(__file__).resolve().parents[2]
exp = Path(__file__).resolve().parent
eda = root.parent / "output/eda"
run = root / "build/h1500v_poll"

measured = json.loads((run / "result.json").read_text())
assert measured["outputs"] == 304128 and len(measured["layers"]) == 12
assert all(hashlib.sha256((root / k).read_bytes()).hexdigest() == v
           for k, v in measured["sha256"].items())

template = (eda / "run_h1500_v2.sh").read_bytes()
prefix, body = template.split(b"<<'PAYLOAD'\n", 1)
encoded, suffix = body.split(b"\nPAYLOAD\n", 1)
old = base64.b64decode(encoded)
oldhash = hashlib.sha256(old).hexdigest().encode()

files = {}
with tarfile.open(fileobj=io.BytesIO(old)) as arc:
    for m in arc:
        files[m.name] = arc.extractfile(m).read()

old_accel = hashlib.sha256(files["rtl/qingyu_accel.sv"]).hexdigest().encode()

# New accelerator RTL and driver; qingyu_fio.sv is byte-identical to H1500.
files["rtl/qingyu_accel.sv"] = (exp / "rtl/qingyu_accel.sv").read_bytes().replace(b"\r", b"")
for name in ["qingyu_accel.c", "soc_perf_main.c"]:
    files["driver/" + name] = (exp / "rtl" / name).read_bytes().replace(b"\r", b"")

for i in range(12):
    name = f"layer{i:02}/firmware64.hex"
    files[name] = (run / name).read_bytes()

files["local_cycles.tsv"] = "".join(
    f"layer{r['layer']:02} {r['cycles']}\n" for r in measured["layers"]).encode()

new_accel = hashlib.sha256((exp / "rtl/qingyu_accel.sv").read_bytes().replace(b"\r", b"")).hexdigest().encode()
files["formality.sh"] = files["formality.sh"].replace(old_accel, new_accel)

# h1500v removed eight 128x16 output banks: 25 weight/output/meta macros instead of 33.
assert b"RAMSP128X16 33 RAMSP1024X16 8 RAMSP4096X16 0" in files["area.tcl"]
files["area.tcl"] = files["area.tcl"].replace(
    b"RAMSP128X16 33 RAMSP1024X16 8 RAMSP4096X16 0",
    b"RAMSP128X16 25 RAMSP1024X16 8 RAMSP4096X16 0")
files["ab_sta.tcl"] = files["ab_sta.tcl"].replace(b"macros=23", b"macros=33")

buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w") as arc:
    for name, data in files.items():
        m = tarfile.TarInfo(name)
        m.size = len(data)
        m.mtime = int(time.time())
        arc.addfile(m, io.BytesIO(data))
packed = gzip.compress(buf.getvalue(), mtime=0)

# Official area cap instead of the self-imposed 0.3 mm2 gate.
suffix = suffix.replace(b"if($NF>=300000)", b"if($NF>=2250000)")
suffix = suffix.replace(b"QINGYU_STA_COUNTS='RAMSP128X16 33 RAMSP1024X16 8 RAMSP4096X16 0'",
                        b"QINGYU_STA_COUNTS='RAMSP128X16 25 RAMSP1024X16 8 RAMSP4096X16 0'")
suffix = suffix.replace(b"41 private macros", b"33 private macros")
suffix = suffix.replace(b"121 SRAM macros", b"113 SRAM macros")
suffix = suffix.replace(b"for variant in H1500;", b"for variant in H1500V;")
suffix = suffix.replace(oldhash, hashlib.sha256(packed).hexdigest().encode())
suffix = suffix.replace(
    b"Engineering timing only; inspect hold/setup violations and formal audit. New energy measurements remain pending.",
    b"Engineering timing only; inspect hold/setup violations and formal audit. Area gate uses the official 2.25 mm2 cap.")

script = prefix + b"<<'PAYLOAD'\n" + base64.encodebytes(packed).rstrip() + b"\nPAYLOAD\n" + suffix
script = script.replace(b"qingyu_h1500_XXXXXX", b"qingyu_h1500v_XXXXXX")
script = script.replace(b"QINGYU_H1500", b"QINGYU_H1500V")
target = eda / "run_h1500v.sh"
target.write_bytes(script)
print(target, len(script), hashlib.sha256(script).hexdigest())
print("area gate:", b"if($NF>=2250000)" in script, "| h1500v names:", b"qingyu_h1500v_XXXXXX" in script)
