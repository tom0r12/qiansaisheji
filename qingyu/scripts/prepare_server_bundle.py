"""Build an isolated opt13/14/15 server verification bundle without uploading.

Only an explicit allowlist of engineering sources, optional 12-layer images,
and freshly compiled firmware is included. PDKs and upstream RTL stay external.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ('opt13_row8', 'opt14_ybank2', 'opt15_validate4')
DEFINES = ('QINGYU_BLOCK_COPY', 'QINGYU_READ_AHEAD', 'QINGYU_FAST_TASK',
           'QINGYU_DOUBLE_BUFFER', 'QINGYU_PIPE_MAC', 'QINGYU_OUT16')
FIXTURE = ROOT / 'experiments/h1500v/opt13_row8'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))


def copy(source, dest):
    if not source.is_file():
        raise FileNotFoundError(source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)


def complete_monitor(macro=False):
    text = (FIXTURE / 'tb/tb_qingyu_soc_performance.sv').read_text()
    marker = ' integer ticks=0, start_tick=-1, live_tick=-1, load_end=-1, end_tick=-1;'
    assert text.count(marker) == 1
    text = text.replace(marker, marker + '\n integer task_start_tick=-1, tp;')
    # The inherited dumpon begins too late: move it into the complete window.
    assert text.count('   if(dump_enabled) $dumpon;') == 1
    text = text.replace('   if(dump_enabled) $dumpon;', '')
    marker = '  ticks = ticks + 1;'
    assert text.count(marker) == 1
    text = text.replace(marker, marker + '''
  for (tp=0;tp<NP;tp=tp+1)
   if (fixture.rst_n && task_start_tick<0 && `MEM.cmd_valid[tp] && `MEM.cmd_read[tp] &&
       `MEM.cmd_addr[32*tp+:32]>=32'ha0040000 &&
       `MEM.cmd_addr[32*tp+:32]<32'ha0050000) begin
    task_start_tick=ticks;
    $display("QINGYU_COMPLETE_START cycle=%0d time_ps=%0t",ticks,$realtime);
    if(dump_enabled) $dumpon;
   end
''')
    marker = '     end_tick=ticks;'
    assert text.count(marker) == 1
    text = text.replace(marker, marker + '''
     if (task_start_tick<0) $fatal(1,"missing complete task start");
     $display("QINGYU_COMPLETE_TASK cycles=%0d validation_and_setup_cycles=%0d start_cycle=%0d end_cycle=%0d",
      end_tick-task_start_tick,start_tick-task_start_tick,task_start_tick,end_tick);
     $display("QINGYU_COMPLETE_END cycle=%0d time_ps=%0t",ticks,$realtime);
''')
    if macro:
        # Physical macro fixture reads mailbox itself. It has no MEM.mem array.
        text, n = re.subn(r'   \$display\("QINGYU_PERF_FIRMWARE.*?;\n',
                          '   $display("QINGYU_PHYSICAL_READBACK_PENDING");\n', text, flags=re.S)
        assert n == 1
    return text


def check_hex(path, width, count):
    lines = path.read_text(encoding='ascii').splitlines()
    if len(lines) != count or any(re.fullmatch('[0-9a-fA-F]{%d}' % width, s) is None for s in lines):
        raise ValueError(f'{path}: expected exactly {count} {width}-digit hex words')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', action='append', choices=CANDIDATES)
    parser.add_argument('--images', type=Path, help='12 layerNN/{shared,expected}.hex directories')
    parser.add_argument('--provenance', type=Path, action='append', help='Source/model/split/config JSON; repeatable')
    parser.add_argument('--data-kind', default='NO_IMAGES')
    parser.add_argument('--compile-firmware', action='store_true')
    parser.add_argument('--firmware-run', action='append', default=[],
                        help='candidate=passed 12-layer run directory; verify and reuse its firmware')
    parser.add_argument('--riscv-prefix', default='riscv64-unknown-elf-')
    parser.add_argument('--include-vendor', action='store_true',
                        help='Include the small public E203 RTL tree and its LICENSE')
    parser.add_argument('--output', type=Path, help='New output directory; existing directory is rejected')
    args = parser.parse_args()
    candidates = args.candidate or list(CANDIDATES)
    if len(set(candidates)) != len(candidates):
        parser.error('duplicate candidate')
    if args.images and (not args.provenance or args.data_kind == 'NO_IMAGES'):
        parser.error('--images requires --provenance and explicit --data-kind')
    if args.provenance and not args.images:
        parser.error('--provenance requires --images')
    firmware_runs = {}
    for item in args.firmware_run:
        name, separator, value = item.partition('=')
        if not separator or name not in candidates or name in firmware_runs:
            parser.error('invalid or duplicate --firmware-run candidate=directory')
        firmware_runs[name] = Path(value).resolve()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = (args.output or ROOT / 'build/server_bundles' / stamp).resolve()
    output.mkdir(parents=True, exist_ok=False)
    bundle = output / 'qingyu_server_bundle'
    bundle.mkdir()
    manifest = dict(format_version=1, created_utc=stamp, candidates={},
                    images_included=bool(args.images), data_kind=args.data_kind,
                    vendor_sha256={}, files_sha256={},
                    timing='first task-source read attempt through last output write response',
                    ppa_status='not executed; see SERVER_README.md')
    manifest['packager_sha256'] = sha(Path(__file__))
    copy(Path(__file__).parent / 'server_bundle/run_server.py', bundle / 'run_server.py')
    write(bundle / 'run_vcs.sh', '#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\nexec python3 run_server.py "$@"\n')
    write(bundle / 's.sh', '#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\nexec python3 run_server.py --candidate opt15_validate4 --mode macro "$@"\n')
    write(bundle / 'common/config.v', '`timescale 1ns/1ps\n' + ''.join('`define ' + d + '\n' for d in DEFINES))
    copy(FIXTURE / 'tb/tb_qingyu_soc.sv', bundle / 'common/tb_behavior.sv')
    physical = (FIXTURE / 'macro/tb_qingyu_soc_macros.sv').read_text()
    # "mailbox" is a SystemVerilog keyword, not a portable array identifier.
    physical = re.sub(r'\bmailbox\b', 'perf_mailbox', physical)
    assert physical.count('PASS real E203 + 129 SRAM macros:') == 1
    physical = physical.replace('PASS real E203 + 129 SRAM macros:', 'PASS real E203 + vendor SRAM:')
    write(bundle / 'common/tb_macro.sv', physical)
    write(bundle / 'common/monitor_behavior.sv', complete_monitor())
    write(bundle / 'common/monitor_macro.sv', complete_monitor(True))
    baseline = (ROOT / 'build/dual_row_study/sources.f').read_text().splitlines()
    skip = {'build/block_config.v', 'build/timescale.v'}
    replacements = {
        'build/dual_row_study/qingyu_accel.sv': 'qingyu_accel.sv',
        'rtl/qingyu_fio.sv': 'qingyu_fio.sv',
        'rtl/qingyu_shared_sram.sv': 'qingyu_shared_sram_mp.sv',
        'generated/qingyu_e203_soc_top.v': 'qingyu_e203_soc_top.v',
    }
    vendor = ROOT / 'vendor/e203_hbirdv2'
    for p in sorted((vendor / 'rtl/e203').rglob('*')):
        if p.is_file() and p.suffix in ('.v', '.sv', '.vh', '.svh'):
            manifest['vendor_sha256'][p.relative_to(vendor).as_posix()] = sha(p)
    if not manifest['vendor_sha256']:
        raise RuntimeError('Pinned E203 RTL absent; restore it before packaging')
    manifest['vendor_included'] = args.include_vendor
    if args.include_vendor:
        for name in manifest['vendor_sha256']:
            copy(vendor / name, bundle / 'vendor/e203_hbirdv2' / name)
        copy(vendor / 'LICENSE', bundle / 'vendor/e203_hbirdv2/LICENSE')
    for candidate in candidates:
        rtl = ROOT / 'experiments/h1500v' / candidate / 'rtl'
        for p in sorted(rtl.rglob('*')):
            if p.is_file() and p.suffix in ('.sv', '.v', '.c', '.h'):
                copy(p, bundle / 'candidates' / candidate / 'rtl' / p.relative_to(rtl))
        entry = dict(firmware_included=bool(args.compile_firmware or candidate in firmware_runs),
                     source_private_ram128=41 if candidate == 'opt13_row8' else 37,
                     source_private_ram1024=16, fixed_shared_ram4096=64)
        manifest['candidates'][candidate] = entry
        behavior = ['common/config.v']
        for name in baseline:
            if not name or name in skip:
                continue
            if name.startswith('vendor/e203_hbirdv2/'):
                behavior.append('@VENDOR@/' + name[len('vendor/e203_hbirdv2/'):])
            elif name in replacements:
                behavior.append('candidates/' + candidate + '/rtl/' + replacements[name])
            elif name == 'tb/tb_qingyu_soc.sv':
                behavior.append('common/tb_behavior.sv')
            elif name == 'tb/tb_qingyu_soc_performance.sv':
                behavior.append('common/monitor_behavior.sv')
            else:
                copy(ROOT / name, bundle / 'common' / name)
                behavior.append('common/' + name)
        removed = {'@VENDOR@/rtl/e203/general/sirv_gnrl_ram.v',
                   '@VENDOR@/rtl/e203/general/sirv_sim_ram.v',
                   'common/rtl/qingyu_sram16.sv',
                   'candidates/' + candidate + '/rtl/qingyu_shared_sram_mp.sv'}
        macro = [x.replace('common/tb_behavior.sv', 'common/tb_macro.sv')
                   .replace('common/monitor_behavior.sv', 'common/monitor_macro.sv')
                 for x in behavior if x not in removed]
        for name in ('qingyu_banked_sram.sv', 'qingyu_sram16.sv', 'sirv_gnrl_ram.v'):
            copy(ROOT / 'rtl/asic' / name, bundle / 'common/rtl/asic' / name)
            macro.append('common/rtl/asic/' + name)
        macro.append('candidates/' + candidate + '/rtl/asic/qingyu_shared_sram_mp.sv')
        write(bundle / 'filelists' / (candidate + '_behavioral.f'), '\n'.join(behavior) + '\n')
        write(bundle / 'filelists' / (candidate + '_macro.f'), '\n'.join(macro) + '\n')
        synth = [x for x in macro if not x.startswith('common/tb_') and not x.startswith('common/monitor_')]
        write(bundle / 'filelists' / (candidate + '_soc_synth.f'), '\n'.join(synth) + '\n')
    for name in ('startup.S', 'runtime.c', 'linker.ld'):
        copy(ROOT / 'sw' / name, bundle / 'common/sw' / name)
    for name in ('synth_dc.tcl', 'formality_margin.tcl', 'check_fixed_netlist_corners.tcl',
                 'probe_timing_inputs.tcl', 'probe_server_sram.tcl'):
        copy(ROOT / 'scripts' / name, bundle / 'historical_reference' / name)
    copy(ROOT / 'constraints/accelerator.sdc', bundle / 'historical_reference/accelerator.sdc')
    if args.images:
        provenance_index = []
        for index, source in enumerate(args.provenance):
            provenance = json.loads(source.read_text(encoding='utf-8-sig'))
            if not isinstance(provenance, dict) or not provenance:
                raise ValueError('Provenance must be a nonempty JSON object')
            target = f'provenance_{index}.json'
            write(bundle / 'images' / target, json.dumps(provenance, ensure_ascii=False, indent=2))
            provenance_index.append(dict(source_name=source.name, source_sha256=sha(source), file=target))
        write(bundle / 'images/provenance.json', json.dumps(provenance_index, indent=2))
        for layer in range(12):
            source = args.images / f'layer{layer:02d}'
            for name, count in [('shared.hex', 131072), ('expected.hex', 12672)]:
                check_hex(source / name, 8, count)
                copy(source / name, bundle / 'images' / f'layer{layer:02d}' / name)
    if args.compile_firmware:
        gcc, objcopy = args.riscv_prefix + 'gcc', args.riscv_prefix + 'objcopy'
        if not shutil.which(gcc) or not shutil.which(objcopy):
            raise RuntimeError('RISC-V compiler missing; run packager in configured Linux/WSL')
        manifest['firmware_compiler'] = subprocess.check_output([gcc, '--version'], text=True).splitlines()[0]
        for candidate in candidates:
            if candidate in firmware_runs:
                continue
            rtl = bundle / 'candidates' / candidate / 'rtl'
            for layer in range(12):
                dest = bundle / 'firmware' / candidate / f'layer{layer:02d}'
                dest.mkdir(parents=True)
                temp = output / 'compiler' / candidate / f'layer{layer:02d}'
                temp.mkdir(parents=True)
                cmd = [gcc, f'-DQINGYU_TEST_LAYER={layer}', *['-D' + d for d in DEFINES],
                       '-march=rv32imac', '-misa-spec=2.2', '-mabi=ilp32', '-ffreestanding',
                       '-fno-builtin', '-msmall-data-limit=0', '-ffunction-sections', '-fdata-sections',
                       '-Wall', '-Wextra', '-Werror', '-nostdlib', '-nostartfiles', '-O3', '-flto',
                       '-funroll-loops', '-I' + str(rtl), '-T' + str(bundle/'common/sw/linker.ld'),
                       '-Wl,--gc-sections', bundle/'common/sw/startup.S', rtl/'soc_perf_main.c',
                       rtl/'qingyu_accel.c', bundle/'common/sw/runtime.c', '-lgcc', '-o', temp/'fw.elf']
                with (temp / 'compile.log').open('w') as log:
                    subprocess.run(list(map(str, cmd)), check=True, stdout=log, stderr=subprocess.STDOUT)
                subprocess.run([objcopy, '-O', 'binary', str(temp/'fw.elf'), str(temp/'fw.bin')], check=True)
                raw = (temp / 'fw.bin').read_bytes()
                if len(raw) > 65536:
                    raise ValueError('Firmware exceeds ITCM')
                raw = raw.ljust(65536, b'\0')
                write(dest / 'firmware64.hex', ''.join(f'{int.from_bytes(raw[i:i+8], "little"):016x}\n' for i in range(0,65536,8)))
                write(dest / 'compile_command.json', json.dumps(list(map(str, cmd)), indent=2))
    for candidate, run_dir in firmware_runs.items():
        report = json.loads((run_dir / 'result.json').read_text())
        if report.get('passed') is not True or report.get('candidate') != candidate:
            raise ValueError('Firmware run did not pass for candidate: ' + str(run_dir))
        rows = report.get('layers', [])
        if sorted(r['layer'] for r in rows) != list(range(12)):
            raise ValueError('Firmware reuse requires all 12 layers')
        rtl = ROOT / 'experiments/h1500v' / candidate / 'rtl'
        for name, expected in report['firmware_sha256'].items():
            if sha(rtl / name) != expected:
                raise ValueError('Firmware source changed since passing run: ' + name)
        for name, expected in report['sources_sha256'].items():
            if name.startswith('experiments/h1500v/' + candidate + '/') and sha(ROOT / name) != expected:
                raise ValueError('Candidate RTL changed since passing run: ' + name)
        for row in rows:
            name = f"layer{row['layer']:02d}"
            firmware = run_dir / name / 'firmware64.hex'
            if sha(firmware) != row['input_sha256']['firmware64.hex']:
                raise ValueError('Tested firmware hash mismatch: ' + str(firmware))
            check_hex(firmware, 16, 8192)
            copy(firmware, bundle / 'firmware' / candidate / name / 'firmware64.hex')
            if args.images:
                for data_name in ('shared.hex', 'expected.hex'):
                    if sha(bundle / 'images' / name / data_name) != row['input_sha256'][data_name]:
                        raise ValueError('Bundle images differ from tested firmware run: ' + candidate + '/' + name)
        write(bundle / 'firmware' / candidate / 'tested_run_summary.json', json.dumps(report, indent=2))
    readme = (Path(__file__).parent / 'server_bundle/SERVER_README.md').read_text(encoding='utf-8')
    write(bundle / 'SERVER_README.md', readme)
    for path in sorted(bundle.rglob('*')):
        if path.is_file():
            manifest['files_sha256'][path.relative_to(bundle).as_posix()] = sha(path)
    write(bundle / 'manifest.json', json.dumps(manifest, indent=2, ensure_ascii=False))
    archive = output / 'qingyu_server_bundle.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                info = zipfile.ZipInfo('qingyu_server_bundle/' + path.relative_to(bundle).as_posix(), (2026, 1, 1, 0, 0, 0))
                info.external_attr = 0o644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, path.read_bytes())
    write(output / 'qingyu_server_bundle.zip.sha256', sha(archive) + '  qingyu_server_bundle.zip\n')
    print(archive)
    print('sha256=' + sha(archive))
    print('images_included=' + str(bool(args.images)) + ' all_candidates_have_firmware=' +
          str(all(c['firmware_included'] for c in manifest['candidates'].values())))


if __name__ == '__main__':
    main()
