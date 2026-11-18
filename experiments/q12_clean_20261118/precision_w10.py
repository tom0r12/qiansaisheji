"""Precision study: X12/W12/Y13 (frozen) vs X12/W10/Y13 (w10=sat10(RNE(w/4)), b'=RNE(b/4), s'=s-2).

Uses the local 600 testing-partition float references (not the organizer set).
Fixed conversion rule; no refit. Pooled per-layer NRMSE as in the scoring rule.
"""
from pathlib import Path
import json, math, sys
import numpy as np
RUN = Path(r'E:/Desktop/qiansaisheji/output/eda/q12_dense_output_20261113/precision600/runs/20261113T054543132846Z')
sys.path.insert(0, str(RUN / 'frozen'))
import study_precision_bandwidth as numeric
import fixed_reference as fixed


def rne_div(v, k):
    """Round-half-even of v / 2^k (integers)."""
    v = np.asarray(v, dtype=np.int64); s = np.full(v.shape, k, dtype=np.int64)
    mag = np.abs(v); q = mag >> s; rem = mag & ((1 << k) - 1); half = 1 << (k - 1)
    inc = (rem > half) | ((rem == half) & ((q & 1) != 0))
    return np.where(v < 0, -(q + inc), q + inc)


def requant(acc, shifts):
    return fixed.requantize(acc, shifts)


def main(samples=600, variants=('w12', 'w10')):
    res = {v: [] for v in variants}
    for layer in range(12):
        data = numeric.load(RUN / 'float_testing' / f'layer{layer:02d}.npz', 'testing')
        cfg = json.loads((RUN / 'frozen' / f'layer{layer:02d}.json').read_text())
        sw = np.exp2(np.asarray(cfg['w_exponents'], dtype=np.float64))
        w, _ = numeric.quantize(data['W'], sw, 12)
        bias = np.rint(data['b'].astype(np.float64) / (2. ** cfg['x_exponent'] * sw)).astype(np.int64)
        shifts = np.asarray(cfg['shifts'], dtype=np.int64)
        scales = np.exp2(cfg['x_exponent'] + np.asarray(cfg['w_exponents']) + shifts)
        w10 = np.clip(rne_div(w, 2), -512, 511); b10 = rne_div(bias, 2); s10 = shifts - 2
        assert np.all(s10 >= 0)
        X = np.stack([numeric.quantize(data['X'][i], 2. ** cfg['x_exponent'], 12)[0] for i in range(samples)])
        ref = data['Y'][:samples].astype(np.float64)
        for v in variants:
            if v == 'w12': y = requant(np.einsum('nij,jk->nik', X, w) + bias, shifts)
            else: y = requant(np.einsum('nij,jk->nik', X, w10) + b10, s10)
            out = y.astype(np.float64) * scales
            e = float(np.sum((out - ref) ** 2)); r = float(np.sum(ref ** 2)); n = out.size
            res[v].append(math.sqrt(e / n) / max(math.sqrt(r / n), 1e-8) * 100)
        print(layer, {v: round(res[v][-1], 5) for v in variants}, flush=True)
    summary = {v: {'per_layer': res[v], 'max': max(res[v]), 'score': max(0, 10 - max(res[v]) / 0.3)} for v in variants}
    print(json.dumps(summary, indent=1))
    Path(__file__).with_suffix('.json').write_text(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
