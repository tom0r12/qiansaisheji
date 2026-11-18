"""Clean-variant local regression runner (real E203 RTL + accelerator, Verilator).

python run.py --variant v1 [--fmt fixed12] [--tasks 12] [--sim-jobs 4]

A variant directory holds override files. Any file in <variant>/src replaces the
base source with the same logical name (base files are '<NNN>_<name>'); files
named in <variant>/remove.txt are dropped; <variant>/add.txt lists extra files
(appended in order). <variant>/firmware/* overrides firmware sources.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[2]
BASE = HERE / 'base'
MINGW = WORK / 'qingyu/tools/verilator/mingw64'
GCC = Path(r'C:\Efinity\efinity-riscv-ide-2025.1\toolchain\bin\riscv-none-embed-gcc.exe')
sys.path.insert(0, str(HERE))
import packets


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(cmd, log, env, cwd=None, timeout=3600):
    with open(log, 'w', encoding='utf-8', errors='replace') as f:
        r = subprocess.run([str(c) for c in cmd], stdout=f, stderr=subprocess.STDOUT, env=env, cwd=cwd, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f'command failed rc={r.returncode}: {cmd[0]} (see {log})')


def logical(name):
    m = re.match(r'^\d{3}_(.+)$', name)
    return m.group(1) if m else name


def stage_sources(variant, out):
    base_list = [Path(l.strip()) for l in (BASE / 'sources.f').read_text().splitlines() if l.strip() and not l.startswith('+incdir')]
    overrides = {p.name: p for p in (variant / 'src').glob('*')} if (variant / 'src').is_dir() else {}
    removed = set()
    if (variant / 'remove.txt').is_file():
        removed = {l.strip() for l in (variant / 'remove.txt').read_text().splitlines() if l.strip()}
    adds = []
    if (variant / 'add.txt').is_file():
        adds = [l.strip() for l in (variant / 'add.txt').read_text().splitlines() if l.strip()]
    stage = out / 'sources'; stage.mkdir()
    order, records, used = [], [], set()
    for p in base_list:
        src = BASE / 'sources' / p.name
        name = logical(p.name)
        if name in removed:
            continue
        if name in overrides:
            src = overrides[name]; used.add(name)
        dest = stage / p.name
        shutil.copy2(src, dest); order.append(dest)
        records.append({'name': name, 'path': str(src), 'sha256': sha(src)})
    for name in adds:
        src = overrides.get(name) or (variant / 'src' / name)
        used.add(name)
        dest = stage / ('900_' + name); shutil.copy2(src, dest); order.append(dest)
        records.append({'name': name, 'path': str(src), 'sha256': sha(src), 'added': True})
    unused = set(overrides) - used
    if unused:
        raise ValueError('override files not matched: %s' % sorted(unused))
    inc = out / 'includes'; shutil.copytree(BASE / 'includes', inc)
    if (variant / 'includes').is_dir():
        for p in (variant / 'includes').glob('*'): shutil.copy2(p, inc / p.name)
    (out / 'sources.f').write_text('+incdir+' + inc.as_posix() + '\n' + '\n'.join(p.as_posix() for p in order) + '\n', encoding='ascii')
    return records


def build_firmware(variant, out, env, defines):
    sw = out / 'firmware_src'; shutil.copytree(BASE / 'firmware_src', sw)
    if (variant / 'firmware').is_dir():
        for p in (variant / 'firmware').glob('*'): shutil.copy2(p, sw / p.name)
    cmd = [GCC, '-march=rv32imac', '-mabi=ilp32', '-ffreestanding', '-fno-builtin', '-msmall-data-limit=0',
           *['-D' + d for d in defines], '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror',
           '-nostdlib', '-nostartfiles', '-O3', '-flto', '-I' + str(sw), '-T' + str(sw / 'linker.ld'), '-Wl,--gc-sections',
           sw / 'startup.S', sw / 'soc_main.c', sw / 'runtime.c', '-lgcc', '-o', out / 'firmware.elf']
    run(cmd, out / 'firmware_compile.log', env, timeout=120)
    run([GCC.with_name('riscv-none-embed-objcopy.exe'), '-O', 'binary', out / 'firmware.elf', out / 'firmware.bin'], out / 'objcopy.log', env)
    data = (out / 'firmware.bin').read_bytes()
    if not 0 < len(data) <= 65536: raise ValueError('firmware size')
    data += b'\0' * (65536 - len(data))
    (out / 'firmware64.hex').write_text(''.join(f'{int.from_bytes(data[i:i + 8], "little"):016x}\n' for i in range(0, len(data), 8)), encoding='ascii')
    return {'size': len((out / 'firmware.bin').read_bytes()), 'defines': defines}


def words(p):
    return [int(x, 16) for x in re.sub(r'//[^\n]*', '', p.read_text()).split()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variant', required=True)
    ap.add_argument('--fmt', default='fixed12', choices=['rice', 'fixed12', 'w10', 'pair12', 'pairw10'])
    ap.add_argument('--tasks', type=int, default=12)  # >12: all 72 frozen fixtures
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--sim-jobs', type=int, default=4)
    ap.add_argument('--define', action='append', default=[])
    ap.add_argument('--plusarg', action='append', default=[])
    ap.add_argument('--lint-only', action='store_true')
    a = ap.parse_args()
    variant = (HERE / 'variants' / a.variant)
    out = HERE / 'runs' / (a.variant + '_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')); out.mkdir(parents=True)
    report = {'variant': a.variant, 'fmt': a.fmt, 'passed': False, 'phase': 'prepare', 'tasks': []}
    commit = lambda: (out / 'result.json').write_text(json.dumps(report, indent=1) + '\n')
    print('RUN=' + str(out), flush=True)
    env = dict(os.environ); env['PATH'] = str(MINGW / 'bin') + ';D:/Git/usr/bin;D:/Git/bin;' + env['PATH']
    env['VERILATOR_ROOT'] = str(MINGW / 'share/verilator')
    try:
        report['sources'] = stage_sources(variant, out)
        report['firmware'] = build_firmware(variant, out, env, a.define)
        rows = packets.export(out, a.fmt, a.tasks); report['packets'] = rows; commit()
        verilator = MINGW / 'bin/verilator_bin.exe'; make = Path('D:/mingw/mingw64/bin/mingw32-make.exe')
        common = ['--timing', '--autoflush', '--timescale-override', '1ns/1ps', '-Wno-fatal', '-DDISABLE_SV_ASSERTION=1',
                  '--top-module', 'tb_q12soc', '--prefix', 'Vq12gpio']
        if a.lint_only:
            run([verilator, '--lint-only', *common, '-f', out / 'sources.f'], out / 'lint.log', env, timeout=600)
            report['phase'] = 'lint_passed'; commit(); print('LINT_OK'); return
        # build cache keyed by source hashes
        key = hashlib.sha256(json.dumps([r['sha256'] for r in report['sources']] + [sha(p) for p in sorted((out / 'includes').glob('*'))]).encode()).hexdigest()[:16]
        cache = HERE / 'build_cache' / key
        exe = cache / 'Vq12gpio.exe'
        if not exe.is_file():
            if cache.exists(): shutil.rmtree(cache)
            cache.mkdir(parents=True)
            shutil.copy2(out / 'sources.f', cache / 'sources.f')
            report['phase'] = 'build'; commit()
            run([verilator, '--cc', '--main', '--exe', *common, '--Mdir', cache, '-f', out / 'sources.f'], out / 'build_0.log', env, timeout=1800)
            run([make, '-C', cache, '-f', 'Vq12gpio.mk', '-j' + str(a.jobs), 'SHELL=D:/Git/bin/sh.exe', 'CXX=g++', 'LINK=g++',
                 'CFG_CXXFLAGS_STD=-std=gnu++20', 'OPT_GLOBAL=-Os -fno-declone-ctor-dtor'], out / 'build_1.log', env, timeout=3600)
            for n in ['libgcc_s_seh-1.dll', 'libstdc++-6.dll', 'libwinpthread-1.dll']: shutil.copy2(MINGW / 'bin' / n, cache / n)
        report['executable'] = str(exe); report['phase'] = 'simulation'; commit()

        def simulate(row):
            case = out / row['directory']
            cmd = [exe, '+FIRMWARE=../firmware64.hex', '+INPUT=input.hex', '+EXPECTED=expected.hex', '+OUTPUT_DUMP=observed.hex',
                   '+INPUT_WORDS=' + str(row['input_words']), '+SERIAL_LOAD=0', '+OUTPUT_WORDS=' + str(packets.WRITE_TRANSACTIONS),
                   '+LAYER=' + row['task'][5:7], *['+' + p for p in a.plusarg]]
            run(cmd, case / 'simulation.log', env, cwd=case, timeout=3600)
            text = (case / 'simulation.log').read_text(errors='replace')
            if re.search(r'^Fatal:|^Error-|\$fatal|%Error', text, re.M): raise ValueError('Simulation fatal ' + row['task'])
            found = re.findall(r'^Q12GPIO_METRICS (.+)$', text, re.M)
            if len(found) != 1 or not re.search(r'^PASS ', text, re.M): raise ValueError('missing PASS/metrics ' + row['task'])
            metrics = {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', found[0])}
            actual = words(case / 'observed.hex'); expected = words(case / 'expected.hex')
            if actual != expected: raise ValueError('output mismatch ' + row['task'])
            dense = words(case / 'dense.hex')
            unpacked = [h for wd in actual[17:] for h in (wd & 65535, wd >> 16)]
            if unpacked != dense: raise ValueError('dense mismatch ' + row['task'])
            return {'task': row['task'], 'metrics': metrics, 'values_checked': 25344}

        with ThreadPoolExecutor(max_workers=a.sim_jobs) as pool:
            futs = [pool.submit(simulate, r) for r in rows]
            for f in as_completed(futs):
                t = f.result(); report['tasks'].append(t); report['tasks'].sort(key=lambda t: t['task']); commit()
                m = t['metrics']; print('TASK', t['task'], m['full_window_cycles'], flush=True)
        cyc = [t['metrics']['full_window_cycles'] for t in report['tasks']]
        report.update(passed=True, phase='complete', mean_cycles=sum(cyc) / len(cyc),
                      layers_per_s=len(cyc) * 150e6 / sum(cyc))
        commit()
        print('COMPLETE mean_cycles=%.2f layers/s=%.2f' % (report['mean_cycles'], report['layers_per_s']), flush=True)
    except BaseException as e:
        report.update(passed=False, phase='failed', error=repr(e)); commit(); raise


if __name__ == '__main__':
    main()
