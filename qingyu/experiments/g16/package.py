"""Pack frozen G sources and tested firmware into F's vendor SRAM / DC / PT flow."""
import base64
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path
from weight_monitor import instrument

experiment = Path(__file__).resolve().parent
root = experiment.parents[1]
eda = root.parent / "output/eda"
run = root / "build/g_combined"
measured = json.loads((run / "result.json").read_text())
assert len(measured["layers"]) == 12 and measured["outputs"] == 304128
assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
           for name, digest in measured["sha256"].items())

def add_file(archive, name, data):
    entry = tarfile.TarInfo(name)
    entry.size = len(data)
    archive.addfile(entry, io.BytesIO(data))

template = (eda / "run_dualrow.sh").read_bytes()
prefix, body = template.split(b"<<'PAYLOAD'\n", 1)
encoded, suffix = body.split(b"\nPAYLOAD\n", 1)
old = base64.b64decode(encoded)
old_hash = hashlib.sha256(old).hexdigest().encode()
assert old_hash in suffix
buf = io.BytesIO()
with tarfile.open(fileobj=io.BytesIO(old)) as src, tarfile.open(fileobj=buf, mode="w") as dst:
    for member in src:
        name = member.name
        data = src.extractfile(member).read()
        if name == "rtl/qingyu_fio.sv":
            header = data.replace(b"\r", b"").split(b"// System-bus endpoint", 1)[0]
            assert header.startswith(b"`define") and len(header) < 200
            data = header + (experiment / name).read_bytes().replace(b"\r", b"")
        elif name == "rtl/qingyu_accel.sv":
            data = (experiment / name).read_bytes().replace(b"\r", b"")
        elif name.endswith("/firmware64.hex"):
            data = (run / name).read_bytes()
        elif name in ("tb_qingyu_soc_performance.sv", "tb_qingyu_soc_macro_performance.sv"):
            data = instrument(data)
        add_file(dst, name, data)
    for name in ("tb_load_chain.sv", "tb_weight_stream.sv"):
        add_file(dst, name, (experiment / "tests" / name).read_bytes().replace(b"\r", b""))
    add_file(dst, "driver/qingyu_accel.c", (experiment / "rtl/qingyu_accel.c").read_bytes())
    local = "".join(f"layer{row['layer']:02} {row['cycles']}\n" for row in measured["layers"])
    add_file(dst, "local_cycles.tsv", local.encode())

packed = gzip.compress(buf.getvalue(), mtime=0)
suffix = suffix.replace(old_hash, hashlib.sha256(packed).hexdigest().encode())
marker = b"grep '^PASS CPU block transfer' ../block_test.log\n"
assert suffix.count(marker) == 1
suffix = suffix.replace(marker, marker + b'''for unit in tb_weight_stream tb_load_chain; do
 vcs -full64 -sverilog -timescale=1ns/1ps +define+ARM_UD_MODEL +define+QINGYU_BLOCK_COPY +define+QINGYU_READ_AHEAD +define+QINGYU_DOUBLE_BUFFER -top "$unit" "../$unit.sv" rtl/qingyu_accel.sv rtl/qingyu_fio.sv macro/qingyu_sram16.sv "$models/RAMSP128X16/verilog/RAMSP128X16.v" "$models/RAMSP4096X16/verilog/RAMSP4096X16.v" -Mdir="$run/${unit}_csrc" -o "$run/${unit}_sim" > "../${unit}_compile.log" 2>&1 || { tail -20 "../${unit}_compile.log"; exit 1; }
 "$run/${unit}_sim" > "../${unit}_test.log" 2>&1
 grep '^PASS ' "../${unit}_test.log"
done
''')
suffix = suffix.replace(b'cat batch_waits.tsv', b'cat batch_waits.tsv\ndiff -u local_cycles.tsv cycles.tsv || echo "QINGYU_G16_VENDOR_CYCLE_DIFFERENCE: review before quoting"')
suffix = suffix.replace(b'for variant in F; do', b'for variant in G; do')
suffix = suffix.replace(b'with frozen fast16 FIO', b'with frozen G16 FIO')
script = prefix + b"<<'PAYLOAD'\n" + base64.encodebytes(packed).rstrip() + b"\nPAYLOAD\n" + suffix
script = script.replace(b"qingyu_dualrow_XXXXXX", b"qingyu_g16_XXXXXX").replace(b"QINGYU_DUALROW", b"QINGYU_G16")
target = eda / "run_g16.sh"
target.write_bytes(script)
print(target, len(script), hashlib.sha256(script).hexdigest())
