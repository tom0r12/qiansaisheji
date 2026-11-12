"""Check opt33 byte-address compatibility and physical bank wiring in four states."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT / 'build/shared_readcache_checks' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True, exist_ok=False)
    base = ROOT / 'experiments/h1500v/opt33_readcache/rtl'
    report = {'passed': False, 'runs': [], 'source_sha256': {},
              'scope': 'Behavior and 64-macro physical-wrapper storage/protocol wiring; original low-byte address convention',
              'limits': ['Local four-state functional macro with write-Q poisoning, not manufacturer timing/PPA',
                         'All tested words initialized and read back through real bus commands',
                         'No formal equivalence, STA, official 600-sample or power claim']}
    def save():
        (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    save()
    modes = [('behavior', [base/'qingyu_shared_sram.sv']),
             ('macro_wrapper', [base/'asic/qingyu_shared_sram.sv', ROOT/'rtl/asic/qingyu_banked_sram.sv', ROOT/'tb/ramsp4096x16_qpoison.sv'])]
    report['source_sha256'][Path(__file__).relative_to(ROOT).as_posix()] = sha(Path(__file__))
    for mode, sources in modes:
        sources = [ROOT/'tb/tb_shared_readcache_wrapper.sv', *sources]
        report['source_sha256'].update({p.relative_to(ROOT).as_posix(): sha(p) for p in sources})
        executable = output/(mode+'.vvp')
        with (output/(mode+'_compile.log')).open('w') as log:
            result = subprocess.run(['iverilog','-g2012','-Wall','-s','tb_shared_readcache_wrapper','-o',str(executable),*map(str,sources)], stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            save()
            raise SystemExit(f'Compile failed: {output}')
        for seed in [17,271,818]:
            log_path = output/f'{mode}_{seed}.log'
            with log_path.open('w') as log:
                result = subprocess.run(['vvp',str(executable),f'+SEED={seed}'], stdout=log, stderr=subprocess.STDOUT, timeout=90)
            text = log_path.read_text()
            line = next((x for x in text.splitlines() if x.startswith('PASS shared_readcache_wrapper ')), None)
            passed = result.returncode == 0 and line is not None
            report['runs'].append(dict(mode=mode, seed=seed, passed=passed, returncode=result.returncode,
                                      log=log_path.relative_to(ROOT).as_posix(), log_sha256=sha(log_path),
                                      metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line or '')}))
            save()
            print(mode,seed,'PASS' if passed else 'FAIL',flush=True)
            if not passed:
                raise SystemExit(text)
    for path,digest in report['source_sha256'].items():
        if sha(ROOT/path) != digest:
            raise SystemExit('Source changed during test: '+path)
    report['passed'] = True
    save()
    print(output/'result.json',flush=True)


if __name__ == '__main__':
    main()
