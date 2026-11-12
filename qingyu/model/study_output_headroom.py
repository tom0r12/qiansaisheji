"""Compare a globally fixed training-calibrated OUT16 headroom policy.

The candidate policy is fixed before evaluation; there is no per-layer or
validation-driven shift search. The existing baseline artifacts are read only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

try:
    from .reference import LayerConfig, NrmseAccumulator, accumulate, decode_layer, encode_layer, requantize
except ImportError:
    from reference import LayerConfig, NrmseAccumulator, accumulate, decode_layer, encode_layer, requantize


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(arguments: list[str], log: Path) -> None:
    with log.open('w', encoding='utf-8') as stream:
        subprocess.run([sys.executable, '-u', *arguments], stdout=stream, stderr=subprocess.STDOUT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--headroom-bits', type=int, choices=[1], default=1)
    args = parser.parse_args()
    source, out = args.reference_run.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    scripts = Path(__file__).resolve().parent
    baseline_path = source / 'validation_vectors_out16/validation_report.json'
    baseline_sha = digest(baseline_path)
    baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
    if baseline.get('output_bits') != 16 or baseline.get('output_headroom_bits', 0) != 0:
        raise ValueError('Expected the unmodified OUT16 zero-headroom baseline')
    candidate_dir = out / 'validation_vectors_out16'
    print('Validating fixed +1 bit candidate from training-only calibration', flush=True)
    run([str(scripts / 'validate_extracted.py'), '--training', str(source / 'float_training'),
         '--validation', str(source / 'float_validation'), '--output', str(candidate_dir),
         '--output-bits', '16', '--output-headroom-bits', '1', '--lanes', '16',
         '--choose-by-layer-label', '--scope',
         'Globally fixed +1 bit output headroom, training-only calibration; disjoint local validation, not official 600'],
        out / 'validation.log')
    candidate_path = candidate_dir / 'validation_report.json'
    candidate = json.loads(candidate_path.read_text(encoding='utf-8'))
    for key in ('training_sample_ids', 'validation_sample_ids', 'source_commit'):
        if candidate[key] != baseline[key]:
            raise ValueError(f'Comparison changed {key}')
    training_metrics = {name: NrmseAccumulator() for name in ('baseline', 'headroom1')}
    saturation = {name: 0 for name in training_metrics}
    layers = []
    for layer in range(12):
        name = f'layer{layer:02d}'
        base_path = source / 'validation_vectors_out16' / name / 'frozen_training_config.json'
        extra_path = candidate_dir / name / 'frozen_training_config.json'
        base = LayerConfig.from_dict(json.loads(base_path.read_text(encoding='utf-8')))
        extra = LayerConfig.from_dict(json.loads(extra_path.read_text(encoding='utf-8')))
        if (extra.shifts != [s + 1 for s in base.shifts]
                or extra.x_exponent != base.x_exponent or extra.w_exponents != base.w_exponents
                or extra.weights_sha256 != base.weights_sha256
                or extra.output_bits != base.output_bits or extra.output_headroom_bits != 1):
            raise ValueError(f'{name}: candidate changed more than the fixed output headroom')
        training_path = source / 'float_training' / (name + '.npz')
        with np.load(training_path, allow_pickle=False) as archive:
            arrays = {key: archive[key] for key in archive.files}
        if str(arrays['split'].item()) != 'training':
            raise ValueError('Training metric source has incorrect split')
        qx, qw, qb, _ = encode_layer(arrays['X'], arrays['W'], arrays['b'], base)
        a = accumulate(qx, qw, qb)
        for tag, cfg in (('baseline', base), ('headroom1', extra)):
            y, count = requantize(a, cfg.shifts, output_bits=16)
            training_metrics[tag].update(layer, arrays['Y'], decode_layer(y, cfg))
            saturation[tag] += count
        layers.append({'layer': layer, 'baseline_config_sha256': digest(base_path),
                       'candidate_config_sha256': digest(extra_path),
                       'training_source_sha256': digest(training_path),
                       'shift_delta_min': min(e-b for e,b in zip(extra.shifts,base.shifts)),
                       'shift_delta_max': max(e-b for e,b in zip(extra.shifts,base.shifts))})
        print(f'Training comparison layer {layer} complete', flush=True)
    result = {'policy': 'Every channel of every layer gets exactly one extra output shift bit',
              'parameter_fit_split': 'training', 'validation_parameter_search': False,
              'official_600_sample_evaluation': False, 'rtl_changed': False,
              'output_bits': 16, 'task_output_bytes': 50688, 'layers': layers,
              'baseline_validation_sha256': baseline_sha, 'candidate_validation_sha256': digest(candidate_path),
              'training': {tag: dict(metric.summary(require_all_layers=True), saturation_count=saturation[tag])
                           for tag, metric in training_metrics.items()},
              'validation': {}}
    for tag, report in (('baseline', baseline), ('headroom1', candidate)):
        nrmse = report['subset_accuracy']['max_nrmse']
        result['validation'][tag] = {
            'max_nrmse': nrmse, 'nrmse_percent': nrmse * 100,
            'output_saturation_count': sum(x['output_saturation_count'] for x in report['layer_diagnostics']),
            'local_score_formula_only': max(0.0, 10 - nrmse / 0.003),
            'max_selected_task_nrmse': max(x['chosen_tasks'][0]['nrmse'] for x in report['layer_diagnostics'])}
    result['validation_improved'] = (result['validation']['headroom1']['max_nrmse']
                                    < result['validation']['baseline']['max_nrmse'])
    if digest(baseline_path) != baseline_sha:
        raise ValueError('Baseline validation report changed during comparison')
    (out / 'headroom_comparison.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    if (result['validation_improved'] and result['training']['headroom1']['meets_3_percent_threshold']
            and candidate['subset_accuracy']['meets_3_percent_threshold']):
        run([str(scripts / 'export_soc_task_images.py'), '--vectors', str(candidate_dir),
             '--output', str(out / 'soc_images_out16'), '--expect-output-bits', '16'], out / 'export.log')
    print(json.dumps({'report': str(out / 'headroom_comparison.json'),
                      'validation_improved': result['validation_improved'], 'validation': result['validation']}), flush=True)


if __name__ == '__main__':
    main()
