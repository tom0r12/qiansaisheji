"""Independent full X/W row-pair layout fixtures and ready/valid RTL checks."""
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
from analyze_lossless_command_budget import numeric,quantized,sha


def word_file(path,data):
    data=bytes(data)
    assert len(data)%4==0
    path.write_text(''.join(f'{int.from_bytes(data[i:i+4],"little"):08x}\n' for i in range(0,len(data),4)))


def golden(value,mode):
    """Direct coordinate gather, independent of RTL slot/word/half selectors."""
    result=[]
    rows,cols=value.shape
    for r in range(0,rows,2):
        for c in range(0,cols,2):
            if mode:
                result.extend([value[r,c],value[r+1,c],value[r,c+1],value[r+1,c+1]])
            else:
                result.extend([value[r,c],value[r,c+1],value[r+1,c] if r+1<rows else 0,
                               value[r+1,c+1] if r+1<rows else 0])
    return bytes(result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--quick',action='store_true')
    p.add_argument('--sim',choices=['iverilog','verilator'],default='iverilog')
    p.add_argument('--seeds',type=int,nargs='+',default=[17,271,20261112])
    args=p.parse_args()
    out=HERE/'runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
    rng=np.random.default_rng(20261112);cases=[];provenance=[]
    def add(value,mode,tag,stem=None):
        value=np.asarray(value,dtype=np.uint8)
        assert value.shape==((64,32) if mode else (99,64))
        stem=stem or f'case{len(cases):03d}'
        raw=out/(stem+'.raw.hex');gold=out/(stem+'.gold.hex')
        word_file(raw,value.tobytes());word_file(gold,golden(value,mode))
        cases.append(dict(id=len(cases),mode=mode,inputs=value.size//4,outputs=512 if mode else 1600,
                          raw=raw.name,gold=gold.name,tag=tag,raw_sha256=sha(raw),gold_sha256=sha(gold)))
    for mode in [0,1]:
        shape=(64,32) if mode else (99,64)
        add(rng.integers(0,256,shape,dtype=np.uint8),mode,'random',stem='direct_w' if mode else 'direct_x')
        for val in [0,128,255]:add(np.full(shape,val,dtype=np.uint8),mode,f'constant_{val}')
        rr,cc=np.indices(shape);add(((rr*37+cc*11)&255).astype(np.uint8),mode,'coordinate_tags')
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
            x,w,_=quantized(numeric.load(path,'validation'),json.loads(cp.read_text()))
            provenance.append(dict(layer=layer,sample_index=9,validation_sha256=sha(path),config_sha256=sha(cp)))
            add(x[9],0,f'layer{layer:02d}_x')
            for group in range(8):add(w[:,32*group:32*(group+1)],1,f'layer{layer:02d}_w_group{group}')
            print('VECTORS',layer,flush=True)
    (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    (out/'manifest.txt').write_text(''.join(f"{c['id']} {c['mode']} {c['inputs']} {c['outputs']} {c['raw']} {c['gold']}\n" for c in cases))
    files=[HERE/'rowpair_pack.sv',HERE/'tb_rowpair_pack.sv',HERE/'contract.json',Path(__file__)]
    hashes={q.name:sha(q) for q in files}
    result=out/'result.json'
    report=dict(schema='qingyu-rowpair-pack-rtl-check-v1',passed=False,simulator=args.sim,quick=args.quick,
                source_sha256_before=hashes,inputs=provenance,case_manifest_sha256=sha(out/'cases.json'),runs=[],
                limits=['Standalone adapter START through output ACK; codec/core/bus and headers excluded',
                        'No STA, area, power or full-task throughput measurement'])
    def save():result.write_text(json.dumps(report,indent=2)+'\n')
    save()
    lint=['verilator','--lint-only','-Wall','--top-module','rowpair_pack',str(files[0])]
    with (out/'rtl_lint.log').open('w') as log:
        check=subprocess.run(lint,cwd=out,stdout=log,stderr=subprocess.STDOUT)
    report['lint_returncode']=check.returncode;report['lint_command']=lint;save()
    if check.returncode:raise SystemExit('RTL lint failed '+str(out))
    if args.sim=='iverilog':
        exe=out/'rowpair.vvp';cmd=['iverilog','-g2012','-Wall','-s','tb_rowpair_pack','-o',str(exe),*map(str,files[:2])]
        run=['vvp',str(exe)]
    else:
        obj=out/'obj';cmd=['verilator','--binary','--timing','--assert','-Wno-fatal','--top-module','tb_rowpair_pack','-j','2','--Mdir',str(obj),*map(str,files[:2])]
        run=[str(obj/'Vtb_rowpair_pack')]
    with (out/'compile.log').open('w') as log:
        compiled=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT)
    report['compile_command']=cmd;report['compile_returncode']=compiled.returncode;save()
    if compiled.returncode:raise SystemExit('Compile failed '+str(out))
    for seed in args.seeds:
        path=out/f'seed{seed}.log'
        with path.open('w') as log:
            rc=subprocess.run([*run,f'+SEED={seed}','+MANIFEST=manifest.txt'],cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        content=path.read_text();passed=rc.returncode==0 and 'PASS rowpair ' in content
        metrics=[{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)} for line in content.splitlines() if line.startswith('CASE ')]
        summary=[{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)} for line in content.splitlines() if line.startswith('PASS rowpair ')]
        report['runs'].append(dict(seed=seed,passed=passed,log=path.name,cases=metrics,summary=summary));save()
        print('RUN',seed,'PASS' if passed else 'FAIL',flush=True)
        if not passed:print(content[-5000:]);raise SystemExit(str(result))
    report['source_sha256_after']={q.name:sha(q) for q in files}
    assert report['source_sha256_after']==hashes
    report['passed']=True;save();print(result,flush=True)


if __name__=='__main__':main()
