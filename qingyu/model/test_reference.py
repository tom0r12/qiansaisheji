"""Meaningful fixed-point and transport tests; no TensorFlow needed."""

import json
import tempfile
import unittest
from pathlib import Path
import subprocess
import sys
import numpy as np
try:
    from . import reference as ref
except ImportError:
    import reference as ref


class ReferenceTests(unittest.TestCase):
    def test_signed_ties_even_and_half_neighbours(self):
        cases = {1: 0, 3: 2, 5: 2, 7: 4, -1: 0, -3: -2, -5: -2, -7: -4}
        for value, expected in cases.items():
            self.assertEqual(ref.round_shift_rne(value, 1), expected)
        for shift in range(1, 48):
            unit = 1 << shift
            for quotient in (0, 1, 2, 5):
                for sign in (-1, 1):
                    halfway = quotient * unit + unit // 2
                    expected = quotient + (quotient & 1)
                    self.assertEqual(ref.round_shift_rne(sign * halfway, shift), sign * expected)
                    if shift > 1:
                        self.assertEqual(ref.round_shift_rne(sign * (halfway - 1), shift), sign * quotient)
                        self.assertEqual(ref.round_shift_rne(sign * (halfway + 1), shift), sign * (quotient + 1))
        self.assertEqual(ref.round_shift_rne(ref.ACC_MIN, 47), -1)
        self.assertEqual(ref.round_shift_rne(ref.ACC_MAX, 47), 1)
        self.assertEqual(ref.round_shift_rne(-123, 0), -123)
        with self.assertRaises(ValueError):
            ref.round_shift_rne(1, 48)

    def test_output_saturation_is_after_rounding(self):
        a = np.array([[ref.I32_MAX, ref.I32_MAX + 1, ref.I32_MIN, ref.I32_MIN - 1],
                      [2 * ref.I32_MAX + 1, 2 * ref.I32_MAX + 2, 2 * ref.I32_MIN - 1, 2 * ref.I32_MIN - 2]])
        y, count = ref.requantize(a, [0, 1, 0, 1])
        self.assertEqual(count, 4)
        np.testing.assert_array_equal(y[0], [ref.I32_MAX, 1073741824, ref.I32_MIN, -1073741824])
        np.testing.assert_array_equal(y[1], [ref.I32_MAX, ref.I32_MAX, ref.I32_MIN, ref.I32_MIN])
        midpoint, midpoint_count = ref.requantize([[2 * ref.I32_MAX + 1]], [1])
        self.assertEqual(int(midpoint[0, 0]), ref.I32_MAX)
        self.assertEqual(midpoint_count, 1)

    def test_dot_matches_independent_python_integer_loop(self):
        rng = np.random.default_rng(7)
        x = rng.integers(-32768, 32768, (3, 7), dtype=np.int16)
        w = rng.integers(-32768, 32768, (7, 5), dtype=np.int16)
        b = np.array([-3, 4, -(1 << 42), 1 << 42, 0], dtype=np.int64)
        shifts = [0, 1, 12, 47, 3]
        result = ref.qlinear_int(x, w, b, shifts)
        for t in range(3):
            for j in range(5):
                integer = int(b[j])
                for k in range(7):
                    integer += int(x[t, k]) * int(w[k, j])
                expected = max(ref.I32_MIN, min(ref.I32_MAX, ref.round_shift_rne(integer, shifts[j])))
                self.assertEqual(int(result.accumulators[t, j]), integer)
                self.assertEqual(int(result.output[t, j]), expected)

    def test_transient_accumulator_overflow_is_not_hidden_by_cancellation(self):
        # Final mathematical sum fits but the first MAC would overflow hardware.
        with self.assertRaises(OverflowError):
            ref.qlinear_int([[2, -2]], [[1], [1]], [ref.ACC_MAX - 1], [1])
        with self.assertRaises(OverflowError):
            ref.qlinear_int([[-2]], [[1]], [ref.ACC_MIN + 1], [1])
        self.assertEqual(int(ref.qlinear_int([[0]], [[0]], [ref.ACC_MIN], [47]).output[0, 0]), -1)

    def test_bad_shapes_types_and_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            ref.accumulate([[1, 2]], [[1]], [0])
        with self.assertRaises(TypeError):
            ref.accumulate([[1.0]], [[1]], [0])
        with self.assertRaises(OverflowError):
            ref.accumulate([[32768]], [[1]], [0])
        with self.assertRaises(ValueError):
            ref.quantize_symmetric16([np.nan], 1)
        with self.assertRaises(ValueError):
            ref.quantize_symmetric16([0.0], 0)

    def test_symmetric_quantizer_ties_and_zero_channel(self):
        np.testing.assert_array_equal(ref.quantize_symmetric16([-.5, -1.5, -2.5, .5, 1.5, 2.5, 1e9, -1e9], 1),
                                      [0, -2, -2, 0, 2, 2, 32767, -32767])
        self.assertEqual(ref.power2_scale_exponent(0), 0)
        for value in (1e-20, 1.0, 32767.0, 32768.0, 1e20):
            scale = 2.0 ** ref.power2_scale_exponent(value)
            self.assertLessEqual(value / scale, 32767)

    def test_calibration_roundtrip_and_frozen_weights(self):
        rng = np.random.default_rng(19)
        x = rng.normal(size=(3, 5, 7))
        w = rng.normal(size=(7, 8))
        w[:, 0] = 0
        b = rng.normal(size=8)
        b[0] = 0
        config = ref.calibrate_layer(x, w, b, 2, role="training")
        reloaded = ref.LayerConfig.from_dict(json.loads(json.dumps(config.as_dict())))
        qx, qw, qb, shifts = ref.encode_layer(x, w, b, reloaded)
        result = ref.qlinear_int(qx, qw, qb, shifts)
        decoded = ref.decode_layer(result.output, reloaded)
        self.assertEqual(result.saturation_count, 0)
        self.assertLess(np.linalg.norm(decoded - (x @ w + b)) / np.linalg.norm(x @ w + b), 0.0002)
        self.assertEqual(config.w_exponents[0], 0)
        with self.assertRaises(ValueError):
            ref.calibrate_layer(x, w, b, 2, role="testing")
        changed = w.copy()
        changed[0, 1] += 1e-6
        with self.assertRaises(ValueError):
            ref.encode_layer(x, changed, b, reloaded)

    def test_little_endian_int16_and_bias48_metadata(self):
        values = np.array([-32768, -1, 0, 1, 32767], dtype=np.int16)
        words = ref.pack_int16_words(values)
        self.assertEqual(int(words[0]), 0xFFFF8000)
        self.assertEqual(int(words[1]), 0x00010000)
        np.testing.assert_array_equal(ref.unpack_int16_words(words, 5), values)
        b = np.array([ref.ACC_MIN, -1, 0, ref.ACC_MAX], dtype=np.int64)
        r = np.array([47, 1, 0, 3])
        meta = ref.pack_meta_words(b, r)
        self.assertEqual(int(meta[1]), 0x002F8000)
        self.assertEqual(int(meta[3]), 0x0001FFFF)
        got_b, got_r = ref.unpack_meta_words(meta)
        np.testing.assert_array_equal(got_b, b)
        np.testing.assert_array_equal(got_r, r)
        meta[1] |= 0x01000000
        with self.assertRaises(ValueError):
            ref.unpack_meta_words(meta)

    def test_vector_export_tile_order_and_hex_roundtrip(self):
        x = np.arange(12, dtype=np.int16).reshape(3, 4) - 6
        w = np.arange(32, dtype=np.int16).reshape(4, 8) - 16
        b, r = np.arange(8, dtype=np.int64), np.zeros(8, dtype=np.int64)
        y = ref.qlinear_int(x, w, b, r).output
        with tempfile.TemporaryDirectory() as folder:
            manifest = ref.export_layer_vectors(folder, x, w, b, r, y, lanes=4)
            got_w = ref.unpack_int16_words(ref.read_hex_words(Path(folder) / "w_tile_words.hex")).reshape(2, 4, 4)
            np.testing.assert_array_equal(got_w[0], w[:, :4])
            np.testing.assert_array_equal(got_w[1], w[:, 4:])
            got_y = ref.read_hex_words(Path(folder) / "y_tile_words.hex").view(np.int32).reshape(2, 3, 4)
            np.testing.assert_array_equal(got_y[0], y[:, :4])
            np.testing.assert_array_equal(got_y[1], y[:, 4:])
            self.assertEqual(manifest["output_words_per_tile"], 12)

    def test_nrmse_uses_global_sums_not_mean_sample_ratios(self):
        acc = ref.NrmseAccumulator()
        acc.update(0, [1.0], [2.0])
        acc.update(0, [100.0], [100.0])
        expected = 1.0 / np.sqrt(10001.0)
        self.assertAlmostEqual(acc.summary()["max_nrmse"], expected)
        zeros = ref.NrmseAccumulator()
        zeros.update(1, [0.0], [1e-10])
        self.assertAlmostEqual(zeros.summary()["max_nrmse"], 0.01)
        with self.assertRaises(ValueError):
            acc.summary(require_all_layers=True)
        for layer in range(1, 12):
            acc.update(layer, [1.0], [1.0])
        self.assertEqual(len(acc.summary(require_all_layers=True)["layers"]), 12)

    def test_npz_cli_uses_training_config_for_separate_validation(self):
        rng = np.random.default_rng(103)
        w, b = rng.normal(size=(4, 8)), rng.normal(size=8)
        train = rng.normal(size=(2, 3, 4))
        validation = rng.normal(size=(2, 3, 4)) * 0.5
        script = Path(__file__).with_name("prepare_layer.py")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            np.savez(path / "train.npz", X=train, W=w, b=b, split=np.array("training"))
            np.savez(path / "validation.npz", X=validation, W=w, b=b,
                     Y=validation @ w + b, split=np.array("validation"))
            subprocess.run([sys.executable, str(script), "calibrate", "--input", str(path / "train.npz"),
                            "--split", "training", "--layer", "0", "--output", str(path / "config.json")],
                           check=True, capture_output=True, text=True)
            before = (path / "config.json").read_bytes()
            subprocess.run([sys.executable, str(script), "convert", "--input", str(path / "validation.npz"),
                            "--split", "validation", "--config", str(path / "config.json"),
                            "--output", str(path / "converted")], check=True, capture_output=True, text=True)
            self.assertEqual(before, (path / "config.json").read_bytes())
            report = json.loads((path / "converted/conversion_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["reference_kind"], "supplied_Y")
            self.assertEqual(len(report["samples"]), 2)
            self.assertLess(report["accuracy"]["max_nrmse"], 0.001)
            wrong_split = subprocess.run([sys.executable, str(script), "convert", "--input", str(path / "validation.npz"),
                                          "--split", "testing", "--config", str(path / "config.json"),
                                          "--output", str(path / "wrong")], capture_output=True, text=True)
            self.assertNotEqual(wrong_split.returncode, 0)


if __name__ == "__main__":
    unittest.main()
