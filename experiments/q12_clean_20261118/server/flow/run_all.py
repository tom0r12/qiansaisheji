"""Run all candidates: candidate k+1 starts when candidate k's DC synthesis
(both whole-SoC synth and standalone u_fio 5-corner fio_synth) has finished;
vendor/formal/PT/GLS overlap across candidates.
Writes ~/Desktop/q12clean_SUMMARY.txt and archives all reports to ~/Desktop/q12clean6_reports_archive.tar.gz.
"""
from pathlib import Path
import datetime, hashlib, json, os, shutil, subprocess, sys, tarfile, time

HERE = Path(__file__).resolve().parent
OUT = Path.home() / 'Desktop' / 'q12clean_SUMMARY.txt'
ARCHIVE = Path.home() / 'Desktop' / 'q12clean6_reports_archive.tar.gz'
KEEP_EXTS = {'.rpt', '.log', '.txt', '.json', '.sdc', '.tsv'}


def sha256_file(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def archive_reports(runs):
    count = 0
    with tarfile.open(str(ARCHIVE), 'w:gz') as tf:
        for label, rdir in sorted(runs.items()):
            if not rdir.is_dir(): continue
            for p in sorted(rdir.rglob('*')):
                if not p.is_file(): continue
                if p.suffix.lower() not in KEEP_EXTS: continue
                if p.stat().st_size > 25_000_000: continue
                arcname = '%s_%s/%s' % (label, rdir.name, p.relative_to(rdir).as_posix())
                tf.add(str(p), arcname=arcname)
                count += 1
    return count, ARCHIVE.stat().st_size, sha256_file(ARCHIVE)


def combine(runs, extra=''):
    parts = []
    for label, run in runs.items():
        s = run / 'SUMMARY.txt'
        parts.append(s.read_text(errors='replace') if s.is_file() else '== %s: running (%s)\n' % (label, run))
    if extra:
        parts.append(extra)
    text = '\n'.join(parts)
    for target in [OUT] + [run.parent / 'q12clean_SUMMARY.txt' for run in runs.values()][:1]:
        try: target.write_text(text)
        except OSError as e: print('summary write failed %s: %s' % (target, e), flush=True)


def main():
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
        raise SystemExit('Q12_DISK_TOO_SMALL: no work root with >= %.0f GB free.' % need)
    os.environ['Q12_WORK_ROOT'] = str(work)
    print('Q12_WORK_ROOT=' + str(work), flush=True)
    ident = json.loads((HERE / 'package_identity.json').read_text())
    for n, h in ident['files'].items():
        if hashlib.sha256((HERE / n).read_bytes()).hexdigest() != h:
            raise SystemExit('Package file changed: ' + n)
    labels = json.loads((HERE / 'candidates.json').read_text())
    procs = []; runs = {}
    for label in labels:
        log = HERE / ('flow_%s.log' % label)
        p = subprocess.Popen([sys.executable, '-u', str(HERE / 'qflow.py'), '--cand', str(HERE / label)] + sys.argv[1:],
                             stdout=log.open('w'), stderr=subprocess.STDOUT, cwd=str(HERE))
        procs.append((label, p, log)); print(datetime.datetime.now(), 'started', label, flush=True)
        while True:
            time.sleep(25)
            t = log.read_text(errors='replace')
            if 'Q12_CLEAN_RUN=' in t:
                runs[label] = Path(t.split('Q12_CLEAN_RUN=')[1].split()[0])
            if (label in runs and (runs[label] / 'SYNTH_DONE').exists()) or p.poll() is not None:
                break
        combine(runs)
    while any(p.poll() is None for _, p, _ in procs):
        time.sleep(45); combine(runs)
    extra = ''
    try:
        cnt, sz, digest = archive_reports(runs)
        extra = '== ARCHIVE: path=%s files=%d bytes=%d sha256=%s\n' % (ARCHIVE, cnt, sz, digest)
        print(extra.strip(), flush=True)
    except BaseException as e:
        extra = '== ARCHIVE_WARNING: %r\n' % (e,)
        print(extra.strip(), flush=True)
    combine(runs, extra)
    print('Q12_ALL_DONE ' + str(OUT), flush=True)


if __name__ == '__main__':
    main()
