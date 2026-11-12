"""Artifact integrity and cold-buffer layout for the validation-task exporter."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

try:
    from .reference import LayerConfig, export_layer_vectors, weight_digest
except ImportError:
    from reference import LayerConfig, export_layer_vectors, weight_digest


class SocImageTests(unittest.TestCase):
    def test_complete_export_and_reject_changed_frozen_task(self):
        # Synthetic temporary artifacts test packaging, not model accuracy.
        script = Path(__file__).with_name('export_soc_task_images.py')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            vectors = root / 'vectors'
            train_ids, val_ids = [f'train-{i}' for i in range(12)], [f'val-{i}' for i in range(12)]
            records = []
            for layer in range(12):
                target = vectors / f'layer{layer:02d}'
                x, w = np.zeros((99, 64), dtype=np.int16), np.zeros((64, 256), dtype=np.int16)
                b, shifts = np.ones(256, dtype=np.int64), np.zeros(256, dtype=np.int64)
                y = np.ones((99, 256), dtype=np.int16)
                export_layer_vectors(target, x, w, b, shifts, y, lanes=16, output_bits=16)
                cfg = LayerConfig(layer, 0, [0] * 256, shifts.tolist(), weight_digest(w, b),
                                  format_version='qingyu-fixed-v2', output_bits=16)
                config = target / 'frozen_training_config.json'
                config.write_text(json.dumps(cfg.as_dict()))
                records.append({'layer': layer, 'config_sha256': hashlib.sha256(config.read_bytes()).hexdigest(),
                                'chosen_tasks': [{'sample_id': val_ids[layer], 'label': layer,
                                    'integer_case_sha256': hashlib.sha256((target / 'integer_case.npz').read_bytes()).hexdigest()}]})
            report = {'kind': 'FROZEN_TRAINING_DISJOINT_VALIDATION_SUBSET', 'scope': 'synthetic unit test',
                      'sample_sets_disjoint': True, 'numerical_configuration_fit_role': 'training',
                      'output_bits': 16, 'layer_diagnostics': records, 'training_sample_ids': train_ids,
                      'validation_sample_ids': val_ids, 'training_samples': 12, 'validation_samples': 12,
                      'source_commit': 'synthetic-unit-test', 'subset_accuracy': {'max_nrmse': 0.0}}
            (vectors / 'validation_report.json').write_text(json.dumps(report))
            command = [sys.executable, str(script), '--vectors', str(vectors), '--output', str(root / 'images')]
            subprocess.run(command, check=True, capture_output=True)
            image = np.array([int(x, 16) for x in (root / 'images/layer00/shared.hex').read_text().split()])
            self.assertEqual(image.size, 131072)
            self.assertTrue(np.all(image[:0x40000 // 4] == 0))
            self.assertEqual(int(image[(0x40000 + 0xc000) // 4]), 1)
            expected = (root / 'images/layer00/expected.hex').read_text().split()
            self.assertEqual(len(expected), 12672)
            self.assertEqual(set(expected), {'00010001'})
            with (vectors / 'layer00/integer_case.npz').open('ab') as stream:
                stream.write(b'changed-after-validation')
            changed = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(changed.returncode, 0)
            self.assertIn('integer task changed after validation', changed.stderr)


if __name__ == '__main__':
    unittest.main()
