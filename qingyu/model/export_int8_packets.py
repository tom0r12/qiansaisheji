"""Export and independently parse complete tiled Rice32 input/output packets.

Packet layout is fixed in experiments/integration/int8stream/contract.json.
No numeric or codec parameters are fitted. Unused output slot words are poison
and must remain unwritten; compressed payload lengths are actual bit lengths.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import struct
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from analyze_lossless_command_budget import numeric,quantized,sha

INPUT_MAGIC=0x31523851
OUTPUT_MAGIC=0x31593851
SLOT_WORDS=398
POISON=0xcccccccc


def bits_words(bits):
    raw=bytes(int(bits[i:i+8].ljust(8,'0'),2) for i in range(0,len(bits),8))
    raw+=bytes((-len(raw))%4)
    return list(struct.unpack('<'+'I'*(len(raw)//4),raw))


def decode_stream(words,bit_count,rows,cols,k,delta):
    if len(words)!=(bit_count+31)//32:raise ValueError('Payload word count')
    raw=b''.join(int(w).to_bytes(4,'little') for w in words)
    stream=''.join(format(b,'08b') for b in raw)
    if any(c!='0' for c in stream[bit_count:]):raise ValueError('Nonzero padding')
    stream=stream[:bit_count];position=0;values=[]
    def get(n):
        nonlocal position
        if position+n>bit_count:raise ValueError('Truncated code')
        text=stream[position:position+n];position+=n
        return int(text,2) if n else 0
    total=rows*cols
    while len(values)<total:
        count=min(32,total-len(values));raw_block=get(1);block=[];rice_cost=0
        for _ in range(count):
            if raw_block:
                byte=get(8);signed=byte if byte<128 else byte-256
                u=-2*signed-1 if signed<0 else 2*signed
            else:
                q=0
                while get(1):
                    q+=1
                    if q>(255>>k):raise ValueError('Unary outside byte range')
                u=(q<<k)|get(k)
                if u>255:raise ValueError('Symbol outside byte range')
                signed=-(u+1)//2 if u&1 else u//2
                byte=signed&255
            rice_cost+=(u>>k)+1+k;block.append(byte)
        if bool(raw_block)!=(rice_cost>=8*count):raise ValueError('Noncanonical block mode')
        values.extend(block)
    if position!=bit_count:raise ValueError('Trailing bits')
    values=np.asarray(values,dtype=np.uint8).reshape(rows,cols)
    if delta:values=(np.cumsum(values.astype(np.int64),axis=0)&255).astype(np.uint8)
    return values


def read_input(packet):
    if packet[0]!=INPUT_MAGIC:raise ValueError('Input format')
    xbits=packet[1];wbits=packet[2:10]
    if len(wbits)!=8 or not 0<xbits<=6336*8+198:raise ValueError('X/header length')
    if any(not 0<v<=2048*8+64 for v in wbits):raise ValueError('W length')
    bias=np.frombuffer(struct.pack('<128I',*packet[10:138]),dtype='<i2').copy()
    shifts=np.frombuffer(struct.pack('<64I',*packet[138:202]),dtype=np.uint8).copy()
    if np.any(shifts>47):raise ValueError('Invalid shift')
    position=202;n=(xbits+31)//32
    x=decode_stream(packet[position:position+n],xbits,99,64,2,True);position+=n
    w=np.empty((64,256),dtype=np.uint8)
    for group,bits in enumerate(wbits):
        n=(bits+31)//32
        w[:,32*group:32*(group+1)]=decode_stream(packet[position:position+n],bits,64,32,5,False)
        position+=n
    if position!=len(packet):raise ValueError('Trailing input words')
    return x,w,bias,shifts


def read_output(packet):
    if len(packet)!=6385 or packet[0]!=OUTPUT_MAGIC:raise ValueError('Output format/allocation')
    y=np.empty((99,256),dtype=np.uint8)
    for tile,bits in enumerate(packet[1:17]):
        if not 0<bits<=12722:raise ValueError('Output bit count')
        n=(bits+31)//32;base=17+tile*SLOT_WORDS
        y[:,16*tile:16*(tile+1)]=decode_stream(packet[base:base+n],bits,99,16,3,True)
        if any(w!=POISON for w in packet[base+n:base+SLOT_WORDS]):raise ValueError('Unused slot overwritten')
    return y


def words_hex(path,words):path.write_text(''.join(f'{int(w):08x}\n' for w in words))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sample',type=int,default=9)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    codec_dir=ROOT/'experiments/codec/rice32'
    manifest=json.loads((codec_dir/'SOURCE_SHA256.json').read_text())
    # Import only the frozen independent software bit writer, never RTL internals.
    spec=importlib.util.spec_from_file_location('frozen_rice_vector_writer',codec_dir/'run_checks.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    frozen=ROOT/'build/global_codec_budget_20261112/frozen_global_codecs.json'
    assert sha(frozen)=='e5e2618ef86c7cf237fde66785b5981c0245c55ecd6cb262031405f620ba0d28'
    codecs=json.loads(frozen.read_text())['codecs']['global_rice32']
    assert [(codecs[x]['k'],codecs[x]['row_delta']) for x in ['x','w','y']]==[(2,True),(5,False),(3,True)]
    precision=ROOT/'build/precision_bandwidth_20261111'
    frozen_configs=json.loads((precision/'frozen_config_sha256.json').read_text())
    study=json.loads((precision/'result.json').read_text())
    ids={(v['role'],v['layer']):v['sha256'] for v in study['inputs']}
    tiled=json.loads((ROOT/'build/tiled_codec_budget_20261112/result.json').read_text())
    contract=ROOT/'experiments/integration/int8stream/contract.json'
    result={'passed':False,'script_sha256':sha(Path(__file__)),'contract_sha256':sha(contract),
      'codec_writer_sha256':sha(codec_dir/'run_checks.py'),'codec_source_manifest_sha256':sha(codec_dir/'SOURCE_SHA256.json'),
      'frozen_global_sha256':sha(frozen),'sample_index':a.sample,'layers':[],
      'scope':'Complete packet serialization, independent parse and dense/tiled integer equivalence; not RTL/PPA or official score'}
    (a.output/'preregistration.json').write_text(json.dumps(result,indent=2)+'\n')
    for layer in range(12):
        path=ROOT/'build/model_reference_20261111_201956_613/float_validation'/f'layer{layer:02d}.npz'
        cp=precision/'x8_w8_y8_h0'/f'layer{layer:02d}.json'
        assert sha(path)==ids['validation',layer] and sha(cp)==frozen_configs['x8_w8_y8_h0/'+cp.name]
        cfg=json.loads(cp.read_text());data=numeric.load(path,'validation')
        x,w,y=quantized(data,cfg);x=x[a.sample];y=y[a.sample]
        bias=np.rint(data['b'].astype(np.float64)/np.exp2(np.asarray(cfg['w_exponents'])+cfg['x_exponent'])).astype(np.int64)
        assert np.all((bias>=-32768)&(bias<=32767))
        xb=module.encode_bytes(x,2,True)
        wb=[module.encode_bytes(w[:,g*32:(g+1)*32],5,False) for g in range(8)]
        yb=[module.encode_bytes(y[:,t*16:(t+1)*16],3,True) for t in range(16)]
        input_words=[INPUT_MAGIC,len(xb),*map(len,wb)]
        input_words+=list(struct.unpack('<128I',bias.astype('<i2').tobytes()))
        input_words+=list(struct.unpack('<64I',np.asarray(cfg['shifts'],dtype=np.uint8).tobytes()))
        input_words+=bits_words(xb)
        for bits in wb:input_words+=bits_words(bits)
        output_words=[POISON]*6385
        output_words[:17]=[OUTPUT_MAGIC,*map(len,yb)]
        for tile,bits in enumerate(yb):
            words=bits_words(bits);start=17+tile*SLOT_WORDS
            assert len(words)<=SLOT_WORDS;output_words[start:start+len(words)]=words
        rx,rw,rb,rs=read_input(input_words);ry=read_output(output_words)
        assert np.array_equal(rx,(x&255).astype(np.uint8)) and np.array_equal(rw,(w&255).astype(np.uint8))
        assert np.array_equal(rb,bias) and np.array_equal(rs,cfg['shifts'])
        assert np.array_equal(ry,(y&255).astype(np.uint8))
        # Direct dot and RNE computed from decoded packet, independent of tiles.
        accum=rx.view(np.int8).astype(np.int64)@rw.view(np.int8).astype(np.int64)+rb
        reconstructed=np.stack([np.clip(numeric.rounded(accum[:,j],int(rs[j])),-128,127) for j in range(256)],axis=1)
        assert np.array_equal(reconstructed,y)
        expected=tiled['candidates']['global_rice32']['layers'][layer]['samples'][a.sample]
        actual_output=17+sum((len(v)+31)//32 for v in yb)
        assert len(input_words)==expected['input_words'] and actual_output==expected['output_words']
        target=a.output/f'layer{layer:02d}';target.mkdir()
        words_hex(target/'input.hex',input_words)
        words_hex(target/'expected_output.hex',output_words)
        words_hex(target/'expected_dense.hex',np.frombuffer((y&255).astype(np.uint8).tobytes(),dtype='<u4'))
        entry={'layer':layer,'sample_index':a.sample,'input_words':len(input_words),'output_written_words':actual_output,
               'output_allocation_words':6385,'x_bits':len(xb),'w_group_bits':list(map(len,wb)),'y_tile_bits':list(map(len,yb)),
               'source_sha256':sha(path),'config_sha256':sha(cp),'files_sha256':{f.name:sha(f) for f in target.iterdir()}}
        (target/'manifest.json').write_text(json.dumps(entry,indent=2)+'\n');result['layers'].append(entry)
        print('PACKET',layer,'PASS',flush=True)
    result['passed']=True
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(a.output/'result.json',flush=True)


if __name__=='__main__':main()
