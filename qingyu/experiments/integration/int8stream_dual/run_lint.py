"""Strict lint of the experimental engine and selected real components in WSL."""
import argparse, hashlib, json, subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core-dir', type=Path, default=ROOT/'experiments/arithmetic/winograd_task8_overlap')
    a = p.parse_args()
    files = [HERE/'qingyu_int8stream_engine.sv',
             ROOT/'experiments/transport/icb_stream_prefix/qingyu_icb_stream_prefix.sv',
             ROOT/'experiments/codec/rice32/rice32_decoder.sv',
             ROOT/'experiments/codec/rice32/rice32_encoder.sv',
             ROOT/'experiments/transport/rowpair_pack/rowpair_pack.sv',
             a.core_dir.resolve()/'winograd_int8_task8.sv',
             ROOT/'experiments/arithmetic/winograd_array8/winograd_int8_pair_acc32.sv',
             ROOT/'rtl/qingyu_sram16.sv']
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = ROOT/'build/int8stream_dual_lint'/stamp
    out.mkdir(parents=True)
    before = {f.relative_to(ROOT).as_posix(): sha(f) for f in files}
    cmd = ['verilator', '--lint-only', '--Wall', '--top-module', 'qingyu_int8stream_engine', *map(str, files)]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    log = out/'lint.log'
    log.write_text(proc.stdout + proc.stderr)
    unchanged = all(sha(ROOT/f) == h for f, h in before.items())
    result = dict(passed=proc.returncode == 0 and unchanged, command=cmd, source_sha256=before,
                  returncode=proc.returncode, unchanged=unchanged, log_sha256=sha(log),
                  warnings=(proc.stdout+proc.stderr).count('%Warning'),
                  tool=subprocess.run(['verilator', '--version'], capture_output=True, text=True, check=True).stdout.strip(),
                  limitations=['RTL lint only; no STA, CDC, synthesis, physical SRAM or PPA conclusion'])
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(out/'result.json')
    if not result['passed']:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
