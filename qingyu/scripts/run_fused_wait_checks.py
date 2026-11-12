"""Check bounded WAIT_FUSED and independent DMA progress, without SoC/PPA claims."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', default='opt27_fusedwait')
    parser.add_argument('--queue', action='store_true', help='Also exercise metadata/fused timeout and reset/drain')
    args = parser.parse_args()
    candidate = ROOT / 'experiments/h1500v' / args.candidate / 'rtl'
    work = ROOT / 'build' / ('fused_wait_' + args.candidate + '_' +
                            datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
    work.mkdir(parents=True)
    top = 'tb_fused_wait_queue' if args.queue else 'tb_fused_wait'
    sources = [ROOT/'rtl/qingyu_sram16.sv', candidate/'qingyu_accel.sv',
               candidate/'qingyu_fio.sv', candidate/'qingyu_icb_merge.sv',
               ROOT/'tb'/f'{top}.sv']
    def snapshot():
        return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    hashes = snapshot()
    report = {'candidate':args.candidate, 'passed':False, 'sources_sha256':hashes,
              'scope':'WAIT control and data protocol, not performance or PPA',
              'test_wait_timeout_cycles':256, 'concurrent_metadata_timeout':args.queue, 'stages':[]}
    defines = ['QINGYU_BLOCK_COPY','QINGYU_READ_AHEAD','QINGYU_FAST_TASK',
               'QINGYU_DOUBLE_BUFFER','QINGYU_PIPE_MAC','QINGYU_OUT16']
    commands = [('compile',['iverilog','-g2012','-s',top,
                           *['-D'+d for d in defines],'-o',str(work/'wait.vvp'),*map(str,sources)]),
                ('simulate',['vvp',str(work/'wait.vvp')])]
    try:
        for stage,command in commands:
            result = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=120)
            log = result.stdout+result.stderr
            (work/(stage+'.log')).write_text(log,encoding='utf-8')
            report['stages'].append({'stage':stage,'command':command,'returncode':result.returncode})
            if result.returncode:
                raise RuntimeError(log[-4000:])
        if 'PASS bounded WAIT_FUSED, independent DMA progress and stable status responses' not in log:
            raise RuntimeError('Missing success marker')
        if hashes != snapshot():
            raise RuntimeError('Sources changed while checking')
        report['passed'] = True
        print(log,end='')
    finally:
        (work/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print('Evidence: '+str(work/'result.json'),flush=True)


if __name__ == '__main__':
    main()
