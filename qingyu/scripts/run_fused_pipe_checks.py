"""Check fused FIFO order, independent read/write progress, and mid-stream faults."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', default='opt30_fusedpipe4')
    parser.add_argument('--iverilog', default=shutil.which('iverilog') or 'G:/iverilog/bin/iverilog.exe')
    parser.add_argument('--vvp', default=shutil.which('vvp') or 'G:/iverilog/bin/vvp.exe')
    args = parser.parse_args()
    candidate = ROOT/'experiments/h1500v'/args.candidate/'rtl'
    work = ROOT/'build/fused_pipe_checks'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    work.mkdir(parents=True)
    sources = [ROOT/'rtl/qingyu_sram16.sv', candidate/'qingyu_accel.sv',
               candidate/'qingyu_fio.sv', candidate/'qingyu_icb_merge.sv',
               ROOT/'tb/tb_fused_pipe.sv']
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    result = dict(passed=False, candidate=args.candidate, sources_sha256=hashes,
                  scope='three seeds, full X/W loads, unique address-derived data, mid-stream read/write faults; no PPA claim', stages=[])
    defines = ['QINGYU_BLOCK_COPY', 'QINGYU_READ_AHEAD', 'QINGYU_FAST_TASK',
               'QINGYU_DOUBLE_BUFFER', 'QINGYU_PIPE_MAC', 'QINGYU_OUT16']
    commands = [('compile', [args.iverilog, '-g2012', '-s', 'tb_fused_pipe',
                             *['-D'+d for d in defines], '-o', str(work/'faults.vvp'), *map(str, sources)]),
                ('simulate', [args.vvp, str(work/'faults.vvp')])]
    try:
        for stage, command in commands:
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
            log = completed.stdout + completed.stderr
            (work/(stage+'.log')).write_text(log)
            result['stages'].append(dict(stage=stage, command=command, returncode=completed.returncode))
            if completed.returncode:
                raise RuntimeError(log[-4000:])
        if 'PASS fused pipeline ordering, full buffers, concurrent requests and mid-stream errors' not in log:
            raise RuntimeError('Success marker missing')
        if hashes != {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}:
            raise RuntimeError('Sources changed while checking')
        result['passed'] = True
        print(log, end='')
    finally:
        (work/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(work/'result.json', flush=True)


if __name__ == '__main__':
    main()
