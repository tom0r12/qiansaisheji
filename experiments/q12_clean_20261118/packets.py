"""Input packet formats for the clean (no input entropy coding) variants.

Numerical tensors come from the frozen Q12 fixtures via the frozen reference
parser; X12/W12 values, bias, shifts and expected dense Y13 are unchanged.

Formats
  rice    : frozen Rice/delta packet (historical baseline only)
  fixed12 : fixed-width signed12 values, LSB-first continuous bit packing in
            32-bit little-endian words (8 values per 3 words). No data-dependent
            field length, no prediction, no entropy coding.
"""
from pathlib import Path
import hashlib, json, struct, sys, zipfile
import numpy as np

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[2]
FROZEN = WORK / 'output/eda/q12_final_20261113'
BASELINE = WORK / 'output/eda/q12_candidate/loader_master/soc_runner/runs/20261112T161939623706Z/result.json'
FIXTURES = WORK / 'output/eda/q12_candidate/fixtures/q12_fixtures72.zip'
OUTPUT_MAGIC = 0x32443151
OUTPUT_WORDS = 12689
WRITE_TRANSACTIONS = 12690
MAGIC = {'rice': 0x31513151, 'fixed12': 0x32583151, 'w10': 0x32573151, 'pair12': 0x32503151, 'pairw10': 0x32503152}
X_SYMBOLS, W_SYMBOLS = 6336, 2048


def rne_div(v, k):
    v = np.asarray(v, dtype=np.int64); mag = np.abs(v); q = mag >> k; rem = mag & ((1 << k) - 1); half = 1 << (k - 1)
    inc = (rem > half) | ((rem == half) & ((q & 1) != 0))
    return np.where(v < 0, -(q + inc), q + inc)


def pack_bits(values, width):
    v = (np.asarray(values, dtype=np.int64).ravel() & ((1 << width) - 1))
    n = 0
    for i, x in enumerate(v.tolist()):
        n |= int(x) << (width * i)
    nbits = width * v.size
    assert nbits % 32 == 0
    return n.to_bytes(nbits // 8, 'little')


def unpack_bits(blob, count, width):
    n = int.from_bytes(blob, 'little'); res = np.empty(count, dtype=np.int64); m = (1 << width) - 1
    for i in range(count):
        x = (n >> (width * i)) & m
        res[i] = x - (1 << width) if x >> (width - 1) else x
    return res


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def pack12(values):
    v = (np.asarray(values, dtype=np.int64).ravel() & 0xFFF).astype(np.uint64)
    assert v.size % 8 == 0
    v = v.reshape(-1, 8)
    acc = np.zeros(v.shape[0], dtype=object)
    out = bytearray()
    for row in v:
        n = 0
        for i, x in enumerate(row):
            n |= int(x) << (12 * i)
        out += n.to_bytes(12, 'little')
    return bytes(out)


def unpack12(blob, count):
    n = int.from_bytes(blob, 'little')
    res = np.empty(count, dtype=np.int64)
    for i in range(count):
        x = (n >> (12 * i)) & 0xFFF
        res[i] = x - 4096 if x & 0x800 else x
    return res


def build(fmt, packed, x, w):
    if fmt == 'rice':
        return packed
    if fmt == 'w10':
        raise ValueError('use build_w10')
    if fmt != 'fixed12':
        raise ValueError(fmt)
    header = struct.pack('<10I', MAGIC[fmt], X_SYMBOLS * 12, *([W_SYMBOLS * 12] * 8))
    meta = packed[40:1320]
    data = header + meta + pack12(x) + b''.join(pack12(w[:, g * 32:g * 32 + 32]) for g in range(8))
    # independent reconstruction
    off = 1320
    rx = unpack12(data[off:off + 9504], X_SYMBOLS).reshape(99, 64); off += 9504
    rw = np.concatenate([unpack12(data[off + 3072 * g:off + 3072 * (g + 1)], W_SYMBOLS).reshape(64, 32) for g in range(8)], axis=1)
    if not (np.array_equal(rx, x) and np.array_equal(rw, w)) or off + 3072 * 8 != len(data):
        raise ValueError('fixed12 reconstruction mismatch')
    return data


def export(out, fmt, tasks=12):
    baseline = json.loads(BASELINE.read_text())
    if sha_bytes(FIXTURES.read_bytes()) != baseline['fixtures_zip_sha256']:
        raise ValueError('Frozen source data changed')
    sys.path.insert(0, str(FROZEN / 'freeze/snapshot/output/eda/q12_candidate/packing'))
    from packet_io import parse_input
    rows = []
    with zipfile.ZipFile(FIXTURES) as z:
        selected = baseline['packets'][:tasks]
        if tasks > 12:  # all 72 frozen fixtures (12 layers x 6 samples); hashes from the archive itself
            names = sorted({n.rsplit('/', 1)[0] for n in z.namelist() if n.endswith('/input.bin')})
            selected = [{'task': n, 'directory': n.replace('/', '_'), 'input_sha256': sha_bytes(z.read(n + '/input.bin')),
                         'dense_sha256': sha_bytes(z.read(n + '/expected_dense16.bin'))} for n in names][:tasks]
        for old in selected:
            case = out / old['directory']; case.mkdir(parents=True, exist_ok=True)
            packed = z.read(old['task'] + '/input.bin')
            dense = z.read(old['task'] + '/expected_dense16.bin')
            if sha_bytes(packed) != old['input_sha256'] or sha_bytes(dense) != old['dense_sha256']:
                raise ValueError('frozen hash mismatch')
            x, w, bias, shifts = parse_input(packed)
            if fmt == 'w10':
                sys.path.insert(0, str(FROZEN / 'freeze/snapshot/output/eda/q12_candidate/reference'))
                import fixed_reference as fixed
                if not np.array_equal(np.frombuffer(dense, dtype='<i2').reshape(99, 256), fixed.direct(x, w, bias, shifts)):
                    raise ValueError('frozen reference does not reproduce W12 dense output')
                w10 = np.clip(rne_div(w, 2), -512, 511); b10 = rne_div(bias, 2); s10 = shifts - 2
                if np.any(s10 < 0): raise ValueError('shift underflow for W10')
                y = fixed.direct(x, w10, b10, s10)
                dense = y.astype('<i2').tobytes()
                header = struct.pack('<10I', MAGIC['w10'], X_SYMBOLS * 12, *([W_SYMBOLS * 10] * 8))
                meta = struct.pack('<256I', *[int(v) & 0xffffffff for v in b10]) + \
                       struct.pack('<64I', *[sum(int(s10[j + k]) << (8 * k) for k in range(4)) for j in range(0, 256, 4)])
                data = header + meta + pack_bits(x, 12) + b''.join(pack_bits(w10[:, g * 32:g * 32 + 32], 10) for g in range(8))
                off = 1320 + 9504
                rw = np.concatenate([unpack_bits(data[off + 2560 * g:off + 2560 * (g + 1)], 2048, 10).reshape(64, 32) for g in range(8)], axis=1)
                if not np.array_equal(rw, w10) or len(data) != 7826 * 4: raise ValueError('w10 packing mismatch')
            else:
                data = build(fmt, packed, x, w) if fmt not in ('pair12', 'pairw10') else b''
            if fmt in ('pair12', 'pairw10'):
                # Same numerics as fixed12 / w10; values reordered offline into the
                # accelerator's row-pair consumption order (see q12_fixed12_reader v6).
                sys.path.insert(0, str(FROZEN / 'freeze/snapshot/output/eda/q12_candidate/reference'))
                import fixed_reference as fixed
                if fmt == 'pairw10':
                    wq = np.clip(rne_div(w, 2), -512, 511); bq = rne_div(bias, 2); sq = shifts - 2; wbits = 10
                    dense = fixed.direct(x, wq, bq, sq).astype('<i2').tobytes()
                else:
                    wq, bq, sq, wbits = w, bias, shifts, 12
                    if not np.array_equal(np.frombuffer(dense, dtype='<i2').reshape(99, 256), fixed.direct(x, w, bias, shifts)):
                        raise ValueError('reference mismatch')
                xo = [x[2 * p + r, 2 * k + c] for p in range(49) for k in range(32) for (r, c) in ((0, 0), (0, 1), (1, 0), (1, 1))]
                xo += [x[98, 2 * k + c] for k in range(32) for c in (0, 1)]
                wo = []
                for g in range(8):
                    G = wq[:, g * 32:g * 32 + 32]
                    wo.append([G[2 * m + r, c2 * 2 + c] for m in range(32) for c2 in range(16) for (c, r) in ((0, 0), (0, 1), (1, 0), (1, 1))])
                header = struct.pack('<10I', MAGIC[fmt], X_SYMBOLS * 12, *([W_SYMBOLS * wbits] * 8))
                meta = struct.pack('<256I', *[int(v) & 0xffffffff for v in bq]) + \
                       struct.pack('<64I', *[sum(int(sq[j + k]) << (8 * k) for k in range(4)) for j in range(0, 256, 4)])
                data = header + meta + pack_bits(np.array(xo), 12) + b''.join(pack_bits(np.array(o), wbits) for o in wo)
                if len(data) != (8850 if wbits == 12 else 7826) * 4: raise ValueError('pair packing length')
            expected = struct.pack('<17I', OUTPUT_MAGIC, *([1584] * 16)) + dense
            for name, blob, width in [('input.hex', data, 4), ('expected.hex', expected, 4), ('dense.hex', dense, 2)]:
                (case / name).write_text(''.join(f'{int.from_bytes(blob[i:i + width], "little"):0{width * 2}x}\n' for i in range(0, len(blob), width)), encoding='ascii')
            rows.append({'task': old['task'], 'directory': case.name, 'input_words': len(data) // 4,
                         'input_sha256': sha_bytes(data), 'dense_sha256': sha_bytes(dense),
                         'frozen_input_sha256': old['input_sha256']})
    return rows


if __name__ == '__main__':
    import tempfile
    t = Path(tempfile.mkdtemp())
    print(export(t, 'fixed12', 2))
