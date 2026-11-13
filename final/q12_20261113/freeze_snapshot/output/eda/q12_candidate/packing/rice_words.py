"""Width-parametric canonical Rice32 reference over real 32-bit bus words."""
import struct
from functools import lru_cache
import numpy as np

@lru_cache(maxsize=32)
def _tables(width, k):
    raw = [format(i, f'0{width}b') for i in range(1 << width)]
    coded = ['1'*(i >> k)+'0'+(format(i & ((1<<k)-1),f'0{k}b') if k else '')
             for i in range(1 << width)]
    return raw, coded

def transformed(values, width, delta):
    values = np.asarray(values, dtype=np.int64)
    low, high = -(1 << (width-1)), (1 << (width-1))-1
    if np.any((values < low) | (values > high)): raise ValueError('symbol range')
    mask = (1 << width)-1
    unsigned = values & mask
    if delta:
        previous = np.zeros_like(unsigned)
        previous[..., 1:, :] = unsigned[..., :-1, :]
        unsigned = (unsigned-previous) & mask
    signed = np.where(unsigned & (1 << (width-1)), unsigned-(1 << width), unsigned)
    u = np.where(signed < 0, -2*signed-1, 2*signed)
    return unsigned, u

def exact_lengths(values, width, k, delta):
    """Exact canonical code lengths for each matrix, checked against serialization."""
    if values.ndim == 2: values = values[None]
    _, u = transformed(values, width, delta)
    u = u.reshape(len(u), -1)
    sizes = np.full((u.shape[1]+31)//32, 32, dtype=np.int64)
    sizes[-1] = u.shape[1]-32*(len(sizes)-1)
    costs = np.add.reduceat((u >> k)+1+k, np.arange(0,u.shape[1],32), axis=1)
    return np.sum(1+np.minimum(costs, width*sizes), axis=1)

def encode(values, width, k, delta):
    if not 1 <= width <= 16 or not 0 <= k < width: raise ValueError('format')
    unsigned, zigzag = transformed(values, width, delta)
    unsigned, zigzag = unsigned.ravel().tolist(), zigzag.ravel().tolist()
    raw_table, code_table = _tables(width, k)
    chunks = []
    for first in range(0,len(unsigned),32):
        a, u = unsigned[first:first+32], zigzag[first:first+32]
        codes = [code_table[i] for i in u]
        if sum(map(len,codes)) >= width*len(a): chunks.append('1'+''.join(raw_table[i] for i in a))
        else: chunks.append('0'+''.join(codes))
    bits = ''.join(chunks)
    nbits = len(bits)
    bits += '0' * ((-nbits) % 32)
    # First stream bit is bit7 of lowest-address byte, matching the existing codec.
    payload = np.packbits(np.frombuffer(bits.encode('ascii'),dtype=np.uint8)-48).tobytes()
    return payload, nbits

def decode(payload, nbits, shape, width, k, delta):
    if len(payload) != 4*((nbits+31)//32): raise ValueError('word count')
    bits = ''.join(format(v,'08b') for v in payload)
    if '1' in bits[nbits:]: raise ValueError('nonzero padding')
    bits = bits[:nbits]
    pos, values = 0, []
    def get(n):
        nonlocal pos
        if pos+n > nbits: raise ValueError('truncated')
        value = int(bits[pos:pos+n],2) if n else 0
        pos += n
        return value
    total = int(np.prod(shape)); mask = (1<<width)-1
    while len(values) < total:
        raw = get(1); n = min(32,total-len(values)); block=[]; cost=0
        for _ in range(n):
            if raw:
                value=get(width); signed=value-(1<<width) if value & (1<<(width-1)) else value
                u=-2*signed-1 if signed<0 else 2*signed
            else:
                zero=bits.find('0',pos)
                if zero<0: raise ValueError('unterminated unary')
                quotient=zero-pos
                if quotient > (mask>>k): raise ValueError('unary overflow')
                pos=zero+1; u=(quotient<<k)|get(k)
                if u>mask: raise ValueError('symbol overflow')
                signed=-(u+1)//2 if u&1 else u//2; value=signed&mask
            block.append(value); cost+=(u>>k)+1+k
        if bool(raw) != (cost >= n*width): raise ValueError('noncanonical block')
        values.extend(block)
    if pos != nbits: raise ValueError('trailing bits')
    result=np.array(values,dtype=np.int64).reshape(shape)
    if delta: result=np.cumsum(result,axis=-2)&mask
    return np.where(result&(1<<(width-1)),result-(1<<width),result)

def bus_words(payload):
    if len(payload)%4: raise ValueError('unaligned bytes')
    return list(struct.unpack('<'+'I'*(len(payload)//4), payload))
