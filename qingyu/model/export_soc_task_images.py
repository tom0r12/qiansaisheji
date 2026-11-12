"""Export verified, selected KWT validation vectors to cold-task SoC images.

Only the upper shared-SRAM staging region is initialized; live buffers are
zero. No computation is moved to the decoder or task-loading firmware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

try:
    from .reference import LayerConfig, output_words, qlinear_int, write_hex_words
except ImportError:
    from reference import LayerConfig, output_words, qlinear_int, write_hex_words


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vectors', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-output-bits', type=int, choices=[16, 32], default=16)
    args = parser.parse_args()
    report_path = args.vectors / 'validation_report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if (report.get('kind') != 'FROZEN_TRAINING_DISJOINT_VALIDATION_SUBSET'
            or not report.get('sample_sets_disjoint')
            or report.get('numerical_configuration_fit_role') != 'training'):
        raise ValueError('Expected disjoint validation evidence with training-only frozen calibration')
    if report.get('output_bits', 32) != args.expect_output_bits:
        raise ValueError('Validation output width does not match the requested SoC format')
    diagnostics = {record['layer']: record for record in report['layer_diagnostics']}
    if set(diagnostics) != set(range(12)):
        raise ValueError('All 12 layer tasks are required')
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for layer in range(12):
        name = f'layer{layer:02d}'
        source = args.vectors / name
        config_path = source / 'frozen_training_config.json'
        config = LayerConfig.from_dict(json.loads(config_path.read_text(encoding='utf-8')))
        if (config.layer != layer or config.output_bits != args.expect_output_bits
                or config.output_headroom_bits != report.get('output_headroom_bits', 0)):
            raise ValueError(f'{name}: configuration does not match the selected layer/format')
        if diagnostics[layer].get('config_sha256') != digest(config_path):
            raise ValueError(f'{name}: frozen configuration changed after validation')
        chosen = diagnostics[layer]['chosen_tasks']
        if len(chosen) != 1 or chosen[0]['sample_id'] not in report['validation_sample_ids']:
            raise ValueError(f'{name}: expected one identified validation task')
        if chosen[0]['sample_id'] in report['training_sample_ids']:
            raise ValueError(f'{name}: task overlaps the calibration subset')
        integer_path = source / 'integer_case.npz'
        if chosen[0].get('integer_case_sha256') != digest(integer_path):
            raise ValueError(f'{name}: integer task changed after validation')
        with np.load(integer_path, allow_pickle=False) as case:
            x, w, b, shifts, expected = (case[key] for key in ('qx', 'qw', 'qb', 'shifts', 'qy'))
            if int(case['output_bits']) != config.output_bits:
                raise ValueError(f'{name}: integer vector output width changed')
        if (x.shape != (99, 64) or w.shape != (64, 256) or b.shape != (256,)
                or shifts.shape != (256,) or expected.shape != (99, 256)):
            raise ValueError(f'{name}: task dimensions do not match the contest')
        if not np.array_equal(shifts, config.shifts):
            raise ValueError(f'{name}: task shifts differ from the frozen format')
        result = qlinear_int(x, w, b, shifts, output_bits=config.output_bits)
        if not np.array_equal(result.output, expected):
            raise ValueError(f'{name}: expected outputs do not match the integer input task')
        image = bytearray(512 * 1024)
        for offset, values, dtype in ((0, x, '<i2'), (0x4000, w, '<i2'),
                                     (0xc000, b, '<i8'), (0xc800, shifts, 'u1')):
            raw = np.asarray(values, dtype=dtype).tobytes()
            image[0x40000 + offset:0x40000 + offset + len(raw)] = raw
        out = args.output / name
        out.mkdir(parents=True, exist_ok=True)
        write_hex_words(out / 'shared.hex', np.frombuffer(image, dtype='<u4'))
        write_hex_words(out / 'expected.hex', output_words(expected, output_bits=config.output_bits))
        (out / 'config.json').write_bytes(config_path.read_bytes())
        records.append({'layer': layer, 'chosen_task': chosen[0], 'output_bits': config.output_bits,
                        'integer_case_sha256': digest(integer_path), 'config_sha256': digest(config_path),
                        'files': {f: digest(out / f) for f in ('shared.hex', 'expected.hex', 'config.json')}})
    manifest = {'data_kind': 'KWT_VALIDATION', 'source_commit': report['source_commit'],
                'official_600_sample_evaluation': False, 'output_bits': args.expect_output_bits,
                'output_headroom_bits': report.get('output_headroom_bits', 0),
                'training_samples': report['training_samples'], 'validation_samples': report['validation_samples'],
                'source_validation_report': str(report_path.resolve()),
                'source_validation_report_sha256': digest(report_path),
                'subset_accuracy': report['subset_accuracy'], 'layers': records}
    (args.output / 'images_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'result': 'exported_validation_tasks', 'layers': 12, 'output_bits': args.expect_output_bits,
                      'output': str(args.output.resolve()), 'official_600_sample_evaluation': False}))


if __name__ == '__main__':
    main()
