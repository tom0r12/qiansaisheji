"""Server VCS run with manufacturer SRAM models; optional exact-window VCD->SAIF.

python3 run_vendor.py --out DIR [--tasks 12] [--saif]
"""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, signal, subprocess, sys, time
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from convert_activity import convert


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def read(p): return json.loads(Path(p).read_text())
def words(p): return [int(x, 16) for x in re.sub(r'//[^\n]*', '', Path(p).read_text()).split()]


def metrics(text, tag):
    rows = re.findall(r'^' + re.escape(tag) + r' (.+)$', text, re.M)
    if len(rows) != 1: raise ValueError('Missing/duplicate ' + tag)
    return {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', rows[0])}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--tasks', type=int, default=12)
    ap.add_argument('--models', type=Path, default=Path('/storage1/admin_public_dir/SRAM_Lib_2025'))
    ap.add_argument('--model-identity', type=Path, default=Path.home() / 'Desktop/sram_models.json')
    ap.add_argument('--compile-timeout', type=int, default=3600)
    ap.add_argument('--task-timeout', type=int, default=5400)
    ap.add_argument('--saif', action='store_true')
    ap.add_argument('--saif-layers', default='0,4,8,11', help='task indices that dump activity, or all')
    ap.add_argument('--saif-timeout', type=int, default=3600)
    ap.add_argument('--simulator', default='vcs')
    a = ap.parse_args()
    m = read(HERE / 'manifest.json')
    for n, h in m['files_sha256'].items():
        if sha(HERE / n) != h: raise ValueError('Package file/hash mismatch: ' + n)
    models = [a.models / n / 'verilog' / (n + '.v') for n in m['required_macro_references']]
    model_check = 'not_compared'
    if a.model_identity.is_file():
        mid = read(a.model_identity)
        for p in models:
            if sha(p) != mid['files'][p.stem]: raise ValueError('Manufacturer model mismatch: ' + str(p))
        model_check = 'matched_' + str(a.model_identity)
    out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    report = {'passed': False, 'phase': 'compile', 'candidate': m['candidate'], 'manifest_sha256': sha(HERE / 'manifest.json'),
              'frozen_result_sha256': m['frozen_result_sha256'], 'model_check': model_check,
              'model_sha256': {str(p): sha(p) for p in models}, 'tasks': [], 'activity_requested': a.saif}
    def save(): (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    def run(cmd, log, timeout, cwd):
        start = time.time()
        with log.open('w') as f:
            proc = subprocess.Popen([str(x) for x in cmd], cwd=str(cwd), stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
            try: rc = proc.wait(timeout=timeout)
            except BaseException:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                proc.wait(); raise
        if rc: raise RuntimeError('tool return=%s; see %s' % (rc, log))
        return time.time() - start
    save()
    try:
        includes = ['+incdir+' + str(HERE / n) for n in m['include_directories']]
        (out / 'sources.f').write_text(''.join('"' + str(p) + '"\n' for p in [HERE / n for n in m['vendor_source_order']] + models))
        vcs = shutil.which(a.simulator)
        if not vcs: raise ValueError('vcs not on PATH')
        flags = ['-full64', '-sverilog', '-timescale=1ns/1ps', '+define+DISABLE_SV_ASSERTION=1', '+define+ARM_UD_MODEL',
                 '+define+Q12_USE_VENDOR_MACROS', '-debug_access+all', '-top', 'tb_q12soc']
        exe = out / 'simv'
        report['compile_seconds'] = run([vcs, *flags, *includes, '-f', out / 'sources.f', '-Mdir=' + str(out / 'csrc'), '-o', exe], out / 'compile.log', a.compile_timeout, out)
        if re.search(r'Error-\[|\bError:|\bFatal:', (out / 'compile.log').read_text(errors='replace')): raise ValueError('Compile log error')
        report['phase'] = 'simulation'; save()
        local = {t['task']: t['metrics'] for t in read(HERE / 'evidence/local_result.json')['tasks']}
        saif_set = None if a.saif_layers == 'all' else {int(x) for x in a.saif_layers.split(',')}
        for idx, row in enumerate(m['tasks'][:a.tasks]):
            dump = a.saif and (saif_set is None or idx in saif_set)
            case = out / row['directory']; case.mkdir(exist_ok=True)
            for name in ['input.hex', 'expected.hex', 'dense.hex']: shutil.copy2(str(HERE / 'tasks' / row['directory'] / name), str(case / name))
            shutil.copy2(str(HERE / 'firmware64.hex'), str(case / 'firmware64.hex'))
            cmd = [exe, '+FIRMWARE=firmware64.hex', '+INPUT=input.hex', '+EXPECTED=expected.hex', '+OUTPUT_DUMP=observed.hex',
                   '+INPUT_WORDS=' + str(row['input_words']), '+OUTPUT_WORDS=12690', '+LAYER=' + row['task'][5:7]]
            if dump: cmd += ['+ACTIVITY=full_runtime.vcd']
            seconds = run(cmd, case / 'simulation.log', a.task_timeout, case)
            text = (case / 'simulation.log').read_text(errors='replace')
            if len(re.findall(r'^PASS real E203 Q12 vendor task;', text, re.M)) != 1 or re.search(r'(?im)^\s*(?:Fatal:|Error:|Error-\[)|\$fatal', text):
                raise ValueError('Missing clean vendor PASS: ' + row['task'])
            v = metrics(text, 'Q12GPIO_METRICS'); counts = metrics(text, 'Q12_VENDOR_MACROS')
            rb = metrics(text, 'Q12_MACRO_READBACK_COMPLETE')
            if counts != m['expected_macros']: raise ValueError('Elaborated macro counts differ')
            if rb != {'words': 131072, 'output_words': 12689, 'source_words': row['input_words']}: raise ValueError('Incomplete physical memory readback')
            observed = words(case / 'observed.hex'); expected = words(case / 'expected.hex'); dense = words(case / 'dense.hex')
            if observed != expected: raise ValueError('Physical dense output mismatch ' + row['task'])
            if [h for w in observed[17:] for h in (w & 65535, w >> 16)] != dense: raise ValueError('INT16 matrix mismatch')
            prior = local[row['task']]
            task = {'task': row['task'], 'directory': row['directory'], 'passed': True, 'metrics': v, 'wall_seconds': seconds,
                    'cycles_delta_from_local': v['full_window_cycles'] - prior['full_window_cycles']}
            if dump:
                first = metrics(text, 'Q12_FULL_START'); last = metrics(text, 'Q12_FULL_END'); vcd = case / 'full_runtime.vcd'
                if not vcd.is_file() or last['cycle'] - first['cycle'] + 1 != v['full_window_cycles']: raise ValueError('Activity window')
                task['activity'] = {'vcd': str(vcd), 'bytes': vcd.stat().st_size, 'start_ps': first['time_ps'], 'end_ps': last['time_ps'],
                                    'duration_ps': last['time_ps'] - first['time_ps'], 'scope': 'tb_q12soc/dut', 'timescale_ps': 1}
                # Convert this window now and delete its VCD (bounded disk use).
                tool = shutil.which('vcd2saif')
                if not tool: raise ValueError('vcd2saif not on PATH')
                saif = case / 'full_runtime.saif'
                run([tool, '-64', '-input', vcd, '-output', saif, '-time', str(first['time_ps']), str(last['time_ps'])], case / 'vcd2saif.log', a.saif_timeout, case)
                head = saif.open(errors='replace').read(65536) if saif.is_file() else ''
                if not re.search(r'\(INSTANCE\s+tb_q12soc\b', head) or not re.search(r'\(INSTANCE\s+dut\b', head):
                    raise ValueError('SAIF hierarchy missing ' + row['task'])
                task['activity'].update(saif_relpath=saif.relative_to(out).as_posix(), saif_sha256=sha(saif))
                os.remove(str(vcd))
            report['tasks'].append(task); save()
            print('Q12_VENDOR_TASK %s cycles=%d delta=%d' % (row['task'], v['full_window_cycles'], task['cycles_delta_from_local']), flush=True)
        mean = sum(t['metrics']['full_window_cycles'] for t in report['tasks']) / len(report['tasks'])
        report.update(functional_passed=True, mean_full_window_cycles=mean, layers_per_s=150e6 / mean)
        save()
        report.update(passed=True, phase='complete'); save()
        print('Q12_VENDOR_COMPLETE mean_cycles=%.2f layers_per_s=%.2f' % (mean, 150e6 / mean), flush=True)
    except BaseException as exc:
        report.update(passed=False, failed_phase=report['phase'], phase='failed', error=repr(exc)); save()
        print('Q12_VENDOR_FAILED ' + repr(exc), flush=True); raise


if __name__ == '__main__':
    main()
