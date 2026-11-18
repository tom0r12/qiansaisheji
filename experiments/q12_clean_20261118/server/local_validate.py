"""Local validation of a server package's vendor tree using LOCAL MOCK SRAMs.

Builds the exact vendor source order (ASIC SRAM wrappers, derived vendor tb,
macro presence binds) with behavioral mock RAMSP models in Verilator and runs
N tasks. Proves the package's own logic/testbench, NOT manufacturer models.
"""
from pathlib import Path
import json, os, re, subprocess, sys, shutil
S = Path(__file__).resolve().parent
WORK = S.parents[3]
MINGW = WORK / 'qingyu/tools/verilator/mingw64'


def main(bundle, tasks=2):
    B = Path(bundle); V = B / 'vendor'; m = json.loads((V / 'manifest.json').read_text())
    out = B.parent.parent / ('local_validation_' + B.name); out.mkdir(exist_ok=True)
    env = dict(os.environ); env['PATH'] = str(MINGW / 'bin') + ';D:/Git/usr/bin;D:/Git/bin;' + env['PATH']; env['VERILATOR_ROOT'] = str(MINGW / 'share/verilator')
    files = [V / n for n in m['vendor_source_order']] + [S / 'local_mock/mock_rams.v']
    (out / 'sources.f').write_text('+incdir+' + (V / 'includes').as_posix() + '\n' + '\n'.join(p.as_posix() for p in files) + '\n')
    build = out / 'vbuild'
    common = ['--timing', '--autoflush', '--timescale-override', '1ns/1ps', '-Wno-fatal', '-DDISABLE_SV_ASSERTION=1', '-DQ12_USE_VENDOR_MACROS=1',
              '--top-module', 'tb_q12soc', '--prefix', 'Vq12v']
    def run(cmd, log, cwd=None):
        with open(log, 'w') as f: r = subprocess.run([str(c) for c in cmd], stdout=f, stderr=subprocess.STDOUT, env=env, cwd=cwd)
        if r.returncode: raise SystemExit('FAILED: see ' + str(log))
    if not (build / 'Vq12v.exe').is_file():
        run([MINGW / 'bin/verilator_bin.exe', '--cc', '--main', '--exe', *common, '--Mdir', build, '-f', out / 'sources.f'], out / 'build0.log')
        run(['D:/mingw/mingw64/bin/mingw32-make.exe', '-C', build, '-f', 'Vq12v.mk', '-j8', 'SHELL=D:/Git/bin/sh.exe', 'CXX=g++', 'LINK=g++',
             'CFG_CXXFLAGS_STD=-std=gnu++20', 'OPT_GLOBAL=-Os -fno-declone-ctor-dtor'], out / 'build1.log')
        for n in ['libgcc_s_seh-1.dll', 'libstdc++-6.dll', 'libwinpthread-1.dll']: shutil.copy2(str(MINGW / 'bin' / n), str(build / n))
    res = []
    for row in m['tasks'][:tasks]:
        case = out / row['directory']; case.mkdir(exist_ok=True)
        for n in ['input.hex', 'expected.hex', 'dense.hex']: shutil.copy2(str(V / 'tasks' / row['directory'] / n), str(case / n))
        shutil.copy2(str(V / 'firmware64.hex'), str(case / 'firmware64.hex'))
        run([build / 'Vq12v.exe', '+FIRMWARE=firmware64.hex', '+INPUT=input.hex', '+EXPECTED=expected.hex', '+OUTPUT_DUMP=observed.hex',
             '+INPUT_WORDS=' + str(row['input_words']), '+OUTPUT_WORDS=12690', '+LAYER=' + row['task'][5:7]], case / 'simulation.log', cwd=case)
        t = (case / 'simulation.log').read_text(errors='replace')
        ok = bool(re.search(r'^PASS real E203 Q12 vendor task;', t, re.M)) and 'Q12_MACRO_READBACK_COMPLETE words=131072 output_words=12689' in t \
            and ('Q12_VENDOR_MACROS RAMSP128X16=%d RAMSP1024X16=6 RAMSP4096X16=80 total=%d' % (m['expected_macros']['RAMSP128X16'], m['expected_macros']['total'])) in t \
            and not re.search(r'%Error|\$fatal|Fatal', t)
        cyc = re.search(r'full_window_cycles=(\d+)', t)
        res.append({'task': row['task'], 'ok': ok, 'cycles': int(cyc.group(1)) if cyc else None})
        print(res[-1], flush=True)
    (out / 'result.json').write_text(json.dumps(res, indent=1))
    if not all(r['ok'] for r in res): raise SystemExit('LOCAL VENDOR VALIDATION FAILED')
    print('LOCAL_VENDOR_VALIDATION_OK (mock SRAMs)')


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2)
