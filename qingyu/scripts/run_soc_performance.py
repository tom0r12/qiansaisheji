"""Measure cold-task E203/ICB latency; numbers are engineering RTL results.

No power or official 150 MHz acceptance is inferred from these measurements.
--package builds a self-contained server VCS bundle for the selected layers.
"""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import sys
import zipfile

from run_soc_verilator import execute, sha256

ROOT = Path(__file__).resolve().parents[1]


def summarize(text, layer):
    if 'PASS real E203' not in text:
        raise ValueError('Independent output checker did not pass')
    matches = re.findall(r'QINGYU_PERF_WINDOW ([^\r\n]+)', text)
    if len(matches) != 1:
        raise ValueError('Expected exactly one complete timing window')
    fields = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', matches[0])}
    if fields['outputs'] != 25344 or fields['load_words'] != 11936 or fields['cycles'] <= 0:
        raise ValueError('Invalid transfer coverage or cycle count')
    if fields['cycles'] != fields['end_cycle'] - fields['start_cycle']:
        raise ValueError('Timing boundary mismatch')
    if fields['cycles'] != fields['start_to_live'] + fields['live_cycles']:
        raise ValueError('Phase boundary mismatch')
    start = re.search(r'QINGYU_PERF_START cycle=\d+ time_ps=(\d+)', text)
    end = re.search(r'QINGYU_PERF_END time_ps=(\d+)', text)
    if not start or not end:
        raise ValueError('Missing activity window boundaries')
    fields['activity_start_ps'] = int(start[1])
    fields['activity_end_ps'] = int(end[1])
    fields['simulated_clock_period_ps'] = (int(end[1])-int(start[1])) / fields['cycles']
    if abs(fields['simulated_clock_period_ps'] - 6666) > 1:
        raise ValueError('Unexpected measured bus clock period')
    waits = re.search(r'QINGYU_BATCH_WAIT full_wait=(\d+) cpu_wait=(\d+)', text)
    if waits:
        fields.update(full_wait_cycles=int(waits[1]), cpu_wait_cycles=int(waits[2]))
    fields.update(layer=layer, passed=True,
                  latency_ms_at_assumed_150mhz=fields['cycles'] / 150000,
                  serial_tasks_per_second_at_assumed_150mhz=150000000 / fields['cycles'],
                  effective_gmac_per_second_at_assumed_150mhz=(99*64*256)*0.15 / fields['cycles'])
    return fields


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pipe-mac',action='store_true')
    parser.add_argument('--block-copy',action='store_true')
    parser.add_argument('--read-ahead',action='store_true')
    parser.add_argument('--double-buffer',action='store_true')
    parser.add_argument('--fast-task', action='store_true')
    parser.add_argument('--layers', default='0', help='comma-separated layer IDs, or all')
    parser.add_argument('--vectors', default='model/full_v2_run/validation_vectors')
    parser.add_argument('--skip-build', action='store_true')
    parser.add_argument('--package', action='store_true', help='Prepare server bundle instead of running native simulation')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args()
    if args.block_copy: args.read_ahead=True
    if args.read_ahead: args.pipe_mac=True
    if args.pipe_mac: args.double_buffer=True
    if args.double_buffer: args.fast_task=True
    layers = list(range(12)) if args.layers == 'all' else [int(x) for x in args.layers.split(',')]
    if not layers or len(set(layers)) != len(layers) or any(x not in range(12) for x in layers):
        parser.error('layers must be distinct IDs from 0 through 11')
    from datetime import datetime
    tag = datetime.now().strftime('%Y%m%d_%H%M%S')
    run = ROOT / 'reports' / ('soc_performance_' + tag)
    run.mkdir(parents=True)
    build = ROOT / 'build'
    tools = ROOT / 'tools/verilator/mingw64'
    env = os.environ.copy()
    env['VERILATOR_ROOT'] = (tools / 'share/verilator').as_posix()
    env['PATH'] = str(tools / 'bin') + os.pathsep + r'D:\Git\usr\bin' + os.pathsep + env.get('PATH', '')
    report = dict(kind='ENGINEERING_COLD_TASK_RTL_PERFORMANCE', passed=False,
                  clock_hz_assumed=150000000, layers=[],
                  window='First E203 staging-source read request assertion to response acceptance of the last unique output word write',
                  source='Upper 64 KiB staging area of functional 512 KiB shared SRAM, supplied by testbench before reset',
                  task_load_bytes=47744, task_output_bytes=101376,
                  includes=['E203 CPU copy of all inputs/parameters into initially empty live buffers',
                            'driver validation, accelerator reset, CPU scheduling and polling',
                            'all ICB waits and all output write responses within the window'],
                  excludes=['power-on/reset/boot before loading', 'external host-to-staging transport before first CPU request'],
                  limitations=['not the official 12-task evaluation dataset or loader',
                               'shared SRAM is functional with one-cycle response, not the final macro implementation',
                               '150 MHz conversion conditional on complete SoC timing closure',
                               'serial isolated-task throughput, not overlapped task throughput',
                               'no whole-SoC power or energy measured'])
    if args.block_copy:
        report['window']='First E203 load-block command assertion to acceptance of the last shared SRAM output write response'
        report['includes'][0]='E203 issues 16-word transfer commands; every staging read, live write and output write uses the shared SRAM endpoint'
    report_path = run / 'summary.json'
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    sources = None
    for layer in layers:
        folder = run / f'layer{layer:02d}'
        folder.mkdir()
        execute([sys.executable, ROOT/'scripts/run_soc.py', '--prepare-only', '--performance-staging',
                 *(['--block-copy'] if args.block_copy else []),*(['--read-ahead'] if args.read_ahead else []), *(['--double-buffer'] if args.double_buffer else []), *(['--fast-task'] if args.fast_task else []), '--layer', str(layer), '--vectors', args.vectors], folder/'prepare.log', env, args.timeout)
        for name in ['firmware64.hex', 'shared.hex', 'firmware.elf']:
            shutil.copy2(build/name, folder/name)
        shutil.copy2(ROOT/args.vectors/f'layer{layer:02d}/y_row_words.hex', folder/'expected.hex')
        current = [ROOT/x for x in (build/'soc_files.f').read_text().splitlines() if x]
        current.append(ROOT/'tb/tb_qingyu_soc_performance.sv')
        if sources is not None and sources != current:
            raise RuntimeError('Source list changed between tasks')
        sources = current
    if args.fast_task:
        config = build/('block_config.v' if args.block_copy else 'ahead_config.v' if args.read_ahead else 'pipe_config.v' if args.pipe_mac else 'db_config.v' if args.double_buffer else 'fast_config.v')
        config.write_text('`define QINGYU_FAST_TASK\n'+('`define QINGYU_DOUBLE_BUFFER\n' if args.double_buffer else '')+('`define QINGYU_PIPE_MAC\n' if args.pipe_mac else '')+('`define QINGYU_READ_AHEAD\n' if args.read_ahead else '')+('`define QINGYU_BLOCK_COPY\n' if args.block_copy else ''))
        sources.insert(0, config)
    source_hashes = {p.relative_to(ROOT).as_posix():sha256(p) for p in sources}
    report['rtl_sha256'] = source_hashes
    report['software_sha256'] = {p.relative_to(ROOT).as_posix():sha256(p) for p in (ROOT/'sw').glob('*') if p.is_file()}
    if args.package:
        package_server(run, sources, layers, report)
        return
    model_dir = build/('verilator_block_performance' if args.block_copy else 'verilator_ahead_performance' if args.read_ahead else 'verilator_pipe_performance' if args.pipe_mac else 'verilator_db_performance' if args.double_buffer else 'verilator_fast_performance' if args.fast_task else 'verilator_soc_performance')
    model_dir.mkdir(exist_ok=True)
    # Keep runtime DLLs beside the executable; some Windows launch policies do
    # not honor PATH for dependent DLLs even when compiler discovery succeeds.
    for name in ('libstdc++-6.dll','libgcc_s_seh-1.dll','libwinpthread-1.dll'):
        shutil.copy2(tools/'bin'/name,model_dir/name)
    filelist = build/'soc_performance.f'
    filelist.write_text('\n'.join(p.relative_to(ROOT).as_posix() for p in sources)+'\n')
    model = 'Vqingyu_soc_performance'
    manifest = model_dir/'build_manifest.json'
    if args.skip_build:
        if json.loads(manifest.read_text())['rtl_sha256'] != source_hashes:
            raise RuntimeError('RTL/TB changed; omit --skip-build')
    else:
        generate = [tools/'bin/verilator_bin.exe', '--cc','--main','--exe','--timing','--autoflush',
                    '--timescale-override','1ns/1ps','--top-module','tb_qingyu_soc_performance',
                    '--prefix',model,'--Mdir',model_dir.relative_to(ROOT).as_posix(),'-Wno-fatal',
                    '-DDISABLE_SV_ASSERTION=1','-Ivendor/e203_hbirdv2/rtl/e203/core',
                    '-Ivendor/e203_hbirdv2/rtl/e203/perips','-Ivendor/e203_hbirdv2/rtl/e203/perips/apb_i2c',
                    '-CFLAGS','-std=gnu++20 -O1','--output-split','10000','-f',filelist]
        execute(generate, run/'generate.log', env, args.timeout)
        execute([r'D:\mingw\mingw64\bin\mingw32-make.exe','-C',model_dir,'-f',model+'.mk',
                 '-j',str(args.jobs),'CXX='+(tools/'bin/g++.exe').as_posix(),
                 'LINK='+(tools/'bin/g++.exe').as_posix(),'AR='+(tools/'bin/ar.exe').as_posix(),
                 'PYTHON3='+Path(sys.executable).as_posix(),'PERL=D:/Git/usr/bin/perl.exe',
                 'VERILATOR_ROOT='+env['VERILATOR_ROOT']],run/'make.log',env,args.timeout)
        manifest.write_text(json.dumps({'rtl_sha256':source_hashes},indent=2)+'\n')
    binary=model_dir/model
    if not binary.is_file(): binary=binary.with_suffix('.exe')
    for layer in layers:
        folder=run/f'layer{layer:02d}'
        hashes={name:sha256(folder/name) for name in ['firmware64.hex','shared.hex','expected.hex']}
        seconds=execute([binary,'+FIRMWARE='+(folder/'firmware64.hex').as_posix(),
                         '+SHARED='+(folder/'shared.hex').as_posix(),
                         '+EXPECTED='+(folder/'expected.hex').as_posix()],folder/'simulation.log',env,args.timeout)
        if hashes != {name:sha256(folder/name) for name in hashes}:
            raise RuntimeError('Task images changed during simulation')
        item=summarize((folder/'simulation.log').read_text(errors='replace'),layer)
        item.update(input_sha256=hashes, host_simulation_seconds=seconds)
        report['layers'].append(item)
        report_path.write_text(json.dumps(report,indent=2)+'\n')
        print(f"PERF layer={layer} cycles={item['cycles']} ms_at_150MHz={item['latency_ms_at_assumed_150mhz']:.6f}",flush=True)
    report['passed']=True
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    report['run_directory']=str(run)
    (ROOT/'reports'/('soc_block_performance_result.json' if args.block_copy else 'soc_ahead_performance_result.json' if args.read_ahead else 'soc_pipe_performance_result.json' if args.pipe_mac else 'soc_db_performance_result.json' if args.double_buffer else 'soc_fast_performance_result.json' if args.fast_task else 'soc_performance_result.json')).write_text(json.dumps(report,indent=2)+'\n')
    print('PERFORMANCE_REPORT: '+str(report_path),flush=True)


def package_server(run, sources, layers, report):
    """No server compiler/toolchain installation; firmware is already built."""
    bundle=run/'qingyu_soc_performance'
    bundle.mkdir(exist_ok=True)
    for path in sources:
        dst=bundle/path.relative_to(ROOT)
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,dst)
    (bundle/'sources.f').write_text('\n'.join(p.relative_to(ROOT).as_posix() for p in sources)+'\n', encoding='utf-8', newline='\n')
    for layer in layers:
        dst=bundle/f'layer{layer:02d}'
        dst.mkdir(exist_ok=True)
        for name in ['firmware64.hex','shared.hex','expected.hex']:
            shutil.copy2(run/f'layer{layer:02d}'/name,dst/name)
    report['status']='PREPARED_NOT_RUN'
    (bundle/'measurement_scope.json').write_text(json.dumps(report,indent=2)+'\n')
    (run/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    shell='''#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
run="$base/run_$(date +%Y%m%d_%H%M%S)_$$"
mkdir "$run"
cd "$base"
sha256sum -c inputs.sha256 > "$run/input_check.log"
echo "QINGYU_PERFORMANCE_DIRECTORY: $run"
vcs -full64 -sverilog +define+DISABLE_SV_ASSERTION=1 -timescale=1ns/1ps \\
 +incdir+vendor/e203_hbirdv2/rtl/e203/core+vendor/e203_hbirdv2/rtl/e203/perips+vendor/e203_hbirdv2/rtl/e203/perips/apb_i2c \\
 -top tb_qingyu_soc_performance -f sources.f -Mdir="$run/csrc" -o "$run/simv" > "$run/compile.log" 2>&1 || { tail -n 35 "$run/compile.log"; exit 1; }
for layer in LAYER_LIST; do
 echo "QINGYU_MEASURING: $layer"
 set --
 if [ "${QINGYU_ACTIVITY_LAYER:-}" = "$layer" ]; then
  set -- "+ACTIVITY=$run/$layer.vcd"
 fi
 "$run/simv" +FIRMWARE="$base/$layer/firmware64.hex" +SHARED="$base/$layer/shared.hex" +EXPECTED="$base/$layer/expected.hex" "$@" > "$run/$layer.log" 2>&1 || { tail -n 25 "$run/$layer.log"; exit 1; }
 grep -q 'PASS real E203' "$run/$layer.log"
 grep -q 'QINGYU_PERF_WINDOW' "$run/$layer.log"
 grep -E 'QINGYU_PERF_WINDOW|QINGYU_PERF_FIRMWARE|PASS real E203' "$run/$layer.log"
done
sha256sum -c inputs.sha256 > "$run/input_recheck.log"
echo "QINGYU_PERFORMANCE_COMPLETE: $run"
echo "Engineering cycles only; full SoC timing/power and official input qualification remain pending."
'''.replace('LAYER_LIST',' '.join(f'layer{x:02d}' for x in layers))
    (bundle/'run.sh').write_text(shell,encoding='ascii',newline='\n')
    shutil.copy2(ROOT/'docs/soc_performance.md',bundle/'README.md')
    (bundle/'inputs.sha256').write_text(''.join(sha256(p)+'  '+p.relative_to(bundle).as_posix()+'\n'
        for p in sorted(bundle.rglob('*')) if p.is_file() and p.name!='inputs.sha256'), encoding='utf-8', newline='\n')
    destination=ROOT.parent/'output/eda'/('qingyu_block_performance.zip' if any(p.name=='block_config.v' for p in sources) else 'qingyu_ahead_performance.zip' if any(p.name=='ahead_config.v' for p in sources) else 'qingyu_pipe_performance.zip' if any(p.name=='pipe_config.v' for p in sources) else 'qingyu_db_performance.zip' if any(p.name=='db_config.v' for p in sources) else 'qingyu_fast_performance.zip' if any(p.name=='fast_config.v' for p in sources) else 'qingyu_soc_performance.zip')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
        for p in bundle.rglob('*'):
            if p.is_file(): archive.write(p,p.relative_to(run))
    print('SERVER_PACKAGE: '+str(destination),flush=True)


if __name__=='__main__': main()
