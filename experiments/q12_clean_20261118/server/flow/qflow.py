"""Clean Q12 server flow for ONE candidate directory:
vendor-SRAM VCS (+SAIF) || DC mapping -> Formality, PT power windows -> SUMMARY.txt

  python3 qflow.py --cand A            # candidate directory (has candidate.json, vendor/, hardware/)
  python3 qflow.py --summary RUN_DIR   # re-print summary of an existing run directory
Options: --layers 0,4,8,11|all (power windows), --compile ultra|medium, --no-gate
"""
from pathlib import Path
import argparse, datetime, json, os, re, shutil, subprocess, sys, tempfile, time
HERE = Path(__file__).resolve().parent
STD = 'scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db'
RAMS = ['RAMSP128X16_tt_1p10v_1p10v_25c.db', 'RAMSP1024X16_tt_1p10v_1p10v_25c.db', 'RAMSP4096X16_tt_1p10v_1p10v_25c.db']
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'


def now(): return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def libraries():
    d = Path.home() / 'Desktop'
    std = d / 'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v' / STD
    files = [std] + [d / 'qingyu_sram_corners' / n for n in RAMS]
    for p in files:
        if not p.is_file(): raise SystemExit('Missing official TT DB: ' + str(p))
    return [p.resolve() for p in files]


def launch(cmd, cwd, env, log):
    cwd.mkdir(parents=True, exist_ok=True)
    f = log.open('w')
    return subprocess.Popen([str(c) for c in cmd], cwd=str(cwd), env=env, stdout=f, stderr=subprocess.STDOUT)


def text(p):
    try: return Path(p).read_text(errors='replace')
    except OSError: return ''


def synth_ok(run):
    # DC echoes script text; require the standalone output line AND a real netlist.
    t = text(Path(run) / 'synth/dc.log'); n = Path(run) / 'synth/mapped.v'
    return bool(re.search(r'^Q12_FINAL_SYNTH_COMPLETE\s*$', t, re.M)) and not re.search(r'^Q12_FINAL_SYNTH_FAILED:', t, re.M) and n.is_file() and n.stat().st_size > 1000000


def summary(run, quiet=False):
    run = Path(run); cj = {}
    if (run / 'candidate.json').is_file(): cj = json.loads((run / 'candidate.json').read_text())
    lines = ['== Q12 CLEAN %s (%s, %s) %s' % (cj.get('label', '?'), cj.get('variant', '?'), cj.get('fmt', '?'), now()), 'run=' + str(run),
             'local: mean_cycles=%s layers/s=%s' % (cj.get('local_mean_cycles'), cj.get('local_layers_per_s'))]
    v = run / 'vendor/result.json'
    if v.is_file():
        r = json.loads(v.read_text())
        lines.append('vendor: passed=%s phase=%s tasks=%d mean_cycles=%s layers/s=%s %s' % (
            r.get('passed'), r.get('phase'), len(r.get('tasks', [])), r.get('mean_full_window_cycles'), r.get('layers_per_s'), r.get('error', '')))
        if r.get('tasks'): lines.append('vendor cycle deltas vs local: ' + ','.join(str(t.get('cycles_delta_from_local')) for t in r['tasks']))
    s = run / 'synth'
    area = dict(re.findall(r'^([A-Z0-9_]+)=(' + NUMBER + r')$', text(s / 'explicit_area_summary.txt'), re.M))
    if area:
        inc = float(area.get('INCREMENTAL_LIBRARY_AREA', 'nan')); macro = 0.0
        for ln in text(s / 'q12_explicit_area_leaves.tsv').splitlines()[1:]:
            c = ln.split('\t')
            if len(c) == 4 and c[1].startswith('RAMSP') and c[3] == 'fio': macro += float(c[2])
        lines.append('AREA incremental=%.1f um2 = %.6f mm2  [fio=%s transport=%s shared_ctrl=%s private_macros=%.1f] full_soc=%s' % (
            inc, inc / 1e6, area.get('FIO_LIBRARY_AREA'), area.get('NEW_TRANSPORT_LIBRARY_AREA'), area.get('SHARED_NONMACRO_LIBRARY_AREA'), macro, area.get('FULL_SOC_LIBRARY_AREA')))
    tmax = re.findall(r'slack\s*\([^)]*\)\s*(' + NUMBER + ')', text(s / 'timing_max.rpt'))
    tmin = re.findall(r'slack\s*\([^)]*\)\s*(' + NUMBER + ')', text(s / 'timing_min.rpt'))
    if tmax or tmin:
        lines.append('TIMING (TT, reported paths): worst setup=%s ns  worst hold=%s ns' % (min(map(float, tmax)) if tmax else 'NA', min(map(float, tmin)) if tmin else 'NA'))
    st = text(s / 'dc.log')
    if st: lines.append('synth: ' + ('COMPLETE' if synth_ok(run) else ('FAILED ' + ' | '.join(re.findall(r'^(?:Error:.*|Q12_FINAL_SYNTH_FAILED:.*)$', st, re.M)[:3]) if re.search(r'^Q12_FINAL_SYNTH_FAILED:', st, re.M) else 'running')))
    cg = text(s / 'clock_gating.rpt')
    m1 = re.search(r'Number of Gated registers\s*\|\s*(\d+)', cg); m2 = re.search(r'Number of Ungated registers\s*\|\s*(\d+)', cg)
    if m1 and m2: lines.append('clock gating: gated=%s ungated=%s' % (m1.group(1), m2.group(1)))
    f = text(run / 'formal/formal.log')
    if f:
        lines.append('formal: ' + ('SUCCEEDED' if re.search(r'^\s*Verification SUCCEEDED', f, re.M) and re.search(r'^Q12_FINAL_FORMAL_COMPLETE\s*$', f, re.M) else ('FAILED' if re.search(r'^\s*Verification FAILED|^Q12_FINAL_FORMAL_FAILED:', f, re.M) else 'running/unknown'))
                     + ' ' + ' '.join(re.findall(r'(\d+ Passing compare points|\d+ Failing compare points)', f)[:2]))
    pw = []
    for d in sorted(run.glob('power_layer*')):
        rep = text(d / 'power.rpt'); meta = d / 'window.json'
        m = re.search(r'^\s*Total Power\s*=\s*(' + NUMBER + r')\s*([munp]?W)?', rep, re.M)
        if m and meta.is_file():
            scale = {'W': 1, 'mW': 1e-3, 'uW': 1e-6, 'nW': 1e-9, 'pW': 1e-12}.get(m.group(2) or 'W', 1)
            w = float(m.group(1)) * scale; dur = json.loads(meta.read_text())['duration_ps']
            pw.append((d.name, w, w * dur * 1e-6))
    for n, w, e in pw: lines.append('%s: power=%.3f mW energy=%.4f uJ' % (n, w * 1e3, e))
    if pw:
        lines.append('ENERGY mean=%.4f uJ over %d windows; mean power=%.3f mW' % (sum(x[2] for x in pw) / len(pw), len(pw), 1e3 * sum(x[1] for x in pw) / len(pw)))
        h = text(sorted(run.glob('power_layer*'))[0] / 'power_hierarchy.rpt').splitlines()
        lines.append('--- power hierarchy (first window) ---'); lines += [x for x in h if x.strip()][:45]
    out = '\n'.join(lines) + '\n'
    (run / 'SUMMARY.txt').write_text(out)
    if not quiet: print(out, flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--summary', type=Path); ap.add_argument('--cand', type=Path)
    ap.add_argument('--layers', default='0,4,8,11')
    ap.add_argument('--compile', default='ultra', choices=['ultra', 'medium']); ap.add_argument('--no-gate', action='store_true')
    ap.add_argument('--work-root', type=Path, default=Path(os.environ.get('Q12_WORK_ROOT', '/tmp'))); ap.add_argument('--skip-vendor', action='store_true')
    a = ap.parse_args()
    if a.summary: summary(a.summary); return
    cand = a.cand.resolve(); cj = json.loads((cand / 'candidate.json').read_text())
    dbs = libraries()
    run = Path(tempfile.mkdtemp(prefix='q12clean_%s_' % cj['label'], dir=str(a.work_root)))
    (run / 'candidate.json').write_text(json.dumps(cj) + '\n')
    print('Q12_CLEAN_RUN=' + str(run), flush=True)
    env = os.environ.copy()
    env.update(Q12_PACKAGE=str(cand), Q12_EXPECT_128=str(cj['n128']), Q12_LIBRARIES=' '.join('{' + str(p) + '}' for p in dbs),
               Q12_COMPILE=a.compile, Q12_GATE='0' if a.no_gate else '1')
    env.update(dict(zip(['Q12_STD_DB', 'Q12_RAM128_DB', 'Q12_RAM1024_DB', 'Q12_RAM4096_DB'], map(str, dbs))))
    (run / 'tmp').mkdir(); env['TMPDIR'] = str(run / 'tmp')
    procs = {}
    if not a.skip_vendor:
        procs['vendor'] = launch([sys.executable, '-u', cand / 'vendor/run_vendor.py', '--out', run / 'vendor', '--saif', '--saif-layers', a.layers], run, env, run / 'vendor.log')
    procs['synth'] = launch([shutil.which('dc_shell') or 'dc_shell', '-f', HERE / 'map.tcl'], run / 'synth', env, run / 'synth' / 'dc.log')
    formal = None
    while procs:
        time.sleep(30)
        for k in list(procs):
            rc = procs[k].poll()
            if rc is None: continue
            print('%s %s stage %s exit=%s' % (now(), cj['label'], k, rc), flush=True); del procs[k]; summary(run, True)
            if k == 'synth':
                (run / 'SYNTH_DONE').write_text(str(rc) + '\n')
                if synth_ok(run):
                    e2 = env.copy(); e2.update(Q12_NETLIST=str(run / 'synth/mapped.v'), Q12_SVF=str(run / 'synth/mapped.svf'))
                    formal = launch([shutil.which('fm_shell') or 'fm_shell', '-f', HERE / 'formal.tcl'], run / 'formal', e2, run / 'formal' / 'formal.log')
    vr = run / 'vendor/result.json'
    if synth_ok(run) and vr.is_file() and json.loads(vr.read_text()).get('passed'):
        r = json.loads(vr.read_text())
        wanted = None if a.layers == 'all' else [int(x) for x in a.layers.split(',')]
        for i, t in enumerate(r['tasks']):
            if wanted is not None and i not in wanted: continue
            d = run / ('power_layer%02d' % i); d.mkdir()
            act = t['activity']; saif = (run / 'vendor' / act['saif_relpath']).resolve()
            (d / 'window.json').write_text(json.dumps({'task': t['task'], 'duration_ps': act['duration_ps'], 'saif': str(saif)}) + '\n')
            e3 = env.copy(); e3.update(Q12_NETLIST=str(run / 'synth/mapped.v'), Q12_SDC=str(run / 'synth/mapped.sdc'), Q12_SAIF=str(saif))
            p = launch([shutil.which('pt_shell') or 'pt_shell', '-f', HERE / 'power.tcl'], d, e3, d / 'pt.log'); p.wait()
            print('%s %s power %s exit=%s' % (now(), cj['label'], d.name, p.returncode), flush=True); summary(run, True)
    else:
        print('POWER SKIPPED: vendor or synthesis incomplete', flush=True)
    if formal is not None:
        formal.wait(); print('%s %s formal exit=%s' % (now(), cj['label'], formal.returncode), flush=True)
    summary(run); (run / 'FLOW_DONE').write_text('1\n'); print('Q12_CLEAN_FLOW_DONE ' + str(run), flush=True)


if __name__ == '__main__':
    main()
