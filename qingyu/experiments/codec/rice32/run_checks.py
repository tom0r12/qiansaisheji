"""Independent Python bitstream fixtures and streaming Rice32 RTL checks."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from analyze_lossless_command_budget import numeric,quantized,sha,symbols


def encode_bytes(value,k,delta):
    data=symbols(value,delta).ravel()
    bits=[]
    for first in range(0,len(data),32):
        block=data[first:first+32]
        signed=[int(b) if b<128 else int(b)-256 for b in block]
        u=[-2*b-1 if b<0 else 2*b for b in signed]
        codes=['1'*(v>>k)+'0'+(format(v&((1<<k)-1),f'0{k}b') if k else '') for v in u]
        if sum(map(len,codes))>=8*len(block):bits.append('1'+''.join(format(int(b),'08b') for b in block))
        else:bits.append('0'+''.join(codes))
    return ''.join(bits)


def word_file(path,data):
    data=bytes(data);data+=b'\0'*((-len(data))%4)
    path.write_text(''.join(f'{int.from_bytes(data[i:i+4],"little"):08x}\n' for i in range(0,len(data),4)))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--quick',action='store_true')
    p.add_argument('--sim',choices=['iverilog','verilator'],default='iverilog')
    p.add_argument('--lanes',type=int,choices=[2,4],default=4)
    p.add_argument('--seeds',type=int,nargs='+',default=[17,271,20261112])
    args=p.parse_args()
    out=HERE/'runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
    frozen_path=ROOT/'build/global_codec_budget_20261112/frozen_global_codecs.json'
    assert sha(frozen_path)=='e5e2618ef86c7cf237fde66785b5981c0245c55ecd6cb262031405f620ba0d28'
    frozen=json.loads(frozen_path.read_text())['codecs']['global_rice32']
    cases=[]
    rng=np.random.default_rng(20261112)
    def add(value,k,delta,row,tag,mode=0,bits_override=None,declared_override=None):
        value=np.asarray(value,dtype=np.uint8)
        bits=encode_bytes(value,k,delta) if bits_override is None else bits_override
        index=len(cases);rp=out/f'case{index:03d}.raw.hex';bp=out/f'case{index:03d}.bits.hex'
        word_file(rp,value.tobytes())
        wire=bytes(int(bits[i:i+8].ljust(8,'0'),2) for i in range(0,len(bits),8))
        word_file(bp,wire)
        cases.append(dict(id=index,mode=mode,symbols=value.size,k=k,delta=int(delta),row=row,bits=len(bits),
                          declared_bits=len(bits) if declared_override is None else declared_override,
                          raw=rp.name,coded=bp.name,tag=tag,raw_sha256=sha(rp),coded_sha256=sha(bp)))
    lengths=[1,3,4,15,16,31,32,33,63,64,65,255,256,257]
    if args.quick:lengths=[1,16,32,65]
    for length in lengths:
        for k in ([2,3,5] if not args.quick else [2,3]):
            value=rng.integers(0,256,length,dtype=np.uint8)
            add(value.reshape(1,-1),k,False,16,f'random_tail_{length}_k{k}')
    for row in [16,64,256]:
        a=rng.integers(0,256,(3,row),dtype=np.uint8)
        a[1]=a[0];a[2]=(a[1].astype(np.uint16)+1).astype(np.uint8)
        add(a,3,True,row,f'delta_epoch_row{row}')
    for k in range(8):
        for value in ([0,128,127] if not args.quick else [0]):
            add(np.full((1,48),value,dtype=np.uint8),k,False,16,f'extreme_{value}_k{k}')
    # These malformed streams use the same declared transport interface.
    add(np.zeros((1,32),dtype=np.uint8),2,False,16,'unary_out_of_byte_range',1,'0'+'1'*64+'0'+'00')
    add(np.zeros((1,32),dtype=np.uint8),3,False,16,'noncanonical_raw',1,'1'+'0'*256)
    add(np.full((1,32),252,dtype=np.uint8),0,False,16,'noncanonical_rice_tie',1,'0'+('1'*7+'0')*32)
    good=encode_bytes(np.zeros((1,32),dtype=np.uint8),3,False)
    add(np.zeros((1,32),dtype=np.uint8),3,False,16,'truncated_semantic',1,good[:-1])
    add(np.zeros((1,32),dtype=np.uint8),3,False,16,'declared_length_mismatch',1,good, len(good)+1)
    add(np.zeros((1,33),dtype=np.uint8),3,False,16,'missing_symbol',1,good)
    add(np.zeros((1,32),dtype=np.uint8),3,True,32,'invalid_delta_width',1,good)
    add(np.zeros((1,32),dtype=np.uint8),3,False,16,'nonzero_padding',1,good)
    last=cases[-1];path=out/last['coded'];words=path.read_text().splitlines()
    words[-1]=f'{int(words[-1],16)|1:08x}'
    path.write_text('\n'.join(words)+'\n');last['coded_sha256']=sha(path)
    add(np.zeros((1,31),dtype=np.uint8),0,False,16,'missing_last_then_drain',1,'0'*64,32)
    # No validation value is used to choose k, delta or code format.
    inputs=[]
    if not args.quick:
        reference=ROOT/'build/model_reference_20261111_201956_613'
        precision=ROOT/'build/precision_bandwidth_20261111'
        study=json.loads((precision/'result.json').read_text())
        ids={(x['role'],x['layer']):x['sha256'] for x in study['inputs']}
        numeric_hashes=json.loads((precision/'frozen_config_sha256.json').read_text())
        for layer in range(12):
            path=reference/'float_validation'/f'layer{layer:02d}.npz'
            cp=precision/'x8_w8_y8_h0'/f'layer{layer:02d}.json'
            assert sha(path)==ids['validation',layer]
            assert sha(cp)==numeric_hashes[f'x8_w8_y8_h0/layer{layer:02d}.json']
            values=quantized(numeric.load(path,'validation'),json.loads(cp.read_text()))
            inputs.append({'layer':layer,'validation_sha256':sha(path),'config_sha256':sha(cp),'sample_index':9})
            for key,value in zip(('x','w','y'),values):
                value=value if key=='w' else value[9]
                codec=frozen[key]
                add(value,codec['k'],codec['row_delta'],value.shape[1],f'validation_layer{layer:02d}_{key}')
                if key=='y':add(value[:,:16],codec['k'],codec['row_delta'],16,f'validation_layer{layer:02d}_y_tile0')
            print('VECTORS',layer,flush=True)
    (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    (out/'manifest.txt').write_text(''.join(f"{c['id']} {c['mode']} {c['symbols']} {c['k']} {c['delta']} {c['row']} {c['bits']} {c['declared_bits']} {c['raw']} {c['coded']}\n" for c in cases))
    sources=[HERE/'rice32_encoder.sv',HERE/'rice32_decoder.sv',HERE/'tb_rice32.sv',HERE/'contract.json',Path(__file__)]
    hashes={q.name:sha(q) for q in sources}
    report={'schema':'qingyu-rice32-rtl-check-v1','passed':False,'simulator':args.sim,'lanes':args.lanes,
            'quick':args.quick,'source_sha256_before':hashes,'frozen_codec_sha256':sha(frozen_path),'inputs':inputs,
            'case_manifest_sha256':sha(out/'cases.json'),'runs':[],
            'limits':['Standalone local START through final codec ACK; full SoC headers/fabric/compute excluded',
                      'No PPA, STA or official task throughput measured','Matrix-row-major codec; array8 layout integration separate']}
    result=out/'result.json'
    def save():result.write_text(json.dumps(report,indent=2)+'\n')
    save()
    report['lint']=[]
    for module in ['rice32_encoder','rice32_decoder']:
        command=['verilator','--lint-only','-Wall','--top-module',module,str(HERE/(module+'.sv'))]
        with (out/(module+'_lint.log')).open('w') as log:
            lint=subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT)
        report['lint'].append({'module':module,'returncode':lint.returncode,'command':command})
        save()
        if lint.returncode:raise SystemExit('RTL lint failed: '+module)
    if args.sim=='iverilog':
        exe=out/'rice32.vvp'
        cmd=['iverilog','-g2012','-Wall','-s','tb_rice32',f'-Ptb_rice32.LANES={args.lanes}','-o',str(exe),*map(str,sources[:3])]
        run=['vvp',str(exe)]
    else:
        obj=out/'obj'
        cmd=['verilator','--binary','--timing','--assert','-Wno-fatal','--top-module','tb_rice32',f'-GLANES={args.lanes}',
             '-j','2','--Mdir',str(obj),*map(str,sources[:3])]
        run=[str(obj/'Vtb_rice32')]
    report['compile_command']=cmd
    with (out/'compile.log').open('w') as log:compiled=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=out)
    report['compile_returncode']=compiled.returncode;save()
    if compiled.returncode:raise SystemExit(f'Compile failed {out}')
    for seed in args.seeds:
        log_path=out/f'seed{seed}.log'
        with log_path.open('w') as log:run_result=subprocess.run([*run,f'+SEED={seed}','+MANIFEST=manifest.txt'],cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=900)
        text=log_path.read_text();ok=run_result.returncode==0 and 'PASS rice32 ' in text
        metrics=[{key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',line)} for line in text.splitlines() if line.startswith('CASE ')]
        report['runs'].append({'seed':seed,'passed':ok,'log':log_path.name,'cases':metrics});save()
        print('RUN',seed,'PASS' if ok else 'FAIL',flush=True)
        if not ok:print(text[-5000:]);raise SystemExit(str(result))
    report['source_sha256_after']={q.name:sha(q) for q in sources}
    assert report['source_sha256_after']==hashes
    report['passed']=True;save();print(result,flush=True)


if __name__=='__main__':main()
