"""Measure unchanged official memory-fabric bandwidth with an ideal 1-cycle slave.

Run in WSL: python3 scripts/run_official_memfab_bandwidth.py
MODE=0 supplies saturated ordered traffic; MODE=1 limits the source to one
outstanding request while allowing response and next command on the same edge.
This is a cycle-level bandwidth test, not SRAM timing, power or official scoring.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
COMMIT='9f3e34f337f5d0a1236a285871ffa2032491617a'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iverilog',default=shutil.which('iverilog') or 'G:/iverilog/bin/iverilog.exe')
    parser.add_argument('--vvp',default=shutil.which('vvp') or 'G:/iverilog/bin/vvp.exe')
    args=parser.parse_args()
    out=ROOT/'build/memfab_bandwidth'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True)
    vendor=ROOT/'vendor/e203_hbirdv2'
    manifest_path=ROOT/'reports/e203-source-manifest.json'
    manifest=json.loads(manifest_path.read_text())
    if not manifest.get('ready') or manifest.get('commit')!=COMMIT:
        raise ValueError('A validated pinned E203 inventory is required')
    # Vendor DFFs contain #1 delays. A TB-only timescale does not affect earlier files.
    timescale=out/'timescale.v'
    timescale.write_text('`timescale 1ns/1ps\n')
    sources=[timescale]
    for path in sorted((vendor/'rtl').rglob('*.v')):
        entry=manifest['files'][path.relative_to(vendor).as_posix()]
        if sha(path)!=entry['sha256'] or not entry['matches_commit']:
            raise ValueError('Official source differs: '+str(path))
        sources.append(path)
    sources.append(ROOT/'tb/tb_official_memfab_bandwidth.sv')
    hashes={p.relative_to(ROOT).as_posix():sha(p) for p in sources}
    runner_hash=sha(Path(__file__))
    result={'passed':False,'source_sha256':hashes,'runner_sha256':runner_hash,
            'vendor_commit':COMMIT,'vendor_manifest_sha256':sha(manifest_path),
            'scope':'Unmodified e203_subsys_mems and parameters; synchronous reads and optional same-accept-edge write completion with elastic backpressure; no SRAM/PPA signoff',
            'timebase':'All vendor files use 1ns/1ps; benchmark clock period is 10ns. Only cycle ratios are reported.',
            'configuration':{'ICB_FIFO_DP':2,'ICB_FIFO_CUT_READY':1,'SPLT_FIFO_OUTS_NUM':1,'SPLT_FIFO_CUT_READY':1,'ALLOW_0CYCL_RSP_default':1},
            'traffic_modes':{'0':'saturated source','1':'one outstanding, same-edge response/reissue allowed'},
            'read_patterns':{'0':'all writes','1':'alternating write/read','2':'all reads'},
            'runs':[],'commands':[]}
    def save():
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    def execute(command,log):
        result['commands'].append(list(map(str,command)));save()
        proc=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=90)
        log.write_text(proc.stdout+proc.stderr)
        proc.check_returncode()
        return proc.stdout+proc.stderr
    save()
    try:
        executable=out/'run.vvp'
        command=[args.iverilog,'-g2012','-DDISABLE_SV_ASSERTION=1','-s','tb_official_memfab_bandwidth','-o',str(executable.relative_to(ROOT))]
        command+=['-I'+str((vendor/'rtl/e203'/d).relative_to(ROOT)) for d in ['core','perips','perips/apb_i2c']]
        command+=[p.relative_to(ROOT).as_posix() for p in sources]
        execute(command,out/'compile.log')
        for zero_write,mode,mixed,stall,rsp_stall in [(z,m,p,s,r) for z in [0,1] for m,p,s,r in ([(m,p,0,0) for m in [0,1] for p in [0,1,2]]+[(m,1,1,1) for m in [0,1]])]:
            name=f'zero{zero_write}_mode{mode}_pattern{mixed}_stall{stall}_rsp{rsp_stall}'
            command=[args.vvp,str(executable.relative_to(ROOT)),f'+MODE={mode}',f'+MIXED={mixed}',f'+STALL={stall}',f'+RSP_STALL={rsp_stall}',f'+ZERO_WRITE={zero_write}']
            log=out/(name+'.log')
            output=execute(command,log)
            lines=[s for s in output.splitlines() if s.startswith('PASS official_memfab ')]
            if len(lines)!=1:raise RuntimeError('Missing unique pass record: '+name)
            row={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',lines[0])}
            row.update(log=log.relative_to(ROOT).as_posix(),log_sha256=sha(log),
                       measured_shared_ii=row['shared_span']/(row['words']-1),
                       mean_source_response_latency=row['latency_sum']/row['words'])
            result['runs'].append(row);save();print(lines[0],flush=True)
        if hashes!={p.relative_to(ROOT).as_posix():sha(p) for p in sources} or sha(Path(__file__))!=runner_hash:
            raise RuntimeError('Source changed during execution')
        result['passed']=True
    except Exception as error:
        result['failure']=str(error)
        save()
        raise
    save()
    print(out/'result.json',flush=True)


if __name__=='__main__':main()
