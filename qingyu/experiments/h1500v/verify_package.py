import base64, hashlib, io, json, tarfile
from pathlib import Path

eda = Path(r"E:\Desktop\qiansaisheji\output\eda")
root = Path(r"E:\Desktop\qiansaisheji\qingyu")
script = (eda / "run_h1500v.sh").read_bytes()
prefix, body = script.split(b"<<'PAYLOAD'\n", 1)
encoded, suffix = body.split(b"\nPAYLOAD\n", 1)
packed = base64.b64decode(encoded)
print("payload sha256:", hashlib.sha256(packed).hexdigest())
print("declared in script:", hashlib.sha256(packed).hexdigest().encode() in suffix)
files = {}
with tarfile.open(fileobj=io.BytesIO(packed)) as arc:
    for m in arc:
        files[m.name] = arc.extractfile(m).read()

v = (root / "experiments/h1500v/rtl").read_bytes if False else None
check = {
    "rtl/qingyu_accel.sv": root / "experiments/h1500v/rtl/qingyu_accel.sv",
    "rtl/qingyu_fio.sv": root / "experiments/h1500v/rtl/qingyu_fio.sv",
    "driver/qingyu_accel.c": root / "experiments/h1500v/rtl/qingyu_accel.c",
    "driver/soc_perf_main.c": root / "experiments/h1500v/rtl/soc_perf_main.c",
    "layer00/firmware64.hex": root / "build/h1500v_poll/layer00/firmware64.hex",
    "layer11/firmware64.hex": root / "build/h1500v_poll/layer11/firmware64.hex",
}
for name, path in check.items():
    same = name in files and files[name] == path.read_bytes()
    print(f"{name:32s} {'OK' if same else 'MISMATCH'}")

print("area.tcl macro check:", b"RAMSP128X16 33 RAMSP1024X16 8 RAMSP4096X16 0" in files["area.tcl"])
accel_hash = hashlib.sha256((root / 'experiments/h1500v/rtl/qingyu_accel.sv').read_bytes()).hexdigest()
print("formality has new accel hash:", accel_hash.encode() in files["formality.sh"])
print("area gate 2.25e6:", b"if($NF>=2250000)" in suffix)
print("stages in suffix:", [s.decode() for s in (b"VCS", b"dc_shell", b"ab_sta.tcl", b"formal") if s in suffix])
print("total payload files:", len(files))
print("script sha256:", hashlib.sha256(script).hexdigest())
