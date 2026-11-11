"""Build INT16-output performance images from the frozen INT32 images.

For each of the 12 performance layers:
  1. parse the staging copy in shared.hex (inputs, weights, bias, shift);
  2. recompute the INT32 outputs and require an exact match with expected.hex;
  3. recalibrate on the training split (same reference.py procedure) and require
     the INT32 shifts to equal the shifts stored in the image;
  4. choose INT16 shifts on the training split (smallest shift with no INT16
     saturation, same rule as INT32), write them into the staging shift table,
     and write the packed INT16 expected outputs (two per word, low lane first).
Also reports validation-split NRMSE for INT32 and INT16 against the float model.
"""
import hashlib, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "model"))
from reference import calibrate_layer, encode_layer, _scale  # noqa: E402

SRC = ROOT / "reports/soc_performance_20261104_224417"
DST = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "reports/soc_performance_q16")
ST = 0x40000 // 4  # staging word base


def rne(a, s):
    s = np.broadcast_to(np.asarray(s, dtype=np.int64), a.shape)
    mag = np.abs(a); q = mag >> s; r = mag - (q << s)
    half = np.where(s > 0, np.int64(1) << np.maximum(s - 1, 0), 0)
    up = (s > 0) & ((r > half) | ((r == half) & ((q & 1) == 1)))
    return np.sign(a) * (q + up)


def acc(x, w, b):
    return (x.astype(np.float64) @ w.astype(np.float64)).astype(np.int64) + b.astype(np.int64)


def words_to_i16(words):
    w = np.asarray(words, dtype=np.uint32)
    lo = (w & 0xffff).astype(np.uint16).view(np.int16)
    hi = (w >> 16).astype(np.uint16).view(np.int16)
    return np.stack([lo, hi], axis=1).reshape(-1)


def min_shift(a_cols, lo, hi):
    out = []
    for j in range(a_cols.shape[1]):
        col = a_cols[:, j]
        for s in range(48):
            r = rne(col, s)
            if r.max() <= hi and r.min() >= lo:
                out.append(s); break
        else:
            raise OverflowError("no shift for column %d" % j)
    return np.array(out, dtype=np.int64)


report = dict(source=str(SRC.relative_to(ROOT)), layers=[])
for L in range(12):
    name = "layer%02d" % L
    mem = np.array([int(l, 16) for l in (SRC / name / "shared.hex").read_text().split()], dtype=np.uint64)
    exp32 = np.array([int(l, 16) for l in (SRC / name / "expected.hex").read_text().split()], dtype=np.uint64)
    x = words_to_i16(mem[ST:ST + 3168]).reshape(99, 64)
    w = words_to_i16(mem[ST + 0x4000 // 4:ST + 0x4000 // 4 + 8192]).reshape(64, 256)
    bw = mem[ST + 0xc000 // 4:ST + 0xc000 // 4 + 512].astype(np.uint64)
    b = (bw[0::2] | (bw[1::2] << np.uint64(32))).view(np.int64)
    sw = mem[ST + 0xc800 // 4:ST + 0xc800 // 4 + 64].astype(np.uint32)
    sh32 = np.frombuffer(sw.astype("<u4").tobytes(), dtype=np.uint8).astype(np.int64)
    a = acc(x, w, b)
    y32 = np.clip(rne(a, sh32), -2**31, 2**31 - 1).astype(np.int64)
    if not np.array_equal((y32.reshape(-1) & 0xffffffff).astype(np.uint64), exp32):
        raise SystemExit(name + ": INT32 recompute does not match expected.hex")
    tr = np.load(ROOT / ("model/full_v2_run/float_training/%s.npz" % name))
    va = np.load(ROOT / ("model/full_v2_run/float_validation/%s.npz" % name))
    cfg = calibrate_layer(tr["X"], tr["W"], tr["b"], L, role="training")
    if not np.array_equal(np.asarray(cfg.shifts), sh32):
        raise SystemExit(name + ": training calibration does not reproduce the image shifts")
    qx, qw, qb, _ = encode_layer(tr["X"], tr["W"], tr["b"], cfg)
    if not (np.array_equal(qw, w) and np.array_equal(qb, b)):
        raise SystemExit(name + ": quantized weights/bias differ from the image")
    sh16 = min_shift(acc(qx, qw, qb).reshape(-1, 256), -32768, 32767)
    if sh16.max() > 47:
        raise SystemExit(name + ": INT16 shift exceeds hardware range")
    y16 = rne(a, sh16)
    task_sat = int(((y16 < -32768) | (y16 > 32767)).sum())
    y16 = np.clip(y16, -32768, 32767).astype(np.int16).reshape(-1)
    packed = (y16[0::2].view(np.uint16).astype(np.uint32)
              | (y16[1::2].view(np.uint16).astype(np.uint32) << 16))
    # validation NRMSE vs float, both formats
    vx, vw, vb, _ = encode_layer(va["X"], va["W"], va["b"], cfg)
    va_acc = acc(vx, vw, vb); yf = va["Y"].astype(np.float64)
    nr = {}
    for tag, s, lo, hi in (("int32", sh32, -2**31, 2**31 - 1), ("int16", sh16, -32768, 32767)):
        q = rne(va_acc, s); sat = int(((q < lo) | (q > hi)).sum()); q = np.clip(q, lo, hi)
        f = np.array([_scale(cfg.x_exponent + e + int(r)) for e, r in zip(cfg.w_exponents, s)])
        nr[tag] = dict(nrmse_percent=float(np.sqrt(np.mean((q * f - yf) ** 2)) / np.sqrt(np.mean(yf ** 2)) * 100),
                       saturated=sat)
    new = mem.copy()
    sb = np.zeros(256, dtype=np.uint8); sb[:] = sh16
    new[ST + 0xc800 // 4:ST + 0xc800 // 4 + 64] = np.frombuffer(sb.tobytes(), dtype="<u4").astype(np.uint64)
    out = DST / name; out.mkdir(parents=True, exist_ok=True)
    (out / "shared.hex").write_text("".join("%08x\n" % int(v) for v in new))
    (out / "expected.hex").write_text("".join("%08x\n" % int(v) for v in packed))
    row = dict(layer=L, shift16_min=int(sh16.min()), shift16_max=int(sh16.max()),
               shift_delta_mean=float((sh16 - sh32).mean()), task_saturated=task_sat,
               validation=nr,
               sha256={f: hashlib.sha256((out / f).read_bytes()).hexdigest() for f in ("shared.hex", "expected.hex")})
    report["layers"].append(row)
    print(name, "ok shift16 %d..%d  task_sat=%d  val NRMSE int32=%.6f%% int16=%.6f%%" % (
        row["shift16_min"], row["shift16_max"], task_sat, nr["int32"]["nrmse_percent"], nr["int16"]["nrmse_percent"]), flush=True)
report["max_validation_nrmse_percent"] = {t: max(r["validation"][t]["nrmse_percent"] for r in report["layers"]) for t in ("int32", "int16")}
(DST / "q16_images.json").write_text(json.dumps(report, indent=2))
print("MAX", report["max_validation_nrmse_percent"])
