"""Lossless DEFLATE screening, with explicit read/write service assumptions.

This is a size experiment, not a proposed free/instantaneous hardware codec.
Raw/row-delta choice is fixed using training data before any validation load.
The numeric INT8 configuration remains the previously frozen configuration.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import zlib
import numpy as np
from analyze_lossless_command_budget import numeric, quantized, sha, symbols, undo_symbols


def encoded(value, delta, verify=False):
    data = symbols(value, delta)
    compressed = zlib.compress(data.tobytes(), level=9)
    if verify:
        decoded = np.frombuffer(zlib.decompress(compressed), dtype=np.uint8).reshape(data.shape)
        restored = undo_symbols(decoded, delta)
        assert np.array_equal(restored, (value & 255).astype(np.uint8))
    return (len(compressed)+3)//4


def frames(value):
    return value if value.ndim == 3 else [value]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-run', type=Path, required=True)
    parser.add_argument('--precision-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    study = json.loads((args.precision_run/'result.json').read_text())
    frozen = json.loads((args.precision_run/'frozen_config_sha256.json').read_text())
    inputs = {(x['role'], x['layer']): x['sha256'] for x in study['inputs']}
    policy = 'x8_w8_y8_h0'
    report = {'schema': 'qingyu-deflate-command-budget-v1', 'passed': False,
              'script_sha256': sha(Path(__file__)), 'helper_sha256': sha(Path(__file__).with_name('analyze_lossless_command_budget.py')),
              'created_utc': datetime.now(timezone.utc).isoformat(), 'fit_role': 'training',
              'numeric_policy': policy, 'zlib_version': zlib.ZLIB_VERSION, 'level': 9,
              'numeric_configuration_changed': False, 'legacy_metadata_words': 576,
              'header_words': 4, 'codebook_words': 0,
              'codebook_note': 'DEFLATE stream contains its own codebook/header/checksum; no external table omitted',
              'layers': [], 'limits': ['Compression CPU runtime is not simulated hardware speed',
                                      'No area, energy, STA, official-loader, or RTL performance claim',
                                      'Write-II1 is a candidate condition, not a completed protocol proof']}
    choices = {}
    for layer in range(12):
        cpath = args.precision_run/policy/f'layer{layer:02d}.json'
        assert sha(cpath) == frozen[f'{policy}/layer{layer:02d}.json']
        config = json.loads(cpath.read_text())
        path = args.reference_run/'float_training'/f'layer{layer:02d}.npz'
        assert sha(path) == inputs['training', layer]
        data = numeric.load(path, 'training')
        values = quantized(data, config)
        biases = np.rint(data['b'].astype(np.float64)/np.exp2(np.asarray(config['w_exponents'])+config['x_exponent'])).astype(np.int64)
        choices[layer] = {'delta': {}, 'training_words': {}, 'bias_signed32_fits': bool(np.all((biases >= -(1<<31)) & (biases < (1<<31)))),
                          'bias_min': int(biases.min()), 'bias_max': int(biases.max())}
        for key, value in zip(('x', 'w', 'y'), values):
            counts = [sum(encoded(v, delta) for v in frames(value)) for delta in (False, True)]
            choices[layer]['delta'][key] = counts[1] < counts[0]
            choices[layer]['training_words'][key] = counts
        print('Frozen DEFLATE choice', layer, flush=True)
    declared = args.output/'training_choices.json'
    declared.write_text(json.dumps(choices, indent=2)+'\n')
    declared_hash = sha(declared)
    for layer in range(12):
        config = json.loads((args.precision_run/policy/f'layer{layer:02d}.json').read_text())
        path = args.reference_run/'float_validation'/f'layer{layer:02d}.npz'
        assert sha(path) == inputs['validation', layer]
        values = quantized(numeric.load(path, 'validation'), config)
        counts = {key: np.asarray([encoded(v, choices[layer]['delta'][key], verify=True) for v in frames(value)])
                  for key, value in zip(('x', 'w', 'y'), values)}
        iw = counts['x'] + counts['w'][0] + 576 + 4
        yw = counts['y']
        samples = [{'sample_index': i, 'input_words': int(iw[i]), 'output_words': int(yw[i]),
                    'r2_w2_shared_preloaded': int(2*(iw[i]+yw[i])),
                    'r2_w1_shared_preloaded': int(2*iw[i]+yw[i]),
                    'r2_w1_loader_write_read_output': int(3*iw[i]+yw[i]),
                    'r2_w1_loader_capture_output': int(iw[i]+yw[i])} for i in range(len(iw))]
        entry = {'layer': layer, 'training_choice': choices[layer], 'samples': samples,
                 'input_words_mean': float(iw.mean()), 'output_words_mean': float(yw.mean())}
        report['layers'].append(entry)
        (args.output/'partial_result.json').write_text(json.dumps(report, indent=2)+'\n')
        print('DEFLATE validation', layer, entry['input_words_mean'], entry['output_words_mean'], flush=True)
    assert sha(declared) == declared_hash
    keys = ['r2_w2_shared_preloaded', 'r2_w1_shared_preloaded', 'r2_w1_loader_write_read_output', 'r2_w1_loader_capture_output']
    report['summary'] = {}
    for key in keys:
        values = np.asarray([s[key] for layer in report['layers'] for s in layer['samples']])
        report['summary'][key] = {'ideal_cycles_mean': float(values.mean()), 'ideal_cycles_max': int(values.max()),
                                  'ideal_task_s_upper_bound_mean': 150e6/float(values.mean()),
                                  'samples_meeting_cycle_budget_without_compute_or_control': int(np.count_nonzero(values < 150e6/10450)),
                                  'samples': len(values)}
    report['training_choices_sha256'] = declared_hash
    report['passed'] = True
    report['meaning_of_passed'] = 'All source identities and all validation stream lossless round-trips passed; no hardware/PPA acceptance.'
    (args.output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report['summary'], indent=2), flush=True)


if __name__ == '__main__':
    main()
