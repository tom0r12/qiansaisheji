"""Verify shared SRAM response semantics using behavior and macro-wrapper models."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    output=ROOT/'build/shared_fastwrite_checks'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    base=ROOT/'experiments/h1500v/opt31_fastwrite/rtl'
    report={'passed':False,'scope':'Protocol and memory semantics only; local functional macro stand-in, not actual vendor timing/PPA','runs':[],'source_sha256':{}}
    for mode,sources in [('behavior',[base/'qingyu_shared_sram.sv']),('macro_wrapper',[base/'asic/qingyu_shared_sram.sv',ROOT/'rtl/asic/qingyu_banked_sram.sv',ROOT/'tb/ramsp4096x16_functional.sv'])]:
        sources=[ROOT/'tb/tb_shared_fastwrite.sv',*sources]
        report['source_sha256'].update({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
        exe=output/(mode+'.vvp')
        cmd=['iverilog','-g2012','-s','tb_shared_fastwrite','-o',str(exe),*map(str,sources)]
        with (output/(mode+'_compile.log')).open('w') as f:
            subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
        for seed in [17,271,818]:
            log=output/f'{mode}_{seed}.log'
            with log.open('w') as f:
                p=subprocess.run(['vvp',str(exe),f'+SEED={seed}'],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=90)
            text=log.read_text();passed=p.returncode==0 and 'PASS shared_fastwrite ' in text
            report['runs'].append(dict(mode=mode,seed=seed,passed=passed,log=log.relative_to(ROOT).as_posix(),output=text.strip()))
            (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
            print(mode,seed,'PASS' if passed else 'FAIL',flush=True)
            if not passed:raise RuntimeError(text)
    for name,expected in report['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise ValueError('Source changed: '+name)
    report['passed']=True
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(output/'result.json')

if __name__=='__main__':main()
