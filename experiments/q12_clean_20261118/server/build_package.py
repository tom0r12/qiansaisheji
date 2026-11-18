"""Build a multi-candidate server package from passing local runs.

python server/build_package.py LABEL=RUN_DIR[:N128] [LABEL=RUN_DIR[:N128] ...]
"""
from pathlib import Path
from datetime import datetime, timezone
import ast, hashlib, json, re, shutil, sys, zipfile
S = Path(__file__).resolve().parent
sys.path.insert(0, str(S))
from make_vendor_tb import make_testbench
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def put(p, s): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding='utf-8', newline='\n')
def copy(a, b): b.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(str(a), str(b))
def logical(n): m = re.match(r'^\d{3}_(.+)$', n); return m.group(1) if m else n


def candidate(run, label, n128, D):
    run = Path(run).resolve(); R = json.loads((run / 'result.json').read_text())
    assert R['passed'] and len(R['tasks']) == 12, 'need a passing 12-task run: ' + str(run)
    V = D / 'vendor'; H = D / 'hardware'
    src = [Path(l.strip()) for l in (run / 'sources.f').read_text().splitlines() if l.strip() and not l.startswith('+incdir')]
    vorder, horder = [], []
    for i, p in enumerate(src):
        name = logical(p.name); rel = 'src/%03d_%s' % (i, name); sim_only = False
        if name == 'sirv_gnrl_ram.v': copy(S / 'asic/sirv_gnrl_ram.v', V / rel)
        elif name == 'qingyu_shared_sram.sv':
            t = p.read_text().replace('\r\n', '\n')
            ctrl = t[:t.index('module qingyu_shared_sram (')]
            ctrl = ctrl[:ctrl.rindex('`timescale')]
            put(V / rel, ctrl + (S / 'asic/qingyu_shared_sram_asic.sv').read_text().replace('\r\n', '\n'))
        elif name == 'tb_q12soc.sv':
            tb, bind = make_testbench(p.read_text(), n128); put(V / rel, tb); sim_only = True
        elif name == 'q12_gpio_source.sv': copy(p, V / rel); sim_only = True
        else: copy(p, V / rel)
        vorder.append(rel)
        if not sim_only: copy(V / rel, H / rel); horder.append(rel)
    rel = 'src/900_qingyu_banked_sram.sv'
    copy(S / 'asic/qingyu_banked_sram.sv', V / rel); copy(V / rel, H / rel); vorder.append(rel); horder.append(rel)
    put(V / 'src/901_macro_presence.sv', bind); vorder.append('src/901_macro_presence.sv')
    for inc in (run / 'includes').glob('*'):
        copy(inc, V / 'includes' / inc.name); copy(inc, H / 'includes' / inc.name)
    copy(run / 'firmware64.hex', V / 'firmware64.hex')
    copy(run / 'result.json', V / 'evidence/local_result.json'); copy(run / 'result.json', H / 'evidence/local_result.json')
    for row in R['packets']:
        for n in ['input.hex', 'expected.hex', 'dense.hex']: copy(run / row['directory'] / n, V / 'tasks' / row['directory'] / n)
    for n in ['run_vendor.py', 'convert_activity.py']: copy(S / 'flow' / n, V / n)
    vm = {'candidate': label + '_' + R['variant'], 'required_macro_references': ['RAMSP128X16', 'RAMSP1024X16', 'RAMSP4096X16'],
          'expected_macros': {'RAMSP128X16': n128, 'RAMSP1024X16': 6, 'RAMSP4096X16': 80, 'total': n128 + 86},
          'vendor_source_order': vorder, 'include_directories': ['includes'], 'frozen_result_sha256': sha(run / 'result.json'),
          'tasks': [{'task': r['task'], 'directory': r['directory'], 'input_words': r['input_words']} for r in R['packets']]}
    vm['files_sha256'] = {q.relative_to(V).as_posix(): sha(q) for q in sorted(V.rglob('*')) if q.is_file()}
    put(V / 'manifest.json', json.dumps(vm, indent=1) + '\n')
    tcl = 'set Q12_SOURCE_ROOT [file dirname [file normalize [info script]]]\nset Q12_SOURCES {}\n'
    tcl += ''.join('lappend Q12_SOURCES [file join $Q12_SOURCE_ROOT {' + n + '}]\n' for n in horder)
    tcl += 'set Q12_INCLUDES [list [file join $Q12_SOURCE_ROOT includes]]\nset Q12_DEFINES {SYNTHESIS=1 DISABLE_SV_ASSERTION=1 Q12_USE_VENDOR_MACROS=1}\n'
    put(H / 'sources.tcl', tcl)
    copy(S / 'flow/report_explicit_area.tcl', H / 'report_explicit_area.tcl')
    copy(S / 'flow/audit.tcl', D / 'audit.tcl')
    put(D / 'candidate.json', json.dumps({'label': label, 'variant': R['variant'], 'fmt': R['fmt'], 'n128': n128,
                                         'local_mean_cycles': R['mean_cycles'], 'local_layers_per_s': R['layers_per_s'],
                                         'local_run': str(run)}, indent=1) + '\n')
    # Gate: VCS/DC require declare-before-use (Verilator/Icarus accept forward refs).
    sys.path.insert(0, str(S.parent)); import check_decl_order
    issues = [(f.name,) + i for f in sorted((V / 'src').glob('*')) for i in check_decl_order.check(f)]
    if issues: raise SystemExit('declare-before-use violations: %s' % issues[:10])


def build(specs):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    B = S / 'packages' / stamp / 'q12clean'
    B.mkdir(parents=True)
    labels = []
    for spec in specs:
        label, rest = spec.split('=', 1)
        run, _, n = rest.rpartition(':') if re.search(r':\d+$', rest) else (rest, '', '30')
        candidate(run, label, int(n), B / label); labels.append(label)
    for n in ['map.tcl', 'fio_map.tcl', 'power.tcl', 'formal.tcl', 'pt_5corner.tcl', 'run_gls.py', 'qflow.py', 'run_all.py']:
        copy(S / 'flow' / n, B / n)
    put(B / 'candidates.json', json.dumps(labels) + '\n')
    put(B / 'README.txt', README)
    ident = {'candidates': labels, 'files': {q.relative_to(B).as_posix(): sha(q) for q in sorted(B.rglob('*')) if q.is_file()}}
    put(B / 'package_identity.json', json.dumps(ident, indent=1) + '\n')
    for q in B.rglob('*.py'): ast.parse(q.read_text(), feature_version=(3, 6))
    import tkinter
    interp = tkinter.Tcl()
    for q in B.rglob('*.tcl'):
        interp.setvar('_q12_tcl', q.read_text())
        if int(interp.eval('info complete $_q12_tcl')) != 1:
            raise SystemExit('Incomplete Tcl syntax in ' + str(q))
    z = B.parent / 'q12clean.zip'
    with zipfile.ZipFile(str(z), 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as f:
        for q in sorted(B.rglob('*')):
            if q.is_file(): f.write(str(q), 'q12clean/' + q.relative_to(B).as_posix())
    rec = {'bundle': str(B), 'zip': str(z), 'zip_sha256': sha(z), 'bytes': z.stat().st_size, 'candidates': specs}
    put(S / 'latest_package.json', json.dumps(rec, indent=1) + '\n'); print(json.dumps(rec, indent=1)); return rec


README = """q12clean server package (no input entropy coding, no shared readcache, no loader)
Candidates: see candidates.json (each has candidate.json with local throughput).
  cd ~/Desktop && rm -rf q12clean && unzip -q q12clean.zip && cd q12clean
  nohup python3 -u run_all.py > ~/Desktop/q12clean_flow.log 2>&1 < /dev/null &
Progress: tail -5 ~/Desktop/q12clean_flow.log     Results: cat ~/Desktop/q12clean_SUMMARY.txt
Per candidate: vendor VCS 12 tasks + SAIF || DC (compile_ultra + clock gating) -> Formality + PT power windows.
"""

if __name__ == '__main__':
    build(sys.argv[1:])
