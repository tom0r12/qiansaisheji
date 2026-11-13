"""X12/W12/Y13 canonical packet reference; no implicit format auto-detection."""
import struct
import numpy as np
from rice_words import decode, bus_words
INPUT_MAGIC=0x31513151
OUTPUT_MAGIC=0x31593151
HEADER_WORDS=330
SLOT_WORDS=646
INPUT_MAX_WORDS=8873
FORMAT_VERSION='q12_x12_w12_y13_h1'
POISON=0xcccccccc

def parse_input(payload):
    words=bus_words(payload)
    if not HEADER_WORDS<=len(words)<=INPUT_MAX_WORDS or words[0]!=INPUT_MAGIC: raise ValueError('input magic/header/size')
    counts=words[1:10]
    if not 0<counts[0]<=6336*12+198: raise ValueError('X length')
    if any(not 0<n<=2048*12+64 for n in counts[1:]): raise ValueError('W length')
    bias=[]
    for word in words[10:266]:
        val=word-(1<<32) if word&(1<<31) else word
        if not -(1<<21)<=val<(1<<21): raise ValueError('bias22 sign extension')
        bias.append(val)
    shifts=np.frombuffer(payload[266*4:330*4],dtype=np.uint8).astype(np.int64)
    if np.any(shifts>47): raise ValueError('shift >47')
    offset=HEADER_WORDS*4
    def take(n,shape,k,delta):
        nonlocal offset
        length=((n+31)//32)*4; data=payload[offset:offset+length];offset+=length
        return decode(data,n,shape,12,k,delta)
    x=take(counts[0],(99,64),6,True)
    w=np.empty((64,256),dtype=np.int64)
    for group in range(8): w[:,group*32:group*32+32]=take(counts[group+1],(64,32),9,False)
    if offset!=len(payload): raise ValueError('trailing input words')
    return x,w,np.asarray(bias,dtype=np.int64),shifts

def build_output(payloads,bit_counts):
    if len(payloads)!=16 or len(bit_counts)!=16: raise ValueError('tile count')
    words=[POISON]*(17+16*SLOT_WORDS)
    words[:17]=[OUTPUT_MAGIC,*bit_counts]
    for tile,(payload,bits) in enumerate(zip(payloads,bit_counts)):
        if not 0<bits<=1584*13+50: raise ValueError('tile bits')
        p=bus_words(payload)
        if len(p)!=(bits+31)//32: raise ValueError('tile payload length')
        start=17+tile*SLOT_WORDS;words[start:start+len(p)]=p
    return struct.pack('<'+'I'*len(words),*words)

def parse_output(payload,k=7):
    words=bus_words(payload)
    if len(words)!=17+16*SLOT_WORDS or words[0]!=OUTPUT_MAGIC: raise ValueError('output magic/allocation')
    y=np.empty((99,256),dtype=np.int64)
    for tile,bits in enumerate(words[1:17]):
        if not 0<bits<=1584*13+50: raise ValueError('tile bits')
        n=(bits+31)//32;start=17+tile*SLOT_WORDS
        if any(w!=POISON for w in words[start+n:start+SLOT_WORDS]): raise ValueError('unused output slot overwritten')
        y[:,tile*16:tile*16+16]=decode(payload[4*start:4*(start+n)],bits,(99,16),13,k,True)
    return y
