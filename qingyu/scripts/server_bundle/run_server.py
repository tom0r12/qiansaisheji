#!/usr/bin/env python3
"""Run a verified bundle in a new directory; keep libraries/vendor read-only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--mode', choices=['behavioral', 'macro'], default='macro')
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--activity', action='store_true')
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if args.candidate not in manifest['candidates']:
        parser.error('candidate is not in manifest')
    for name, expected in manifest['files_sha256'].items():
        path = bundle / name
        if not path.is_file() or digest(path) != expected:
            raise RuntimeError('Bundle file missing or changed: ' + name)
    included_vendor = bundle / 'vendor/e203_hbirdv2'
    vendor = Path(os.environ.get('QINGYU_VENDOR_ROOT', str(included_vendor))).resolve()
    for name, expected in manifest['vendor_sha256'].items():
        path = vendor / name
        if not path.is_file() or digest(path) != expected:
            raise RuntimeError('Pinned external E203 source missing or changed: ' + str(path))
    if not manifest['images_included'] or not manifest['candidates'][args.candidate]['firmware_included']:
        raise RuntimeError('Source-only bundle: rebuild with --images, --provenance and --compile-firmware')
    models = Path(os.environ.get('QINGYU_SRAM_MODELS', '/storage1/admin_public_dir/SRAM_Lib_2025')).resolve()
    macro_files = [models / name / 'verilog' / (name + '.v')
                   for name in ['RAMSP128X16', 'RAMSP1024X16', 'RAMSP4096X16']]
    if args.mode == 'macro':
        for path in macro_files:
            if not path.is_file():
                raise RuntimeError('Missing vendor macro model: ' + str(path))
    vcs = os.environ.get('QINGYU_VCS') or shutil.which('vcs')
    if not vcs:
        known = Path('/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs')
        if known.is_file():
            vcs = str(known)
    if not vcs:
        raise RuntimeError('VCS not found; configure QINGYU_VCS')
    print('QINGYU_BUNDLE_PREFLIGHT_PASS candidate=' + args.candidate, flush=True)
    if args.preflight:
        return
    parent = Path(os.environ.get('QINGYU_RUN_PARENT', str(Path.home() / 'Desktop'))).resolve()
    if not parent.is_dir():
        raise RuntimeError('Run parent does not exist: ' + str(parent))
    work = Path(tempfile.mkdtemp(prefix='qingyu_verify_' + args.candidate + '_', dir=str(parent)))
    print('QINGYU_ISOLATED_RUN=' + str(work), flush=True)
    inputs = work / 'inputs'
    shutil.copytree(str(bundle), str(inputs))
    for name, expected in manifest['files_sha256'].items():
        if digest(inputs / name) != expected:
            raise RuntimeError('Input changed while freezing run: ' + name)
    if 'QINGYU_VENDOR_ROOT' not in os.environ and manifest.get('vendor_included'):
        vendor = inputs / 'vendor/e203_hbirdv2'
    src = inputs / 'filelists' / (args.candidate + '_' + args.mode + '.f')
    source_lines = []
    for line in src.read_text().splitlines():
        if line.startswith('@VENDOR@/'):
            source_lines.append(str(vendor / line[len('@VENDOR@/'):]))
        else:
            source_lines.append(str(inputs / line))
    if args.mode == 'macro':
        source_lines.extend(map(str, macro_files))
    # VCS file lists use one quoted pathname per line, allowing spaces in roots.
    if any('"' in s or '\n' in s for s in source_lines):
        raise RuntimeError('Unsupported quote/newline in source pathname')
    resolved = work / 'sources.f'
    resolved.write_text('\n'.join('"' + s + '"' for s in source_lines) + '\n')
    includes = ['+incdir+' + str(vendor / 'rtl/e203' / name)
                for name in ['core', 'perips', 'perips/apb_i2c']]
    command = [vcs, '-full64', '-sverilog', '-timescale=1ns/1ps',
               '+define+DISABLE_SV_ASSERTION=1', '-top', 'tb_qingyu_soc_performance',
               *includes, '-f', str(resolved), '-Mdir=' + str(work / 'csrc'),
               '-o', str(work / 'simv')]
    if args.mode == 'macro':
        command.append('+define+ARM_UD_MODEL')
    if args.activity:
        command.append('-debug_access+all')
    result = dict(passed=False, candidate=args.candidate, mode=args.mode,
                  data_kind=manifest['data_kind'], compile_command=command,
                  manifest_sha256=digest(bundle / 'manifest.json'),
                  vendor_model_sha256={str(p): digest(p) for p in macro_files} if args.mode == 'macro' else {},
                  layers=[], limits=['No synthesis, STA, equivalence, power or area acceptance is implied'])
    report = work / 'result.json'
    report.write_text(json.dumps(result, indent=2))

    def run(cmd, log):
        with log.open('w') as stream:
            rc = subprocess.call(cmd, cwd=str(work), stdout=stream, stderr=subprocess.STDOUT)
        if rc:
            raise RuntimeError('Tool failed; retained log: ' + str(log))

    run(command, work / 'compile.log')
    for layer in range(12):
        name = 'layer%02d' % layer
        vector = inputs / 'images' / name
        fw = inputs / 'firmware' / args.candidate / name / 'firmware64.hex'
        # Legacy SV fixtures store plusarg strings in 1024-bit registers.
        # Relative paths avoid truncation when the contest home path is long.
        cmd = [str(work / 'simv'), '+FIRMWARE=' + str(fw.relative_to(work)),
               '+SHARED=' + str((vector / 'shared.hex').relative_to(work)),
               '+EXPECTED=' + str((vector / 'expected.hex').relative_to(work))]
        if args.activity:
            cmd.append('+ACTIVITY=' + name + '.vcd')
        log = work / (name + '.log')
        run(cmd, log)
        text = log.read_text(errors='replace')
        complete = re.findall(r'QINGYU_COMPLETE_TASK cycles=(\d+) validation_and_setup_cycles=(\d+)', text)
        if 'PASS real E203' not in text or len(complete) != 1:
            raise RuntimeError('Missing output/complete-window PASS: ' + str(log))
        cycles, setup = map(int, complete[0])
        result['layers'].append(dict(layer=layer, outputs=25344,
                                     complete_task_cycles=cycles, validation_and_setup_cycles=setup))
        report.write_text(json.dumps(result, indent=2))
        print('QINGYU_LAYER_PASS %s complete_cycles=%d' % (name, cycles), flush=True)
    result['passed'] = True
    result['mean_complete_cycles'] = sum(r['complete_task_cycles'] for r in result['layers']) / 12.0
    report.write_text(json.dumps(result, indent=2))
    print('QINGYU_12_LAYER_PASS ' + str(report), flush=True)


if __name__ == '__main__':
    main()
