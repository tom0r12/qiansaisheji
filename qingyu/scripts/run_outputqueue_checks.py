"""Exercise output credit, write retirement, errors and reset with an independent stream.

The stream is an explicitly synthetic protocol fixture. Full numerical behavior
is separately checked by the real-accelerator SoC runner.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',default='opt32_outputqueue')
    args=parser.parse_args()
    out=ROOT/'build/outputqueue_checks'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True)
    base=ROOT/'experiments/h1500v'/args.candidate/'rtl'
    sources=[ROOT/'tb/tb_outputqueue_stream_source.sv',base/'qingyu_fio.sv',base/'qingyu_icb_merge.sv',ROOT/'tb/tb_outputqueue_faults.sv']
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    result=dict(passed=False,candidate=args.candidate,scope='Synthetic independent stream; protocol only, not arithmetic/PPA',source_sha256=hashes,runs=[])
    def save(): (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    defines=['QINGYU_BLOCK_COPY','QINGYU_READ_AHEAD','QINGYU_FAST_TASK','QINGYU_DOUBLE_BUFFER','QINGYU_PIPE_MAC','QINGYU_OUT16']
    commands=[('compile',['iverilog','-g2012','-s','tb_outputqueue_faults',*['-D'+d for d in defines],'-o',str(out/'run.vvp'),*map(str,sources)])]
    commands += [(str(seed),['vvp',str(out/'run.vvp'),f'+SEED={seed}']) for seed in [17,271,818]]
    try:
        for name,cmd in commands:
            proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=120)
            log=out/(name+'.log');log.write_text(proc.stdout+proc.stderr)
            passed=proc.returncode==0 and (name=='compile' or 'PASS outputqueue all scenarios' in proc.stdout)
            result['runs'].append(dict(name=name,command=cmd,passed=passed,log=log.relative_to(ROOT).as_posix(),log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()));save()
            if not passed: raise RuntimeError((proc.stdout+proc.stderr)[-6000:])
            print(name,'PASS',flush=True)
        if hashes!={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}: raise RuntimeError('Source changed')
        result['passed']=True
    finally:
        save();print(out/'result.json',flush=True)

if __name__=='__main__':main()
