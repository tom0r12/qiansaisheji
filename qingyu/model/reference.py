"""Bit-accurate signed fixed-point model. Requires only NumPy.

All accumulations include the bias and check the 48-bit range after each MAC.
No floating point is used by the integer inference path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np

ACC_MIN, ACC_MAX = -(1 << 47), (1 << 47) - 1
I32_MIN, I32_MAX = -(1 << 31), (1 << 31) - 1
Q16_MAX = (1 << 15) - 1


def output_format(output_bits: int) -> tuple[int, int, type]:
    """The output width is part of the frozen format, not a transport hint."""
    if isinstance(output_bits, bool) or not isinstance(output_bits, (int, np.integer)) or output_bits not in (16, 32):
        raise ValueError("output_bits must be 16 or 32")
    return -(1 << (output_bits - 1)), (1 << (output_bits - 1)) - 1, np.int16 if output_bits == 16 else np.int32


def _check_headroom(bits: int) -> None:
    if isinstance(bits, bool) or not isinstance(bits, (int, np.integer)) or not 0 <= bits <= 47:
        raise ValueError("output_headroom_bits must be an integer in 0..47")


def _integers(value: Any, name: str) -> np.ndarray:
    a = np.asarray(value)
    if a.dtype.kind not in "iu":
        raise TypeError(f"{name} must contain integers")
    if a.dtype.kind == "u" and a.size and np.max(a) > np.iinfo(np.int64).max:
        raise OverflowError(f"{name} cannot be represented by int64")
    return a.astype(np.int64, copy=False)


def _finite(value: Any, name: str) -> np.ndarray:
    a = np.asarray(value, dtype=np.float64)
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{name} contains non-finite values")
    return a


def round_shift_rne(value: int, shift: int) -> int:
    """Integer division by 2**shift, nearest with ties to even, both signs."""
    if not isinstance(shift, (int, np.integer)) or not 0 <= int(shift) <= 47:
        raise ValueError("right shift must be an integer in 0..47")
    if not isinstance(value, (int, np.integer)):
        raise TypeError("value must be an integer")
    value, shift = int(value), int(shift)
    if shift == 0:
        return value
    magnitude = abs(value)
    quotient, remainder = divmod(magnitude, 1 << shift)
    half = 1 << (shift - 1)
    if remainder > half or (remainder == half and quotient & 1):
        quotient += 1
    return -quotient if value < 0 else quotient


def requantize(accumulators: Any, shifts: Any, *, output_bits: int = 32) -> tuple[np.ndarray, int]:
    lower, upper, dtype = output_format(output_bits)
    a = _integers(accumulators, "accumulators")
    r = _integers(shifts, "shifts")
    if a.ndim < 1 or r.shape != (a.shape[-1],):
        raise ValueError("shifts must have one entry per output channel")
    if np.any((a < ACC_MIN) | (a > ACC_MAX)):
        raise OverflowError("accumulator is outside signed 48-bit range")
    if np.any((r < 0) | (r > 47)):
        raise ValueError("right shifts must be in 0..47")
    result = np.empty(a.shape, dtype=dtype)
    saturated = 0
    # Vectorize over rows; the last-axis loop permits different channel shifts.
    for j, shift in enumerate(r):
        column = a[..., j]
        magnitude = np.abs(column)  # signed48 minimum fits in positive int64
        s = int(shift)
        if s:
            quotient = magnitude >> s
            remainder = magnitude & ((1 << s) - 1)
            half = 1 << (s - 1)
            increment = (remainder > half) | ((remainder == half) & ((quotient & 1) != 0))
            rounded = quotient + increment.astype(np.int64)
        else:
            rounded = magnitude
        rounded = np.where(column < 0, -rounded, rounded)
        saturated += int(np.count_nonzero((rounded < lower) | (rounded > upper)))
        result[..., j] = np.clip(rounded, lower, upper).astype(dtype)
    return result, saturated


def accumulate(qx: Any, qw: Any, qb: Any) -> np.ndarray:
    """Supports X[...,K], W[K,N], b[N], checking every intermediate sum."""
    x, w, b = (_integers(v, n) for v, n in ((qx, "qx"), (qw, "qw"), (qb, "qb")))
    if x.ndim < 2 or w.ndim != 2 or x.shape[-1] != w.shape[0] or b.shape != (w.shape[1],):
        raise ValueError("expected X[...,K], W[K,N], b[N] with matching dimensions")
    if not x.size or not w.size:
        raise ValueError("empty matrices are not supported")
    if np.any((x < -32768) | (x > 32767)) or np.any((w < -32768) | (w > 32767)):
        raise OverflowError("input and weight values must fit signed 16 bits")
    if np.any((b < ACC_MIN) | (b > ACC_MAX)):
        raise OverflowError("bias must fit signed 48 bits")
    rows = x.reshape(-1, x.shape[-1])
    a = np.broadcast_to(b, (rows.shape[0], w.shape[1])).copy()
    for k in range(w.shape[0]):
        # int64 safely contains a signed48 value plus one signed32 product.
        a += rows[:, k, None] * w[k, None, :]
        if np.any((a < ACC_MIN) | (a > ACC_MAX)):
            raise OverflowError(f"signed 48-bit accumulation overflow at k={k}")
    return a.reshape(x.shape[:-1] + (w.shape[1],))


@dataclass(frozen=True)
class LinearResult:
    output: np.ndarray
    accumulators: np.ndarray
    saturation_count: int


def qlinear_int(qx: Any, qw: Any, qb: Any, shifts: Any, *, output_bits: int = 32) -> LinearResult:
    a = accumulate(qx, qw, qb)
    y, count = requantize(a, shifts, output_bits=output_bits)
    return LinearResult(y, a, count)


def _scale(exponent: int) -> float:
    if not isinstance(exponent, (int, np.integer)):
        raise TypeError("scale exponent must be an integer")
    try:
        value = math.ldexp(1.0, int(exponent))
    except OverflowError as exc:
        raise ValueError("scale exponent exceeds float64 range") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError("scale cannot be represented as a positive float64")
    return value


def power2_scale_exponent(maximum_absolute_value: float) -> int:
    maximum = float(maximum_absolute_value)
    if not math.isfinite(maximum) or maximum < 0:
        raise ValueError("maximum must be finite and nonnegative")
    if maximum == 0:
        return 0
    exponent = int(math.ceil(math.log2(maximum) - math.log2(Q16_MAX)))
    scale = _scale(exponent)
    # Verify the floating-point log boundary rather than relying on it alone.
    while maximum / scale > Q16_MAX:
        exponent += 1
        scale = _scale(exponent)
    return exponent


def quantize_symmetric16(value: Any, scale: Any) -> np.ndarray:
    a, s = _finite(value, "float values"), _finite(scale, "scale")
    if np.any(s <= 0):
        raise ValueError("scales must be positive")
    with np.errstate(over="ignore"):
        quantized = np.rint(a / s)
    return np.clip(quantized, -Q16_MAX, Q16_MAX).astype(np.int16)


def weight_digest(w: Any, b: Any) -> str:
    digest = hashlib.sha256()
    for value in (w, b):
        a = np.ascontiguousarray(_finite(value, "weights/bias"), dtype="<f8")
        digest.update(str(a.shape).encode("ascii"))
        digest.update(a.tobytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class LayerConfig:
    layer: int
    x_exponent: int
    w_exponents: list[int]
    shifts: list[int]
    weights_sha256: str
    calibration_role: str = "training"
    format_version: str = "qingyu-fixed-v1"
    output_bits: int = 32
    output_headroom_bits: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, source: dict[str, Any]) -> "LayerConfig":
        config = cls(**source)
        if config.format_version not in ("qingyu-fixed-v1", "qingyu-fixed-v2") or config.calibration_role != "training":
            raise ValueError("unsupported format or non-training calibration")
        output_format(config.output_bits)
        _check_headroom(config.output_headroom_bits)
        if config.format_version == "qingyu-fixed-v1" and (config.output_bits != 32 or config.output_headroom_bits):
            raise ValueError("legacy v1 configurations require INT32 output without extra headroom")
        if not 0 <= config.layer <= 11:
            raise ValueError("layer index must be 0..11")
        _scale(config.x_exponent)
        for exponent in config.w_exponents:
            _scale(exponent)
        shifts = _integers(config.shifts, "shifts")
        if not len(config.w_exponents) or len(config.w_exponents) != len(config.shifts):
            raise ValueError("weight scales and shifts must cover the same nonempty channel set")
        if np.any((shifts < 0) | (shifts > 47)):
            raise ValueError("right shifts must be 0..47")
        if len(config.weights_sha256) != 64:
            raise ValueError("missing weight provenance hash")
        return config


def encode_layer(x: Any, w: Any, b: Any, config: LayerConfig) -> tuple[np.ndarray, ...]:
    output_format(config.output_bits)
    x, w, b = (_finite(v, n) for v, n in ((x, "X"), (w, "W"), (b, "b")))
    if x.ndim < 2 or w.ndim != 2 or x.shape[-1] != w.shape[0] or b.shape != (w.shape[1],):
        raise ValueError("expected X[...,K], W[K,N], b[N]")
    if len(config.w_exponents) != w.shape[1] or len(config.shifts) != w.shape[1]:
        raise ValueError("configuration output channel count does not match W")
    if weight_digest(w, b) != config.weights_sha256:
        raise ValueError("weights or bias differ from frozen configuration")
    sx = _scale(config.x_exponent)
    sw = np.array([_scale(e) for e in config.w_exponents], dtype=np.float64)
    product_scale = sx * sw
    if np.any(~np.isfinite(product_scale)) or np.any(product_scale <= 0):
        raise ValueError("product scales cannot be represented")
    qx, qw = quantize_symmetric16(x, sx), quantize_symmetric16(w, sw)
    qb_float = np.rint(b / product_scale)
    if np.any(~np.isfinite(qb_float)) or np.any((qb_float < ACC_MIN) | (qb_float > ACC_MAX)):
        raise OverflowError("encoded bias does not fit signed48")
    qb = qb_float.astype(np.int64)
    return qx, qw, qb, np.asarray(config.shifts, dtype=np.int64)


def calibrate_layer(x: Any, w: Any, b: Any, layer: int, *, role: str,
                    output_bits: int = 32, output_headroom_bits: int = 0) -> LayerConfig:
    output_format(output_bits)
    _check_headroom(output_headroom_bits)
    if role != "training":
        raise ValueError("only training data may be used for calibration")
    if not 0 <= layer <= 11:
        raise ValueError("layer index must be 0..11")
    x, w, b = (_finite(v, n) for v, n in ((x, "X"), (w, "W"), (b, "b")))
    if x.ndim < 2 or w.ndim != 2 or x.shape[-1] != w.shape[0] or b.shape != (w.shape[1],):
        raise ValueError("expected X[...,K], W[K,N], b[N]")
    if not x.size or not w.size:
        raise ValueError("calibration data cannot be empty")
    config = LayerConfig(layer, power2_scale_exponent(float(np.max(np.abs(x)))),
                         [power2_scale_exponent(float(v)) for v in np.max(np.abs(w), axis=0)],
                         [0] * w.shape[1], weight_digest(w, b),
                         format_version="qingyu-fixed-v2" if output_bits == 16 or output_headroom_bits else "qingyu-fixed-v1",
                         output_bits=output_bits, output_headroom_bits=output_headroom_bits)
    qx, qw, qb, _ = encode_layer(x, w, b, config)
    # Bound applies to arbitrary valid symmetric INT16 operands, including
    # validation inputs whose values saturate at the quantizer limits.
    bound = w.shape[0] * Q16_MAX * Q16_MAX
    if np.any(np.abs(qb) > ACC_MAX - bound):
        raise OverflowError("bias plus worst-case INT16 dot product exceeds signed48")
    a = accumulate(qx, qw, qb)
    shifts: list[int] = []
    for j in range(w.shape[1]):
        column = a[..., j]
        for shift in range(48):
            _, count = requantize(column[..., None], np.array([shift]), output_bits=output_bits)
            if count == 0:
                # A single declared policy is applied to every channel/layer.
                # It trades resolution for range using training data only.
                if shift + output_headroom_bits > 47:
                    raise OverflowError("requested output headroom exceeds the hardware shift range")
                shifts.append(shift + output_headroom_bits)
                break
        else:
            raise OverflowError("no supported output shift can represent training output")
    return LayerConfig(config.layer, config.x_exponent, config.w_exponents,
                       shifts, config.weights_sha256, format_version=config.format_version,
                       output_bits=output_bits, output_headroom_bits=output_headroom_bits)


def decode_layer(qy: Any, config: LayerConfig) -> np.ndarray:
    lower, upper, _ = output_format(config.output_bits)
    y = _integers(qy, "qy")
    if y.ndim < 1 or y.shape[-1] != len(config.w_exponents):
        raise ValueError("output channel count differs from configuration")
    if np.any((y < lower) | (y > upper)):
        raise OverflowError(f"output must fit signed{config.output_bits}")
    factors = np.array([_scale(config.x_exponent + e + r)
                        for e, r in zip(config.w_exponents, config.shifts)])
    result = y.astype(np.float64) * factors
    if not np.all(np.isfinite(result)):
        raise OverflowError("decoded output is non-finite")
    return result


class NrmseAccumulator:
    """Accumulate squared sums per layer, then normalize; never average ratios."""

    def __init__(self) -> None:
        self.layers: dict[int, tuple[int, float, float]] = {}

    def update(self, layer: int, reference: Any, decoded: Any) -> None:
        if not 0 <= layer <= 11:
            raise ValueError("layer index must be 0..11")
        ref, got = _finite(reference, "reference"), _finite(decoded, "decoded")
        if ref.shape != got.shape or not ref.size:
            raise ValueError("reference and decoded must have the same nonempty shape")
        count, error_sum, reference_sum = self.layers.get(layer, (0, 0.0, 0.0))
        error_sum += float(np.sum(np.square(got - ref), dtype=np.float64))
        reference_sum += float(np.sum(np.square(ref), dtype=np.float64))
        if not math.isfinite(error_sum) or not math.isfinite(reference_sum):
            raise OverflowError("NRMSE squared sums are non-finite")
        self.layers[layer] = count + ref.size, error_sum, reference_sum

    def summary(self, *, require_all_layers: bool = False) -> dict[str, Any]:
        if not self.layers:
            raise ValueError("no samples have been accumulated")
        if require_all_layers and set(self.layers) != set(range(12)):
            raise ValueError("all 12 layers are required")
        by_layer = {}
        for layer, (count, errors, references) in sorted(self.layers.items()):
            nrmse = math.sqrt(errors / count) / max(math.sqrt(references / count), 1e-8)
            by_layer[str(layer)] = {"elements": count, "nrmse": nrmse}
        maximum = max(record["nrmse"] for record in by_layer.values())
        return {"layers": by_layer, "max_nrmse": maximum,
                "meets_3_percent_threshold": maximum <= 0.03}


def pack_int16_words(value: Any) -> np.ndarray:
    a = _integers(value, "int16 data").reshape(-1)
    if np.any((a < -32768) | (a > 32767)):
        raise OverflowError("value does not fit signed16")
    if a.size % 2:
        a = np.append(a, 0)
    unsigned = (a & 0xFFFF).astype(np.uint32)
    return unsigned[0::2] | (unsigned[1::2] << 16)


def unpack_int16_words(words: Any, count: int | None = None) -> np.ndarray:
    values = _integers(words, "words").reshape(-1)
    if np.any((values < 0) | (values > 0xFFFFFFFF)):
        raise OverflowError("word must fit unsigned32")
    halves = np.empty(values.size * 2, dtype=np.int64)
    halves[0::2], halves[1::2] = values & 0xFFFF, (values >> 16) & 0xFFFF
    halves = np.where(halves & 0x8000, halves - 0x10000, halves).astype(np.int16)
    if count is not None:
        if not 0 <= count <= halves.size:
            raise ValueError("invalid unpack count")
        halves = halves[:count]
    return halves


def pack_meta_words(bias: Any, shifts: Any) -> np.ndarray:
    b, r = _integers(bias, "bias"), _integers(shifts, "shifts")
    if b.ndim != 1 or r.shape != b.shape:
        raise ValueError("bias and shifts must be matching one-dimensional arrays")
    if np.any((b < ACC_MIN) | (b > ACC_MAX)) or np.any((r < 0) | (r > 47)):
        raise OverflowError("metadata fields out of range")
    words = np.empty(b.size * 2, dtype=np.uint32)
    words[0::2] = (b & 0xFFFFFFFF).astype(np.uint32)
    words[1::2] = (((b >> 32) & 0xFFFF) | (r << 16)).astype(np.uint32)
    return words


def unpack_meta_words(words: Any) -> tuple[np.ndarray, np.ndarray]:
    a = _integers(words, "metadata").reshape(-1)
    if a.size % 2 or np.any((a < 0) | (a > 0xFFFFFFFF)):
        raise ValueError("metadata needs pairs of unsigned32 words")
    high = a[1::2]
    if np.any(high & 0xFF000000):
        raise ValueError("reserved metadata bits must be zero")
    bias = a[0::2] | ((high & 0xFFFF) << 32)
    bias = np.where(bias & (1 << 47), bias - (1 << 48), bias)
    shifts = (high >> 16) & 0xFF
    if np.any(shifts > 47):
        raise ValueError("unsupported metadata right shift")
    return bias, shifts


def output_words(value: Any, *, output_bits: int = 32) -> np.ndarray:
    lower, upper, _ = output_format(output_bits)
    a = _integers(value, "output").reshape(-1)
    if np.any((a < lower) | (a > upper)):
        raise OverflowError(f"output does not fit signed{output_bits}")
    if output_bits == 16:
        return pack_int16_words(a)
    return (a & 0xFFFFFFFF).astype(np.uint32)


def write_hex_words(path: str | Path, words: Any) -> None:
    a = _integers(words, "hex words").reshape(-1)
    if np.any((a < 0) | (a > 0xFFFFFFFF)):
        raise OverflowError("hex word outside unsigned32")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(f"{int(word):08x}\n" for word in a), encoding="ascii")


def read_hex_words(path: str | Path) -> np.ndarray:
    values = [int(line.strip(), 16) for line in Path(path).read_text(encoding="ascii").splitlines()
              if line.strip()]
    if any(value < 0 or value > 0xFFFFFFFF for value in values):
        raise ValueError("hex word outside unsigned32")
    return np.array(values, dtype=np.uint32)


def export_layer_vectors(directory: str | Path, qx: Any, qw: Any, qb: Any,
                         shifts: Any, qy: Any, *, lanes: int = 4,
                         output_bits: int = 32) -> dict[str, Any]:
    _, _, output_dtype = output_format(output_bits)
    x, w, b, y = (_integers(v, n) for v, n in
                  ((qx, "qx"), (qw, "qw"), (qb, "qb"), (qy, "qy")))
    r = _integers(shifts, "shifts")
    if x.ndim != 2 or w.ndim != 2 or y.shape != (x.shape[0], w.shape[1]):
        raise ValueError("vector export requires one X[ROWS,K], W[K,N], Y[ROWS,N]")
    if x.shape[1] != w.shape[0] or b.shape != (w.shape[1],) or r.shape != b.shape:
        raise ValueError("vector dimensions do not match")
    if lanes <= 0 or w.shape[1] % lanes or (w.shape[0] * lanes) % 2:
        raise ValueError("output count must divide LANES and tile packing must have even size")
    if output_bits == 16 and lanes % 2:
        raise ValueError("INT16 output tiles require an even lane count")
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    tiles = w.shape[1] // lanes
    tile_w = w.reshape(w.shape[0], tiles, lanes).transpose(1, 0, 2)
    tile_y = y.reshape(x.shape[0], tiles, lanes).transpose(1, 0, 2)
    files = {"x_words.hex": pack_int16_words(x),
             "w_tile_words.hex": pack_int16_words(tile_w),
             "meta_words.hex": pack_meta_words(b, r),
             "y_row_words.hex": output_words(y, output_bits=output_bits),
             "y_tile_words.hex": output_words(tile_y, output_bits=output_bits)}
    for name, words in files.items():
        write_hex_words(target / name, words)
    np.savez_compressed(target / "integer_case.npz", qx=x.astype(np.int16),
                        qw=w.astype(np.int16), qb=b, shifts=r.astype(np.uint8),
                        qy=y.astype(output_dtype), output_bits=np.int64(output_bits))
    return {"rows": x.shape[0], "k": x.shape[1], "outputs": w.shape[1],
            "lanes": lanes, "tiles": tiles, "x_words": len(files["x_words.hex"]),
            "weight_words_per_tile": w.shape[0] * lanes // 2,
            "meta_words_per_tile": lanes * 2,
            "output_bits": output_bits, "output_words_per_tile": x.shape[0] * lanes * output_bits // 32,
            "files": {name: {"words": len(words), "sha256": hashlib.sha256((target / name).read_bytes()).hexdigest()}
                      for name, words in files.items()}}
