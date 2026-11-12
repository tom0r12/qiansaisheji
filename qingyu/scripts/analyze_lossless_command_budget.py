"""Measure a training-frozen lossless codec's command budget, not RTL speed.

No numeric configuration is changed. Per-layer byte Huffman tables and the
choice of raw bytes versus preceding-row modular deltas use training only.
All 256 code lengths per stream are charged as cold metadata, including the
output encoder table. Every encoded stream is padded to a complete bus word.
"""
from __future__ import annotations
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
os.environ.setdefault('OMP_NUM_THREADS', '2')
import argparse
from datetime import datetime, timezone
import hashlib
import heapq
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'model'))
import study_precision_bandwidth as numeric


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def symbols(values, delta):
    values = np.asarray(values, dtype=np.int16)
    if not delta:
        return (values & 255).astype(np.uint8)
    result = values.copy()
    result[..., 1:, :] = values[..., 1:, :] - values[..., :-1, :]
    return (result & 255).astype(np.uint8)


def undo_symbols(encoded, delta):
    if not delta:
        return encoded
    return (np.cumsum(encoded.astype(np.int64), axis=-2) & 255).astype(np.uint8)


def lengths_for(counts):
    # A nonzero pseudocount ensures held-out symbols always have a code.
    heap = [(int(n)+1, i, [i]) for i, n in enumerate(counts)]
    heapq.heapify(heap)
    lengths = np.zeros(256, dtype=np.int64)
    serial = 256
    while len(heap) > 1:
        a, _, sa = heapq.heappop(heap)
        b, _, sb = heapq.heappop(heap)
        merged = sa + sb
        lengths[merged] += 1
        heapq.heappush(heap, (a+b, serial, merged))
        serial += 1
    return lengths


def canonical(lengths):
    code = 0
    previous = 0
    answer = {}
    for symbol in sorted(range(256), key=lambda x: (int(lengths[x]), x)):
        length = int(lengths[symbol])
        code <<= length-previous
        answer[symbol] = (code, length)
        code += 1
        previous = length
    return answer


def check_roundtrip(values, delta, lengths):
    source = symbols(values, delta)
    codes = canonical(lengths)
    reverse = {(n, c): symbol for symbol, (c, n) in codes.items()}
    bits = ''.join(format(codes[int(v)][0], '0%db' % codes[int(v)][1])
                   for v in source.ravel())
    decoded = []
    code = length = 0
    for bit in bits:
        code = (code << 1) | (bit == '1')
        length += 1
        key = (length, code)
        if key in reverse:
            decoded.append(reverse[key])
            code = length = 0
    assert length == 0 and len(decoded) == source.size
    restored = undo_symbols(np.asarray(decoded, dtype=np.uint8).reshape(source.shape), delta)
    assert np.array_equal(restored, (values & 255).astype(np.uint8))
    assert len(bits) == int(lengths[source].sum())


def quantized(data, config):
    x, _ = numeric.quantize(data['X'], math.ldexp(1., config['x_exponent']), 8)
    w, _ = numeric.quantize(data['W'], np.exp2(config['w_exponents']), 8)
    a, _, _ = numeric.encode(data, config)
    y = np.empty(a.shape, dtype=np.int64)
    for j, shift in enumerate(config['shifts']):
        y[..., j] = np.clip(numeric.rounded(a[..., j], shift), -128, 127)
    return x, w, y


def train_codec(values):
    options = []
    for delta in (False, True):
        transformed = symbols(values, delta)
        counts = np.bincount(transformed.ravel(), minlength=256)
        lengths = lengths_for(counts)
        options.append((int(counts @ lengths), delta, lengths))
    bits, delta, lengths = min(options, key=lambda x: (x[0], x[1]))
    return {'row_delta': delta, 'lengths': lengths.tolist(),
            'training_bits': bits, 'training_symbols': int(values.size)}


def words(values, codec):
    transformed = symbols(values, codec['row_delta'])
    lengths = np.asarray(codec['lengths'])
    axes = tuple(range(1, values.ndim))
    bits = lengths[transformed].sum(axis=axes) if values.ndim == 3 else lengths[transformed].sum()
    return (np.asarray(bits, dtype=np.int64) + 31) // 32


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-run', type=Path, required=True)
    parser.add_argument('--precision-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    study = json.loads((args.precision_run/'result.json').read_text())
    frozen = json.loads((args.precision_run/'frozen_config_sha256.json').read_text())
    input_hashes = {(x['role'], x['layer']): x['sha256'] for x in study['inputs']}
    policy = 'x8_w8_y8_h0'
    report = {'schema': 'qingyu-lossless-command-budget-v1', 'passed': False,
              'created_utc': datetime.now(timezone.utc).isoformat(),
              'script_sha256': sha(Path(__file__)), 'source_study_sha256': sha(args.precision_run/'result.json'),
              'numeric_policy': policy, 'numeric_config_unchanged': True,
              'fit_role': 'training', 'codec': 'canonical byte Huffman, optional modular preceding-row delta',
              'cold_codebook_words': 192, 'stream_header_words': 4,
              'legacy_numeric_metadata_words': 576, 'layers': [],
              'limits': ['No RTL codec, timing, area, energy, or official-loader result',
                         'Static entropy coding only; no arithmetic is delegated to the decoder',
                         'Codec chosen on training; validation used only for command-count assessment',
                         'II=2 bounds are conditional until original-fabric protocol evidence is reviewed']}
    codecs = {}
    for layer in range(12):
        config_path = args.precision_run/policy/f'layer{layer:02d}.json'
        assert sha(config_path) == frozen[f'{policy}/layer{layer:02d}.json']
        config = json.loads(config_path.read_text())
        path = args.reference_run/'float_training'/f'layer{layer:02d}.npz'
        assert sha(path) == input_hashes['training', layer]
        values = quantized(numeric.load(path, 'training'), config)
        codecs[layer] = {key: train_codec(v) for key, v in zip(('x', 'w', 'y'), values)}
        (args.output/f'codec_layer{layer:02d}.json').write_text(json.dumps(codecs[layer], indent=2)+'\n')
        print('Frozen training codec', layer, flush=True)
    codec_hashes = {p.name: sha(p) for p in args.output.glob('codec_layer*.json')}
    for layer in range(12):
        config_path = args.precision_run/policy/f'layer{layer:02d}.json'
        config = json.loads(config_path.read_text())
        path = args.reference_run/'float_validation'/f'layer{layer:02d}.npz'
        assert sha(path) == input_hashes['validation', layer]
        values = quantized(numeric.load(path, 'validation'), config)
        x, w, y = values
        for key, v in zip(('x', 'w', 'y'), values):
            first = v[0] if v.ndim == 3 else v
            check_roundtrip(first, codecs[layer][key]['row_delta'], np.asarray(codecs[layer][key]['lengths']))
        xw = words(x, codecs[layer]['x']); ww = int(words(w, codecs[layer]['w'])); yw = words(y, codecs[layer]['y'])
        iw = xw + ww + 576 + 192 + 4
        one_pass = iw + yw
        reread = 2*iw + yw
        item = {'layer': layer, 'samples': len(x), 'weight_words': ww,
                'row_delta': {k: v['row_delta'] for k, v in codecs[layer].items()},
                'samples_commands': [{'sample_index': i, 'input_words': int(iw[i]),
                                      'output_words': int(yw[i]), 'one_pass_words': int(one_pass[i]),
                                      'initial_write_reread_output_words': int(reread[i])} for i in range(len(x))],
                'one_pass_min': int(one_pass.min()), 'one_pass_max': int(one_pass.max()),
                'one_pass_mean': float(one_pass.mean()),
                'ii2_task_s_upper_bound_using_mean': 150e6/(2*float(one_pass.mean()))}
        report['layers'].append(item)
        (args.output/'partial_result.json').write_text(json.dumps(report, indent=2)+'\n')
        print('Validation', layer, 'words mean/max', item['one_pass_mean'], item['one_pass_max'], flush=True)
    assert codec_hashes == {p.name: sha(p) for p in args.output.glob('codec_layer*.json')}
    report['codec_sha256'] = codec_hashes
    report['passed'] = True
    report['meaning_of_passed'] = 'All source identities checked, frozen codecs retained, and one full task/stream per layer round-tripped losslessly; not a performance acceptance.'
    report['overall_mean_one_pass_words'] = float(np.mean([r['one_pass_mean'] for r in report['layers']]))
    report['ii2_task_s_upper_bound_from_mean'] = 150e6/(2*report['overall_mean_one_pass_words'])
    report['max_observed_task_words'] = max(r['one_pass_max'] for r in report['layers'])
    (args.output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(args.output/'result.json', flush=True)


if __name__ == '__main__':
    main()
