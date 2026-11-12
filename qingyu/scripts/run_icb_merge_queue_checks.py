"""Check queued ICB arbitration independently of the SoC and firmware."""
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
    parser.add_argument('--iverilog', default=shutil.which('iverilog') or 'G:/iverilog/bin/iverilog.exe')
    parser.add_argument('--vvp', default=shutil.which('vvp') or 'G:/iverilog/bin/vvp.exe')
    parser.add_argument('--seed', type=int, action='append')
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = ROOT / 'build/icb_queue_checks' / stamp
    output.mkdir(parents=True)
    sources = [Path('tb/tb_icb_merge_queue.sv'),
               Path('experiments/h1500v/opt24_busqueue/rtl/qingyu_icb_merge.sv')]
    result = dict(passed=False, sources_sha256={str(p): hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}, runs=[])
    for ports, depth, mask in [(6, 1, 63), (6, 3, 63), (6, 4, 63), (2, 4, 1), (2, 8, 1)]:
        name = f'p{ports}_d{depth}_m{mask}'
        executable = output / (name + '.vvp')
        command = [args.iverilog, '-g2012', '-s', 'tb_icb_merge_queue',
                   f'-Ptb_icb_merge_queue.NP={ports}', f'-Ptb_icb_merge_queue.DEPTH={depth}',
                   f'-Ptb_icb_merge_queue.MASK={mask}', '-o', str(executable.relative_to(ROOT)),
                   *map(str, sources)]
        with (output/(name+'_compile.log')).open('w') as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        for seed in args.seed or [17, 271, 818]:
            log_path = output / (name + f'_seed{seed}.log')
            command = [args.vvp, str(executable.relative_to(ROOT)), f'+SEED={seed}']
            with log_path.open('w') as log:
                completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=90)
            text = log_path.read_text(errors='replace')
            passed = completed.returncode == 0 and 'PASS queue ' in text
            result['runs'].append(dict(ports=ports, depth=depth, mask=mask, seed=seed,
                                       passed=passed, log=log_path.relative_to(ROOT).as_posix(),
                                       output=text.strip()))
            (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
            print(name, 'seed', seed, 'PASS' if passed else 'FAIL', flush=True)
            if not passed:
                raise RuntimeError(str(log_path) + '\n' + text)
    result['passed'] = True
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(output/'result.json')


if __name__ == '__main__':
    main()
