"""Check exact paired-product FFN identity; no RTL or PPA performance claim."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'model'))
import study_precision_bandwidth as numeric


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transformed(x, w, b):
    row = np.sum(x[..., 0::2]*x[..., 1::2], axis=-1)
    col = np.sum(w[0::2]*w[1::2], axis=0)
    result = b - row[..., None] - col
    peak = int(np.max(np.abs(result)))
    for k in range(0, w.shape[0], 2):
        result += (x[..., k, None] + w[k+1]) * (x[..., k+1, None] + w[k])
        peak = max(peak, int(np.max(np.abs(result))))
    return result, peak


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-run', type=Path, required=True)
    parser.add_argument('--precision-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = {'passed': False, 'schema': 'qingyu-exact-paired-product-study-v1',
              'created_utc': datetime.now(timezone.utc).isoformat(),
              'script_sha256': sha(Path(__file__)), 'layers': [],
              'direct_multiplications': 99*64*256,
              'paired_multiplications_including_hardware_factors': 99*32*256 + 99*32 + 256*32,
              'limits': ['No RTL, latency, timing, area, energy or official score result',
                         'All row/column factors must be computed by hardware in task window',
                         'Extra adders, widened intermediate arithmetic and factor storage required',
                         'Memory traffic does not decrease from this identity alone']}
    frozen = json.loads((args.precision_run/'frozen_config_sha256.json').read_text())
    study = json.loads((args.precision_run/'result.json').read_text())
    hashes = {(x['role'], x['layer']): x['sha256'] for x in study['inputs']}
    for layer in range(12):
        path = args.reference_run/'float_validation'/f'layer{layer:02d}.npz'
        cpath = args.precision_run/'x8_w8_y8_h0'/f'layer{layer:02d}.json'
        assert sha(path) == hashes['validation', layer]
        assert sha(cpath) == frozen[f'x8_w8_y8_h0/layer{layer:02d}.json']
        config = json.loads(cpath.read_text())
        data = numeric.load(path, 'validation')
        scale = np.exp2(config['w_exponents'])
        x, _ = numeric.quantize(data['X'][0], math.ldexp(1., config['x_exponent']), 8)
        w, _ = numeric.quantize(data['W'], scale, 8)
        b = np.rint(data['b']/(math.ldexp(1., config['x_exponent'])*scale)).astype(np.int64)
        direct = x @ w + b
        actual, peak = transformed(x, w, b)
        assert np.array_equal(actual, direct)
        assert np.all(np.abs(actual) < (1 << 47))
        result['layers'].append({'layer': layer, 'outputs_checked': actual.size,
                                 'intermediate_abs_peak': peak, 'config_sha256': sha(cpath),
                                 'data_sha256': sha(path)})
    rng = np.random.default_rng(20261111)
    for case in range(32):
        x = rng.integers(-128, 128, (3, 64), dtype=np.int64)
        w = rng.integers(-128, 128, (64, 16), dtype=np.int64)
        b = rng.integers(-(1<<30), 1<<30, 16, dtype=np.int64)
        actual, _ = transformed(x, w, b)
        assert np.array_equal(actual, x @ w + b)
    result['random_signed8_cases'] = 32
    result['passed'] = True
    result['meaning_of_passed'] = 'Exact integer identity checked on 12 complete model tasks and 32 independent signed corner/random cases'
    (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(args.output/'result.json')


if __name__ == '__main__':
    main()
