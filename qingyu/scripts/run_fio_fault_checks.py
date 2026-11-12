"""Exercise transport errors and response backpressure at the FIO boundary."""
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
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--fused', action='store_true')
    args = parser.parse_args()
    candidate = ROOT / 'experiments/h1500v' / args.candidate / 'rtl'
    work = ROOT / 'build' / ('fio_faults_' + args.candidate + '_' +
                            datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
    work.mkdir(parents=True)
    sources = [ROOT/'rtl/qingyu_sram16.sv', candidate/'qingyu_accel.sv',
               candidate/'qingyu_fio.sv', candidate/'qingyu_icb_merge.sv',
               ROOT/'tb/tb_fio_faults.sv']
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sources}
    report = {'candidate': args.candidate, 'passed': False, 'sources_sha256': hashes,
              'scope': 'FIO transport errors; no SoC performance or PPA claim', 'stages': []}
    defines = ['QINGYU_BLOCK_COPY', 'QINGYU_READ_AHEAD', 'QINGYU_FAST_TASK',
               'QINGYU_DOUBLE_BUFFER', 'QINGYU_PIPE_MAC', 'QINGYU_OUT16']
    commands = [('compile', ['iverilog', '-g2012', '-s', 'tb_fio_faults',
                            *['-D'+d for d in defines], '-o', str(work/'faults.vvp'),
                            *map(str, sources)]),
                ('simulate', ['vvp', str(work/'faults.vvp'), '+FUSED='+str(int(args.fused))])]
    try:
        for stage, command in commands:
            process = subprocess.run(command, cwd=ROOT, capture_output=True,
                                     text=True, timeout=120)
            log = process.stdout + process.stderr
            (work/(stage+'.log')).write_text(log, encoding='utf-8')
            report['stages'].append({'stage':stage, 'command':command,
                                     'returncode':process.returncode})
            if process.returncode:
                raise RuntimeError(log[-4000:])
        if 'PASS FIO transport faults and hardware-reset recovery' not in log:
            raise RuntimeError('Missing success marker')
        if hashes != {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sources}:
            raise RuntimeError('Sources changed while checking')
        report['passed'] = True
        print(log, end='')
    finally:
        (work/'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print('Evidence: '+str(work/'result.json'), flush=True)


if __name__ == '__main__':
    main()
