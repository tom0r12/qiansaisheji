"""Run all candidates: candidate k+1 starts when candidate k's DC synthesis has
finished (avoids concurrent DC licenses); vendor/formal/PT overlap.
Writes ~/Desktop/q12clean_SUMMARY.txt combining every candidate summary."""
from pathlib import Path
import hashlib, json, subprocess, sys, time, datetime
HERE = Path(__file__).resolve().parent
OUT = Path.home() / 'Desktop' / 'q12clean_SUMMARY.txt'


def main():
    import os, shutil
    need = float(os.environ.get('Q12_MIN_FREE_GB', '15'))
    choices = ([Path(os.environ['Q12_WORK_ROOT'])] if os.environ.get('Q12_WORK_ROOT') else []) + \
              [Path('/tmp'), Path.home() / 'Desktop' / 'q12work']
    work = None
    for c in choices:
        try:
            c.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(str(c)).free / 1e9
        except OSError as e:
            print('work root %s unusable: %s' % (c, e), flush=True); continue
        print('work root %s free %.1f GB (need %.0f GB) writable=%s' % (c, free, need, os.access(str(c), os.W_OK)), flush=True)
        if free >= need and os.access(str(c), os.W_OK):
            work = c; break
    if work is None:
        raise SystemExit('Q12_DISK_TOO_SMALL: no work root with >= %.0f GB free; free space (see 服务器操作 02) or set Q12_WORK_ROOT.' % need)
    os.environ['Q12_WORK_ROOT'] = str(work)
    print('Q12_WORK_ROOT=' + str(work), flush=True)
    ident = json.loads((HERE / 'package_identity.json').read_text())
    for n, h in ident['files'].items():
        if hashlib.sha256((HERE / n).read_bytes()).hexdigest() != h: raise SystemExit('Package file changed: ' + n)
    labels = json.loads((HERE / 'candidates.json').read_text())
    procs = []; runs = {}
    for label in labels:
        log = HERE / ('flow_%s.log' % label)
        p = subprocess.Popen([sys.executable, '-u', str(HERE / 'qflow.py'), '--cand', str(HERE / label)] + sys.argv[1:],
                             stdout=log.open('w'), stderr=subprocess.STDOUT, cwd=str(HERE))
        procs.append((label, p, log)); print(datetime.datetime.now(), 'started', label, flush=True)
        while True:  # wait for this candidate's run dir and synthesis completion
            time.sleep(30)
            t = log.read_text(errors='replace')
            if 'Q12_CLEAN_RUN=' in t:
                runs[label] = Path(t.split('Q12_CLEAN_RUN=')[1].split()[0])
            if (label in runs and (runs[label] / 'SYNTH_DONE').exists()) or p.poll() is not None: break
        combine(runs)
    while any(p.poll() is None for _, p, _ in procs):
        time.sleep(60); combine(runs)
    combine(runs); print('Q12_ALL_DONE ' + str(OUT), flush=True)


def combine(runs):
    parts = []
    for label, run in runs.items():
        s = run / 'SUMMARY.txt'
        parts.append(s.read_text(errors='replace') if s.is_file() else '== %s: running (%s)\n' % (label, run))
    text = '\n'.join(parts)
    for target in [OUT] + [run.parent / 'q12clean_SUMMARY.txt' for run in runs.values()][:1]:
        try: target.write_text(text)
        except OSError as e: print('summary write failed %s: %s' % (target, e), flush=True)


if __name__ == '__main__':
    main()
