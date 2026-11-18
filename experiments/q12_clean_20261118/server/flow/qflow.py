"""Clean Q12 v9 unified server flow for ONE candidate directory:
- Manufacturer-SRAM VCS 12 tasks (+SAIF)
- Whole-SoC DC mapping (TT setup + 5-corner bc_wc hold) -> Formality + 5-corner PT STA + PT power windows + TT SDF GLS (A)
- Standalone u_fio (qingyu_q12_stream_fio) DC 5-corner bc_wc mapping -> Formality + 5-corner PT STA
All from the exact same frozen staged RTL in hardware/sources.tcl (no cross-version splicing).
"""
from pathlib import Path
import argparse, datetime, json, os, re, shutil, subprocess, sys, tempfile, time

HERE = Path(__file__).resolve().parent
CORNER_SPEC = [
    ('tt_25c',  'scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db',   'tt_1p10v_1p10v_25c'),
    ('ss_125c', 'scc40nll_vhsc40_rvt_ss_v0p99_125c_basic.db', 'ss_0p99v_0p99v_125c'),
    ('ss_m40c', 'scc40nll_vhsc40_rvt_ss_v0p99_-40c_basic.db', 'ss_0p99v_0p99v_m40c'),
    ('ff_125c', 'scc40nll_vhsc40_rvt_ff_v1p21_125c_basic.db', 'ff_1p21v_1p21v_125c'),
    ('ff_m40c', 'scc40nll_vhsc40_rvt_ff_v1p21_-40c_basic.db', 'ff_1p21v_1p21v_m40c'),
]
MACROS = ['RAMSP128X16', 'RAMSP1024X16', 'RAMSP4096X16']
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'


def now(): return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def corner_libraries():
    d = Path.home() / 'Desktop'
    std_dir = d / 'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v'
    sram_dir = d / 'qingyu_sram_corners'
    out = {}
    for cname, std_name, sram_suf in CORNER_SPEC:
        files = [std_dir / std_name] + [sram_dir / ('%s_%s.db' % (m, sram_suf)) for m in MACROS]
        for p in files:
            if not p.is_file():
                raise SystemExit('Missing official corner DB (%s): %s' % (cname, p))
        out[cname] = [p.resolve() for p in files]
    return out


def launch(cmd, cwd, env, log):
    cwd.mkdir(parents=True, exist_ok=True)
    f = log.open('w')
    return subprocess.Popen([str(c) for c in cmd], cwd=str(cwd), env=env, stdout=f, stderr=subprocess.STDOUT)


def text(p):
    try: return Path(p).read_text(errors='replace')
    except OSError: return ''


def synth_ok(run):
    t = text(Path(run) / 'synth/dc.log'); n = Path(run) / 'synth/mapped.v'
    return bool(re.search(r'^Q12_FINAL_SYNTH_COMPLETE\s*$', t, re.M)) and not re.search(r'^Q12_FINAL_SYNTH_FAILED:', t, re.M) and n.is_file() and n.stat().st_size > 1000000


def fio_synth_ok(run):
    t = text(Path(run) / 'fio_synth/dc.log'); n = Path(run) / 'fio_synth/fio_mapped.v'
    return bool(re.search(r'^Q12_FIO_SYNTH_COMPLETE\s*$', t, re.M)) and not re.search(r'^Q12_FIO_SYNTH_FAILED:', t, re.M) and n.is_file() and n.stat().st_size > 100000


def formal_status(log_path):
    f = text(log_path)
    if not f: return 'not_started'
    ok = bool(re.search(r'^\s*Verification SUCCEEDED', f, re.M)) and bool(re.search(r'^Q12_FINAL_FORMAL_COMPLETE\s*$', f, re.M))
    fail = bool(re.search(r'^\s*Verification FAILED|^Q12_FINAL_FORMAL_FAILED:', f, re.M))
    pts = ' '.join(re.findall(r'(\d+ Passing compare points|\d+ Failing compare points)', f)[:2])
    return ('SUCCEEDED ' if ok else ('FAILED ' if fail else 'running/unknown ')) + pts


def parse_pt_corners(root):
    rows = []
    for cname, _, _ in CORNER_SPEC:
        st = text(Path(root) / cname / 'summary.txt')
        for m in re.finditer(r'^Q12_PT_CORNER top=(\S+) corner=(\S+) group=(\S+) setup=(\S+) hold=(\S+)', st, re.M):
            rows.append(m.groups())
    return rows


def summary(run, quiet=False):
    run = Path(run); cj = {}
    if (run / 'candidate.json').is_file(): cj = json.loads((run / 'candidate.json').read_text())
    lines = ['== Q12 CLEAN %s (%s, %s) %s' % (cj.get('label', '?'), cj.get('variant', '?'), cj.get('fmt', '?'), now()),
             'run=' + str(run),
             'local: mean_cycles=%s layers/s=%s' % (cj.get('local_mean_cycles'), cj.get('local_layers_per_s'))]
    v = run / 'vendor/result.json'
    if v.is_file():
        r = json.loads(v.read_text())
        lines.append('vendor: passed=%s phase=%s tasks=%d mean_cycles=%s layers/s=%s %s' % (
            r.get('passed'), r.get('phase'), len(r.get('tasks', [])), r.get('mean_full_window_cycles'), r.get('layers_per_s'), r.get('error', '')))
        if r.get('tasks'):
            lines.append('vendor cycle deltas vs local: ' + ','.join(str(t.get('cycles_delta_from_local')) for t in r['tasks']))
    s = run / 'synth'
    area = dict(re.findall(r'^([A-Z0-9_]+)=(' + NUMBER + r')$', text(s / 'explicit_area_summary.txt'), re.M))
    if area:
        inc = float(area.get('INCREMENTAL_LIBRARY_AREA', 'nan')); macro = 0.0
        for ln in text(s / 'q12_explicit_area_leaves.tsv').splitlines()[1:]:
            c = ln.split('\t')
            if len(c) == 4 and c[1].startswith('RAMSP') and c[3] == 'fio': macro += float(c[2])
        lines.append('AREA (whole-SoC TT+bcwc-hold) incremental=%.1f um2 = %.6f mm2  [fio=%s transport=%s shared_ctrl=%s private_macros=%.1f] full_soc=%s' % (
            inc, inc / 1e6, area.get('FIO_LIBRARY_AREA'), area.get('NEW_TRANSPORT_LIBRARY_AREA'), area.get('SHARED_NONMACRO_LIBRARY_AREA'), macro, area.get('FULL_SOC_LIBRARY_AREA')))
    cr = text(s / 'constraints.rpt')
    if cr:
        def sec(name):
            hdr = r'^\s*(max_delay/setup|min_delay/hold|max_transition|max_capacitance|max_fanout|critical_range|max_area|sequential_clock_pulse_width|min_capacitance|min_pulse_width)\b'
            parts = re.split(hdr, cr, flags=re.M)
            return sum(len(re.findall(r'\(VIOLATED', parts[i + 1])) for i in range(1, len(parts) - 1, 2) if parts[i] == name)
        lines.append('whole-SoC DC constraint violators: setup=%d hold=%d max_transition=%d max_capacitance=%d' % (
            sec('max_delay/setup'), sec('min_delay/hold'), sec('max_transition'), sec('max_capacitance')))
    st = text(s / 'dc.log')
    lines += ['  dc: ' + x for x in re.findall(r'^(Q12_(?:INSPECT_CLK_PINS|POST_COMPILE_WNS|INCREMENTAL_DONE|BCWC_HOLD_ARMED|HOLDFIX_\w+|POST_HOLD_RESYNC)\b.*)$', st, re.M)]
    if st:
        lines.append('synth (whole-SoC): ' + ('COMPLETE' if synth_ok(run) else ('FAILED ' + ' | '.join(re.findall(r'^(?:Error:.*|Q12_FINAL_SYNTH_FAILED:.*)$', st, re.M)[:3]) if re.search(r'^Q12_FINAL_SYNTH_FAILED:', st, re.M) else 'running')))
    cg = text(s / 'clock_gating.rpt')
    m1 = re.search(r'Number of Gated registers\s*\|\s*(\d+)', cg); m2 = re.search(r'Number of Ungated registers\s*\|\s*(\d+)', cg)
    if m1 and m2: lines.append('clock gating (whole-SoC): gated=%s ungated=%s' % (m1.group(1), m2.group(1)))
    if (run / 'formal/formal.log').is_file():
        lines.append('formal (whole-SoC): ' + formal_status(run / 'formal/formal.log'))

    # Standalone u_fio 5-corner summary
    fs = run / 'fio_synth'
    fst = text(fs / 'dc.log')
    if fst:
        fa = re.search(r'Total cell area:\s*(' + NUMBER + ')', text(fs / 'fio_area.rpt'))
        farea_str = ('%.1f um2 (%.6f mm2)' % (float(fa.group(1)), float(fa.group(1)) / 1e6)) if fa else 'NA'
        lines.append('fio_synth (standalone u_fio bc_wc ss_m40c/ff_m40c): %s area=%s' % (
            'COMPLETE' if fio_synth_ok(run) else ('FAILED' if re.search(r'^Q12_FIO_SYNTH_FAILED:', fst, re.M) else 'running'), farea_str))
        lines += ['  fio_dc: ' + x for x in re.findall(r'^(Q12_FIO_(?:POST_COMPILE|INC_DONE|HOLDFIX_\w+)\b.*)$', fst, re.M)]
    if (run / 'fio_formal/formal.log').is_file():
        lines.append('fio_formal (standalone u_fio): ' + formal_status(run / 'fio_formal/formal.log'))

    fio_5c = parse_pt_corners(run / 'pt_fio_5c')
    if fio_5c:
        lines.append('--- PrimeTime 5-Corner STA: Standalone u_fio (qingyu_q12_stream_fio) ---')
        all_met = True
        for top_m, cname, gname, smax, smin in fio_5c:
            lines.append('  u_fio corner=%-8s group=%-10s setup=%s ns  hold=%s ns' % (cname, gname, smax, smin))
            if (smax != 'NA' and float(smax) < 0) or (smin != 'NA' and float(smin) < 0):
                all_met = False
        lines.append('  u_fio 5-corner verdict: ' + ('ALL 5 CORNERS SETUP & HOLD MET (>= 0)' if all_met and len(fio_5c) >= 5 else 'VIOLATION OR INCOMPLETE'))

    soc_5c = parse_pt_corners(run / 'pt_soc_5c')
    if soc_5c:
        lines.append('--- PrimeTime 5-Corner STA: Whole-SoC (qingyu_e203_soc_top) ---')
        hold_all_met = True; tt_setup_met = True
        for top_m, cname, gname, smax, smin in soc_5c:
            lines.append('  soc   corner=%-8s group=%-15s setup=%s ns  hold=%s ns' % (cname, gname, smax, smin))
            if smin != 'NA' and float(smin) < 0: hold_all_met = False
            if cname == 'tt_25c' and smax != 'NA' and float(smax) < 0: tt_setup_met = False
        lines.append('  soc 5-corner verdict: TT_setup=%s  ALL_5_CORNER_HOLD=%s' % (
            'MET' if tt_setup_met else 'VIOLATED', 'MET' if hold_all_met else 'VIOLATED'))

    # Gate-level simulation summary
    gr = run / 'gls/result.json'
    if gr.is_file():
        gj = json.loads(gr.read_text())
        lines.append('GLS (TT SDF whole-SoC mapped.v): passed=%s phase=%s task=%s cycles=%s mismatches=%s sdf_bytes=%s %s' % (
            gj.get('passed'), gj.get('phase'), gj.get('task'), gj.get('full_window_cycles'), gj.get('mismatches'), gj.get('sdf_bytes'), gj.get('error', '')))

    # Power windows
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
        es = [x[2] for x in pw]
        lines.append('ENERGY mean=%.4f uJ (min=%.4f max=%.4f) over %d windows; mean power=%.3f mW' % (
            sum(es) / len(es), min(es), max(es), len(pw), 1e3 * sum(x[1] for x in pw) / len(pw)))
        d0 = sorted(run.glob('power_layer*'))[0]; h = (text(d0 / 'power_hier3.rpt') or text(d0 / 'power_hierarchy.rpt')).splitlines()
        kept, skip = [], False
        for x in h:
            if skip and re.match(r'^\s+[\d.e+-]+\s', x): skip = False; continue
            skip = False
            if 'SNPS_CLOCK_GATE' in x or 'clk_gate_' in x:
                skip = not re.search(r'\d\.\d+e?-?\d*\s+[\d.]+\s*$', x); continue
            kept.append(x)
        lines.append('--- power hierarchy (first window) ---'); lines += [x for x in kept if x.strip()][:55]
    out = '\n'.join(lines) + '\n'
    (run / 'SUMMARY.txt').write_text(out)
    if not quiet: print(out, flush=True)
    return out


def run_pt_5corners(pt_bin, run_subroot, top_mod, netlist, sdc, corners, base_env):
    procs = []
    for cname, _, _ in CORNER_SPEC:
        cdir = run_subroot / cname
        e = base_env.copy()
        e.update(Q12_TOP_MODULE=top_mod, Q12_CORNER_NAME=cname,
                 Q12_NETLIST=str(netlist), Q12_SDC=str(sdc),
                 Q12_LIBRARIES=' '.join(str(p) for p in corners[cname]))
        procs.append((cname, launch([pt_bin, '-f', HERE / 'pt_5corner.tcl'], cdir, e, cdir / 'pt.log')))
    for cname, p in procs:
        p.wait()
        print('%s PT 5-corner %s/%s exit=%s' % (now(), top_mod, cname, p.returncode), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--summary', type=Path); ap.add_argument('--cand', type=Path)
    ap.add_argument('--layers', default='auto', help='auto (all for A, 0,4,8,11 for B), all, or comma list')
    ap.add_argument('--compile', default='ultra', choices=['ultra', 'medium']); ap.add_argument('--no-gate', action='store_true')
    ap.add_argument('--work-root', type=Path, default=Path(os.environ.get('Q12_WORK_ROOT', '/tmp')))
    ap.add_argument('--skip-vendor', action='store_true'); ap.add_argument('--skip-gls', action='store_true')
    a = ap.parse_args()
    if a.summary: summary(a.summary); return
    cand = a.cand.resolve(); cj = json.loads((cand / 'candidate.json').read_text())
    layers = ('all' if cj['label'] == 'A' else '0,4,8,11') if a.layers == 'auto' else a.layers
    do_gls = (not a.skip_gls) and (cj['label'] == 'A')
    corners = corner_libraries()
    tt_dbs = corners['tt_25c']; ss_dbs = corners['ss_m40c']; ff_dbs = corners['ff_m40c']; ff125_dbs = corners['ff_125c']
    run = Path(tempfile.mkdtemp(prefix='q12clean_%s_' % cj['label'], dir=str(a.work_root)))
    (run / 'candidate.json').write_text(json.dumps(cj) + '\n')
    print('Q12_CLEAN_RUN=' + str(run), flush=True)
    env = os.environ.copy()
    env.update(Q12_PACKAGE=str(cand), Q12_EXPECT_128=str(cj['n128']),
               Q12_LIBRARIES=' '.join(str(p) for p in tt_dbs),
               Q12_COMPILE=a.compile, Q12_GATE='0' if a.no_gate else '1')
    env.update(dict(zip(['Q12_STD_DB', 'Q12_RAM128_DB', 'Q12_RAM1024_DB', 'Q12_RAM4096_DB'], map(str, tt_dbs))))
    env.update(dict(zip(['Q12_SS_STD_DB', 'Q12_SS_RAM128_DB', 'Q12_SS_RAM1024_DB', 'Q12_SS_RAM4096_DB'], map(str, ss_dbs))))
    env.update(dict(zip(['Q12_FF_STD_DB', 'Q12_FF_RAM128_DB', 'Q12_FF_RAM1024_DB', 'Q12_FF_RAM4096_DB'], map(str, ff_dbs))))
    env.update(dict(zip(['Q12_FF125_STD_DB', 'Q12_FF125_RAM128_DB', 'Q12_FF125_RAM1024_DB', 'Q12_FF125_RAM4096_DB'], map(str, ff125_dbs))))
    (run / 'tmp').mkdir(); env['TMPDIR'] = str(run / 'tmp')

    dc_bin = shutil.which('dc_shell') or 'dc_shell'
    fm_bin = shutil.which('fm_shell') or 'fm_shell'
    pt_bin = shutil.which('pt_shell') or 'pt_shell'

    procs = {}
    if not a.skip_vendor:
        procs['vendor'] = launch([sys.executable, '-u', cand / 'vendor/run_vendor.py', '--out', run / 'vendor', '--saif', '--saif-layers', layers], run, env, run / 'vendor.log')
    procs['synth'] = launch([dc_bin, '-f', HERE / 'map.tcl'], run / 'synth', env, run / 'synth' / 'dc.log')

    formal = None; fio_formal = None; gls_proc = None
    while procs:
        time.sleep(20)
        for k in list(procs):
            rc = procs[k].poll()
            if rc is None: continue
            print('%s %s stage %s exit=%s' % (now(), cj['label'], k, rc), flush=True); del procs[k]; summary(run, True)
            if k == 'synth':
                if synth_ok(run):
                    e_fm = env.copy()
                    e_fm.update(Q12_TOP_MODULE='qingyu_e203_soc_top',
                                Q12_NETLIST=str(run / 'synth/mapped.v'), Q12_SVF=str(run / 'synth/mapped.svf'))
                    formal = launch([fm_bin, '-f', HERE / 'formal.tcl'], run / 'formal', e_fm, run / 'formal/formal.log')
                    if do_gls:
                        gls_proc = launch([sys.executable, '-u', HERE / 'run_gls.py', '--run', run, '--cand', cand], run, env, run / 'gls.log')
                # Launch standalone u_fio 5-corner synthesis sequentially on the single DC slot
                procs['fio_synth'] = launch([dc_bin, '-f', HERE / 'fio_map.tcl'], run / 'fio_synth', env, run / 'fio_synth/dc.log')
            elif k == 'fio_synth':
                # Release DC slot for next candidate in run_all.py!
                (run / 'SYNTH_DONE').write_text(str(rc) + '\n')
                if fio_synth_ok(run):
                    e_ffm = env.copy()
                    e_ffm.update(Q12_TOP_MODULE='qingyu_q12_stream_fio',
                                 Q12_LIBRARIES=' '.join(str(p) for p in ss_dbs),
                                 Q12_NETLIST=str(run / 'fio_synth/fio_mapped.v'), Q12_SVF=str(run / 'fio_synth/fio_mapped.svf'))
                    fio_formal = launch([fm_bin, '-f', HERE / 'formal.tcl'], run / 'fio_formal', e_ffm, run / 'fio_formal/formal.log')

    # Run PrimeTime 5-corner STA on standalone u_fio and whole-SoC
    if fio_synth_ok(run):
        run_pt_5corners(pt_bin, run / 'pt_fio_5c', 'qingyu_q12_stream_fio', run / 'fio_synth/fio_mapped.v', run / 'fio_synth/fio_mapped.sdc', corners, env)
        summary(run, True)
    if synth_ok(run):
        run_pt_5corners(pt_bin, run / 'pt_soc_5c', 'qingyu_e203_soc_top', run / 'synth/mapped.v', run / 'synth/mapped.sdc', corners, env)
        summary(run, True)

    # Run PrimeTime PX power windows (batches of up to 4 concurrent PT processes)
    vr = run / 'vendor/result.json'
    if synth_ok(run) and vr.is_file() and json.loads(vr.read_text()).get('passed'):
        r = json.loads(vr.read_text())
        wanted = None if layers == 'all' else [int(x) for x in layers.split(',')]
        tasks_to_run = [(i, t) for i, t in enumerate(r['tasks']) if wanted is None or i in wanted]
        for b in range(0, len(tasks_to_run), 4):
            batch = []
            for i, t in tasks_to_run[b:b + 4]:
                d = run / ('power_layer%02d' % i); d.mkdir()
                act = t['activity']; saif = (run / 'vendor' / act['saif_relpath']).resolve()
                (d / 'window.json').write_text(json.dumps({'task': t['task'], 'duration_ps': act['duration_ps'], 'saif': str(saif)}) + '\n')
                e3 = env.copy(); e3.update(Q12_NETLIST=str(run / 'synth/mapped.v'), Q12_SDC=str(run / 'synth/mapped.sdc'), Q12_SAIF=str(saif))
                batch.append((d.name, launch([pt_bin, '-f', HERE / 'power.tcl'], d, e3, d / 'pt.log')))
            for dname, p in batch:
                p.wait()
                print('%s %s power %s exit=%s' % (now(), cj['label'], dname, p.returncode), flush=True)
            summary(run, True)
    else:
        print('POWER SKIPPED: vendor or synthesis incomplete', flush=True)

    for tag, proc in [('formal', formal), ('fio_formal', fio_formal), ('gls', gls_proc)]:
        if proc is not None:
            proc.wait()
            print('%s %s %s exit=%s' % (now(), cj['label'], tag, proc.returncode), flush=True)
    summary(run)
    (run / 'FLOW_DONE').write_text('1\n')
    print('Q12_CLEAN_FLOW_DONE ' + str(run), flush=True)


if __name__ == '__main__':
    main()
