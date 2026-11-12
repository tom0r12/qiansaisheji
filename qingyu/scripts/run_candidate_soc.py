"""Portable Linux/WSL E203 cold-task comparison for production OUT16 candidates.

Synthetic data checks integration and bit accuracy; it is not KWT accuracy or
official PPA. The complete window includes the initial parameter-validation
reads that precede the historical staging-command timing window.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFINES = ['QINGYU_BLOCK_COPY', 'QINGYU_READ_AHEAD', 'QINGYU_FAST_TASK',
           'QINGYU_DOUBLE_BUFFER', 'QINGYU_PIPE_MAC', 'QINGYU_OUT16']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_build_arguments(arguments, directory):
    """Keep semantic compiler arguments; normalize only run paths and jobs."""
    result = []
    index = 0
    generated = {'--Mdir': directory / 'obj', '-f': directory / 'sources.f'}
    while index < len(arguments):
        argument = arguments[index]
        if argument in generated or argument == '-j':
            if index + 1 >= len(arguments):
                raise ValueError('Missing compiler option value: ' + argument)
            value = arguments[index + 1]
            if argument in generated:
                if (ROOT / value).resolve() != generated[argument].resolve():
                    raise ValueError('Unexpected generated build path: ' + value)
                result.extend([argument, '<run>/' + generated[argument].name])
            index += 2
        else:
            result.append(argument)
            index += 1
    return result


def verify_build_arguments(prior, build_directory, expected):
    """Older runs must provide Verilator's recorded command, never bypass it."""
    actual = prior.get('simulator_build_arguments')
    if actual is None:
        record = build_directory / 'obj' / 'Vcandidate__verFiles.dat'
        commands = [line for line in record.read_text(encoding='utf-8').splitlines()
                    if line.startswith('C ')]
        if len(commands) != 1:
            raise ValueError('Missing or ambiguous recorded Verilator command; rebuild required')
        quoted = shlex.split(commands[0])
        if len(quoted) != 2:
            raise ValueError('Unsupported recorded Verilator command; rebuild required')
        actual = normalized_build_arguments(shlex.split(quoted[1]), build_directory)
    if actual != expected:
        raise ValueError('Simulator build arguments changed; rebuild required')


def verify_images(directory, data_kind, layers):
    """Reject mislabeled or modified external vectors before simulation."""
    manifest_path = directory / 'images_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('data_kind') != data_kind or manifest.get('output_bits') != 16:
        raise ValueError('Image provenance kind or output width does not match this run')
    records = manifest.get('layers', [])
    by_layer = {record['layer']: record for record in records}
    if len(by_layer) != len(records) or not set(range(layers)) <= set(by_layer):
        raise ValueError('Image manifest has duplicate or missing layers')
    for layer in range(layers):
        record = by_layer[layer]
        for name in ['shared.hex', 'expected.hex', 'config.json']:
            path = directory / f'layer{layer:02d}' / name
            if sha(path) != record['files'].get(name):
                raise ValueError(f'Image changed after export: {path}')
    return manifest, sha(manifest_path)


def run(command, log, cwd=ROOT, timeout=600):
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(list(map(str, command)), cwd=cwd, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{log}\n{log.read_text(errors="replace")[-5000:]}')


def synthetic_images(directory, seed):
    """INT64 matrix sum is exact for these bounded, independently generated data."""
    rng = np.random.default_rng(seed)
    x = rng.integers(-30000, 30001, (99, 64), dtype=np.int16)
    w = rng.integers(-30000, 30001, (64, 256), dtype=np.int16)
    b = rng.integers(-(1 << 30), 1 << 30, 256, dtype=np.int64)
    shifts = rng.integers(17, 23, 256, dtype=np.uint8)
    a = x.astype(np.int64) @ w.astype(np.int64) + b
    assert np.all(np.abs(a) < (1 << 47))
    s = shifts.astype(np.int64)
    mag = np.abs(a)
    q = mag >> s
    rem = mag - (q << s)
    half = np.int64(1) << (s - 1)
    q += (rem > half) | ((rem == half) & ((q & 1) != 0))
    q = np.clip(np.sign(a) * q, -32768, 32767).astype('<i2')
    image = bytearray(512 * 1024)
    for offset, value, dtype in [(0, x, '<i2'), (0x4000, w, '<i2'),
                                  (0xc000, b, '<i8'), (0xc800, shifts, 'u1')]:
        payload = np.asarray(value, dtype=dtype).tobytes()
        image[0x40000 + offset:0x40000 + offset + len(payload)] = payload
    shared = np.frombuffer(image, dtype='<u4')
    expected = np.frombuffer(q.tobytes(), dtype='<u4')
    for filename, words in [('shared.hex', shared), ('expected.hex', expected)]:
        (directory / filename).write_text(''.join(f'{int(v):08x}\n' for v in words), encoding='ascii')


def complete_window_monitor(source):
    text = source.read_text(encoding='utf-8')
    marker = ' integer ticks=0, start_tick=-1, live_tick=-1, load_end=-1, end_tick=-1;'
    assert text.count(marker) == 1
    text = text.replace(marker, marker + '\n integer task_start_tick=-1, tp;')
    marker = '  ticks = ticks + 1;'
    assert text.count(marker) == 1
    text = text.replace(marker, marker + '''
  // Start on first attempted task-source read, including validation traffic.
  for (tp=0;tp<NP;tp=tp+1)
   if (task_start_tick<0 && `MEM.cmd_valid[tp] && `MEM.cmd_read[tp] &&
       `MEM.cmd_addr[32*tp+:32]>=32'ha0040000 &&
       `MEM.cmd_addr[32*tp+:32]<32'ha0050000) task_start_tick=ticks;
''')
    marker = '     end_tick=ticks;'
    assert text.count(marker) == 1
    text = text.replace(marker, marker + '''
     if (task_start_tick<0) $fatal(1,"missing complete task start");
     $display("QINGYU_COMPLETE_TASK cycles=%0d validation_and_setup_cycles=%0d start_cycle=%0d end_cycle=%0d",
      end_tick-task_start_tick,start_tick-task_start_tick,task_start_tick,end_tick);
''')
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', default='opt14_ybank2')
    parser.add_argument('--layers', type=int, default=1)
    parser.add_argument('--seed', type=int, default=20261111)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--images', type=Path, help='Existing layerNN/{shared,expected}.hex; provenance required')
    parser.add_argument('--data-kind', default='SYNTHETIC_ENGINEERING')
    parser.add_argument('--reuse-build', type=Path, help='Reuse a previous run only after checking every compiled source hash')
    args = parser.parse_args()
    if not 1 <= args.layers <= 12 or args.jobs < 1:
        parser.error('layers must be 1..12, jobs must be positive')
    if args.images and args.data_kind == 'SYNTHETIC_ENGINEERING':
        parser.error('Supply an explicit --data-kind for external images')
    if not args.images and args.data_kind != 'SYNTHETIC_ENGINEERING':
        parser.error('Non-synthetic data requires --images and its provenance manifest')
    provenance = verify_images(args.images, args.data_kind, args.layers) if args.images else None
    for tool in ['verilator', 'g++', 'make', 'riscv64-unknown-elf-gcc', 'riscv64-unknown-elf-objcopy']:
        if not shutil.which(tool):
            parser.error(f'{tool} missing; run scripts/setup_local.ps1 first and use WSL')
    candidate = ROOT / 'experiments/h1500v' / args.candidate / 'rtl'
    if not candidate.is_dir():
        parser.error(f'missing candidate {candidate}')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    work = ROOT / 'build' / f'soc_{args.candidate}_{stamp}'
    work.mkdir(parents=True)
    if provenance:
        (work / 'images_manifest.json').write_text(json.dumps(provenance[0], indent=2))
    fixture = ROOT / 'experiments/h1500v/opt13_row8/tb'
    monitor = work / 'tb_complete_task.sv'
    monitor.write_text(complete_window_monitor(fixture / 'tb_qingyu_soc_performance.sv'))
    config = work / 'config.v'
    config.write_text('`timescale 1ns/1ps\n' + ''.join(f'`define {d}\n' for d in DEFINES))
    baseline = (ROOT / 'build/dual_row_study/sources.f').read_text().splitlines()
    replacements = {
        'build/block_config.v': config, 'build/timescale.v': None,
        'build/dual_row_study/qingyu_accel.sv': candidate / 'qingyu_accel.sv',
        'rtl/qingyu_fio.sv': candidate / 'qingyu_fio.sv',
        'rtl/qingyu_shared_sram.sv': candidate / 'qingyu_shared_sram_mp.sv',
        'generated/qingyu_e203_soc_top.v': candidate / 'qingyu_e203_soc_top.v',
        'tb/tb_qingyu_soc.sv': fixture / 'tb_qingyu_soc.sv',
        'tb/tb_qingyu_soc_performance.sv': monitor,
    }
    sources = [replacements.get(name, ROOT / name) for name in baseline if name.strip()]
    sources = [p for p in sources if p is not None]
    missing = [str(p) for p in sources if not p.is_file()]
    if missing:
        raise FileNotFoundError('Restore pinned dependencies with setup_local.ps1: ' + '\n'.join(missing))
    filelist = work / 'sources.f'
    filelist.write_text('\n'.join(str(p.relative_to(ROOT)) for p in sources) + '\n')
    obj = work / 'obj'
    cmd = ['verilator', '--binary', '--timing', '--autoflush', '--timescale-override', '1ns/1ps',
           '--top-module', 'tb_qingyu_soc_performance', '--prefix', 'Vcandidate', '--Mdir', obj,
           '-Wno-fatal', '-DDISABLE_SV_ASSERTION=1', '-j', str(args.jobs),
           '-CFLAGS', '-O1', '-f', filelist]
    cmd += ['-Ivendor/e203_hbirdv2/rtl/e203/' + d for d in ['core', 'perips', 'perips/apb_i2c']]
    build_arguments = normalized_build_arguments(list(map(str, cmd[1:])), work)
    if args.reuse_build:
        previous = (ROOT / args.reuse_build).resolve()
        prior = json.loads((previous / 'result.json').read_text())
        if prior['candidate'] != args.candidate:
            raise ValueError('Cannot reuse a different candidate')
        old_sources = prior['sources_sha256']
        def normalized_order(lines, directory):
            prefix = str(directory.relative_to(ROOT)) + '/'
            return [('<generated>/' + n[len(prefix):]) if n.startswith(prefix) else n
                    for n in lines if n.strip()]
        if normalized_order((previous/'sources.f').read_text().splitlines(), previous) != normalized_order(filelist.read_text().splitlines(), work):
            raise ValueError('Compiled source order changed; rebuild required')
        for filename, expected_hash in old_sources.items():
            if sha(ROOT / filename) != expected_hash:
                raise ValueError('Previously compiled source changed: ' + filename)
        # Generated files live in run-specific directories, so compare their
        # content as well as the stable RTL paths, not just the old directory.
        old_stable = {n:h for n,h in old_sources.items() if not n.startswith(str(previous.relative_to(ROOT)) + '/')}
        new_stable = {str(p.relative_to(ROOT)):sha(p) for p in sources if not p.is_relative_to(work)}
        if old_stable != new_stable:
            raise ValueError('Compiled file list differs; rebuild required')
        for generated in ['config.v', 'tb_complete_task.sv']:
            if sha(previous/generated) != sha(work/generated):
                raise ValueError('Generated configuration/monitor changed; rebuild required')
        obj = ROOT / prior.get('simulator_build_directory', str(previous.relative_to(ROOT))) / 'obj'
        verify_build_arguments(prior, obj.parent, build_arguments)
        if not (obj/'Vcandidate').is_file():
            raise FileNotFoundError('Previous simulator binary missing')
        if prior.get('simulator_sha256') and sha(obj/'Vcandidate') != prior['simulator_sha256']:
            raise ValueError('Previous simulator binary changed')
        print(f'Reusing verified RTL build: {previous}', flush=True)
    else:
        print(f'Building {args.candidate}: {work}', flush=True)
        run(cmd, work / 'build.log', timeout=900)
    report = dict(candidate=args.candidate, data_kind=args.data_kind, passed=False,
                  clock_hz_assumed=150000000, layers=[],
                  limits=['behavioral SRAM; no official accuracy, STA, area or power result',
                          'complete timing starts with the first parameter-source read request'],
                  sources_sha256={str(p.relative_to(ROOT)): sha(p) for p in sources},
                  simulator_sha256=sha(obj/'Vcandidate'),
                  simulator_build_directory=str(obj.parent.relative_to(ROOT)),
                  simulator_build_arguments=build_arguments,
                  simulator_build_arguments_sha256=hashlib.sha256(json.dumps(build_arguments, separators=(',', ':')).encode()).hexdigest(),
                  firmware_sha256={p.name: sha(p) for p in [candidate/'soc_perf_main.c',candidate/'qingyu_accel.c',candidate/'qingyu_accel.h']})
    if provenance:
        report['images_manifest_sha256'] = provenance[1]
        report['image_source_commit'] = provenance[0].get('source_commit')
        report['official_600_sample_evaluation'] = provenance[0].get('official_600_sample_evaluation', False)
    result_path = work / 'result.json'
    result_path.write_text(json.dumps(report, indent=2))
    for layer in range(args.layers):
        case = work / f'layer{layer:02d}'
        case.mkdir()
        cc = ['riscv64-unknown-elf-gcc', f'-DQINGYU_TEST_LAYER={layer}',
              *['-D' + d for d in DEFINES], '-march=rv32imac', '-misa-spec=2.2', '-mabi=ilp32',
              '-ffreestanding', '-fno-builtin', '-msmall-data-limit=0', '-ffunction-sections',
              '-fdata-sections', '-Wall', '-Wextra', '-Werror', '-nostdlib', '-nostartfiles',
              '-O3', '-flto', '-funroll-loops', '-I' + str(candidate), '-Isw', '-Tsw/linker.ld',
              '-Wl,--gc-sections', 'sw/startup.S', candidate/'soc_perf_main.c',
              candidate/'qingyu_accel.c', 'sw/runtime.c', '-lgcc', '-o', case/'firmware.elf']
        run(cc, case/'compile.log')
        run(['riscv64-unknown-elf-objcopy', '-O', 'binary', case/'firmware.elf', case/'firmware.bin'], case/'objcopy.log')
        raw = (case/'firmware.bin').read_bytes()
        if len(raw) > 65536:
            raise ValueError('Firmware exceeds ITCM')
        raw = raw.ljust(65536, b'\0')
        (case/'firmware64.hex').write_text(''.join(f'{int.from_bytes(raw[i:i+8], "little"):016x}\n' for i in range(0,65536,8)))
        if args.images:
            for name in ['shared.hex', 'expected.hex']:
                shutil.copy2(args.images/f'layer{layer:02d}'/name, case/name)
        else:
            synthetic_images(case, args.seed + layer)
        hashes = {p.name: sha(p) for p in case.glob('*.hex')}
        if provenance:
            exported = next(r for r in provenance[0]['layers'] if r['layer'] == layer)['files']
            if any(hashes[name] != exported[name] for name in ['shared.hex', 'expected.hex']):
                raise ValueError('External image changed between verification and copying')
        run([obj/'Vcandidate', '+FIRMWARE=firmware64.hex', '+SHARED=shared.hex', '+EXPECTED=expected.hex'], case/'simulation.log', cwd=case)
        text = (case/'simulation.log').read_text()
        if 'PASS real E203' not in text:
            raise RuntimeError(f'Output checker did not pass: {case}')
        complete = re.findall(r'QINGYU_COMPLETE_TASK cycles=(\d+) validation_and_setup_cycles=(\d+)', text)
        legacy = re.findall(r'QINGYU_PERF_WINDOW cycles=(\d+)', text)
        if len(complete) != 1 or len(legacy) != 1:
            raise RuntimeError('Missing or repeated timing windows')
        cycles, overhead = map(int, complete[0])
        if cycles != int(legacy[0]) + overhead:
            raise RuntimeError('Inconsistent timing windows')
        if hashes != {p.name: sha(p) for p in case.glob('*.hex')}:
            raise RuntimeError('Input changed during execution')
        row = dict(layer=layer, outputs=25344, complete_task_cycles=cycles,
                   historical_window_cycles=int(legacy[0]), validation_and_setup_cycles=overhead,
                   input_sha256=hashes)
        report['layers'].append(row)
        result_path.write_text(json.dumps(report, indent=2))
        print(json.dumps(row), flush=True)
    report['passed'] = True
    report['mean_complete_cycles'] = sum(r['complete_task_cycles'] for r in report['layers'])/args.layers
    report['tasks_per_second_at_assumed_150mhz'] = 150000000/report['mean_complete_cycles']
    result_path.write_text(json.dumps(report, indent=2))
    print(f'PASS {result_path}', flush=True)


if __name__ == '__main__':
    main()
