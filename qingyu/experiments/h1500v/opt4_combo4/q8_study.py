"""Validation-split error of INT32 / INT16 / INT8 FFN1 outputs vs the float model.
INT8 variants: (a) smallest no-saturation shift on training (same rule as INT16);
(b) per-column shift minimising training MSE (saturation allowed)."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "model"))
from reference import calibrate_layer, encode_layer, _scale

def rne(a, s):
    s = np.broadcast_to(np.asarray(s, dtype=np.int64), a.shape)
    mag = np.abs(a); q = mag >> s; r = mag - (q << s)
    half = np.where(s > 0, np.int64(1) << np.maximum(s - 1, 0), 0)
    up = (s > 0) & ((r > half) | ((r == half) & ((q & 1) == 1)))
    return np.sign(a) * (q + up)
def acc(x, w, b):
    return (x.astype(np.float64) @ w.astype(np.float64)).astype(np.int64) + b.astype(np.int64)
def min_shift(a, lo, hi):
    out = []
    for j in range(a.shape[1]):
        c = a[:, j]
        for s in range(48):
            r = rne(c, s)
            if r.max() <= hi and r.min() >= lo: out.append(s); break
    return np.array(out)
def mse_shift(a, lo, hi, f_of, yf):
    out = []
    for j in range(a.shape[1]):
        best = None
        for s in range(48):
            q = np.clip(rne(a[:, j], s), lo, hi) * f_of(j, s)
            e = np.mean((q - yf[:, j]) ** 2)
            if best is None or e < best[0]: best = (e, s)
        out.append(best[1])
    return np.array(out)

rows = []
for L in range(12):
    n = "layer%02d" % L
    tr = np.load(ROOT / f"model/full_v2_run/float_training/{n}.npz")
    va = np.load(ROOT / f"model/full_v2_run/float_validation/{n}.npz")
    cfg = calibrate_layer(tr["X"], tr["W"], tr["b"], L, role="training")
    tx, tw, tb, _ = encode_layer(tr["X"], tr["W"], tr["b"], cfg)
    ta = acc(tx, tw, tb).reshape(-1, 256)
    vx, vw, vb, _ = encode_layer(va["X"], va["W"], va["b"], cfg)
    va_acc = acc(vx, vw, vb).reshape(-1, 256); yf = va["Y"].astype(np.float64).reshape(-1, 256)
    tyf = tr["Y"].astype(np.float64).reshape(-1, 256)
    f_of = lambda j, s: _scale(cfg.x_exponent + cfg.w_exponents[j] + int(s))
    shifts = dict(int32=np.asarray(cfg.shifts), int16=min_shift(ta, -32768, 32767),
                  int8_nosat=min_shift(ta, -128, 127),
                  int8_mse=mse_shift(ta, -128, 127, f_of, tyf))
    rng = dict(int32=(-2**31, 2**31-1), int16=(-32768, 32767), int8_nosat=(-128, 127), int8_mse=(-128, 127))
    row = dict(layer=L)
    for t, s in shifts.items():
        lo, hi = rng[t]
        q = rne(va_acc, s); sat = float(((q < lo) | (q > hi)).mean() * 100); q = np.clip(q, lo, hi)
        f = np.array([f_of(j, s[j]) for j in range(256)])
        e = q * f - yf
        row[t] = dict(nrmse=float(np.sqrt(np.mean(e**2)) / np.sqrt(np.mean(yf**2)) * 100), sat_pct=sat,
                      cos=float(np.sum(q*f*yf) / np.sqrt(np.sum((q*f)**2) * np.sum(yf**2))))
    rows.append(row)
    print(n, "  ".join(f"{t}: {row[t]['nrmse']:.4f}% sat {row[t]['sat_pct']:.3f}%" for t in shifts), flush=True)
for t in ("int32", "int16", "int8_nosat", "int8_mse"):
    v = [r[t]["nrmse"] for r in rows]
    print(t, "mean %.4f%%  max %.4f%%" % (np.mean(v), np.max(v)))
json.dump(rows, open(sys.argv[2], "w"), indent=1)
