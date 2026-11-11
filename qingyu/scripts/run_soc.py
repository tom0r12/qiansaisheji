"""Build real RV32 firmware and exercise the augmented official E203 SoC."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GCC_DEFAULT = r'C:\Efinity\efinity-riscv-ide-2025.1\toolchain\bin\riscv-none-embed-gcc.exe'

def run(command, name, timeout=300):
    log = ROOT / 'build' / f'{name}.log'
    start = time.monotonic()
    try:
        with log.open('w', encoding='utf-8') as stream:
            process = subprocess.run([str(x) for x in command], cwd=ROOT,
                                     stdout=stream, stderr=subprocess.STDOUT,
                                     timeout=timeout)
    except subprocess.TimeoutExpired:
        (ROOT/'reports'/f'{name}_timeout.json').write_text(json.dumps({
            'status':'timed_out','passed':None,'timeout_seconds':timeout,
            'log':str(log.relative_to(ROOT)),
            'note':'Runtime limit reached; this is not an arithmetic mismatch or a passing result.'
        },indent=2),encoding='utf-8')
        print(f'{name}: runtime limit {timeout}s reached; see {log}',flush=True)
        raise SystemExit(124) from None
    print(f'{name}: exit={process.returncode}, seconds={time.monotonic()-start:.1f}, log={log}', flush=True)
    if process.returncode:
        print(log.read_text(encoding='utf-8',errors='replace')[-6000:])
        raise SystemExit(process.returncode)
    return log

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gcc',default=os.environ.get('RISCV_GCC',GCC_DEFAULT))
    parser.add_argument('--layer',type=int,default=0)
    parser.add_argument('--vectors',default='tb/vectors',
                        help='Root containing layerNN/integer_case.npz and y_row_words.hex')
    parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--prepare-only',action='store_true',help='Generate firmware/images/file list without compiling a simulator')
    parser.add_argument('--block-copy',action='store_true')
    parser.add_argument('--read-ahead',action='store_true')
    parser.add_argument('--double-buffer',action='store_true')
    parser.add_argument('--fast-task', action='store_true')
    parser.add_argument('--performance-staging',action='store_true',help='CPU copies cold task data from a staging region through the real bus')
    parser.add_argument('--timeout',type=int,default=900)
    args=parser.parse_args()
    if args.block_copy: args.read_ahead=True
    if args.read_ahead: args.double_buffer=True
    if args.double_buffer: args.fast_task=True
    build=ROOT/'build'; build.mkdir(exist_ok=True)
    if not Path(args.gcc).is_file():
        raise SystemExit('Set RISCV_GCC or --gcc to an RV32-compatible GCC.')
    run([sys.executable,ROOT/'scripts/prepare_soc.py'],'prepare_soc')
    objcopy=str(args.gcc).replace('gcc.exe','objcopy.exe') if str(args.gcc).endswith('.exe') else str(args.gcc).removesuffix('gcc')+'objcopy'
    common=[args.gcc,f'-DQINGYU_TEST_LAYER={args.layer}',
            '-march=rv32imac','-mabi=ilp32','-Os','-g','-ffreestanding',
            '-fno-builtin','-msmall-data-limit=0','-ffunction-sections','-fdata-sections',
            '-Wall','-Wextra','-Werror','-nostdlib','-nostartfiles','-Isw']
    if args.block_copy: common.append('-DQINGYU_BLOCK_COPY')
    if args.read_ahead: common.append('-DQINGYU_READ_AHEAD')
    if args.double_buffer: common.append('-DQINGYU_DOUBLE_BUFFER')
    if args.fast_task:
        common += ['-DQINGYU_FAST_TASK', '-O3', '-flto', '-funroll-loops']
    run(common+['-Tsw/linker.ld','-Wl,--gc-sections,-Map,build/firmware.map',
        'sw/startup.S',('sw/soc_perf_main.c' if args.performance_staging else 'sw/soc_test_main.c'),'sw/qingyu_accel.c','sw/runtime.c',
        '-lgcc','-o','build/firmware.elf'],'build_firmware')
    run([objcopy,'-O','binary','build/firmware.elf','build/firmware.bin'],'objcopy')
    data=(build/'firmware.bin').read_bytes()
    if len(data)>65536: raise ValueError('Firmware exceeds ITCM')
    data=data.ljust(65536,b'\0')
    (build/'firmware64.hex').write_text(''.join(f'{int.from_bytes(data[i:i+8],"little"):016x}\n' for i in range(0,len(data),8)))
    vector_root=(ROOT/args.vectors).resolve()
    case=vector_root/f'layer{args.layer:02d}/integer_case.npz'
    with np.load(case,allow_pickle=False) as values:
        shared=bytearray(512*1024)
        def store(offset,value,dtype):
            payload=np.asarray(value,dtype=dtype).tobytes(order='C')
            shared[offset:offset+len(payload)]=payload
        store(0,values['qx'],'<i2'); store(0x4000,values['qw'],'<i2')
        store(0xc000,values['qb'],'<i8'); store(0xc800,values['shifts'],'u1')
        if args.performance_staging:
            shared[0x40000:0x50000] = shared[:0x10000]
            shared[:0x10000] = bytes(0x10000)
    (build/'shared.hex').write_text(''.join(f'{int.from_bytes(shared[i:i+4],"little"):08x}\n' for i in range(0,len(shared),4)))
    vendor=ROOT/'vendor/e203_hbirdv2/rtl/e203'
    # Upstream DFF simulation models contain #1 delays without a timescale.
    # A directive must precede every source, otherwise Icarus defaults to seconds.
    timescale=build/'timescale.v'
    timescale.write_text('`timescale 1ns/1ps\n',encoding='ascii')
    files=[timescale]+sorted(vendor.rglob('*.v'))
    files+=sorted((ROOT/'generated').glob('*.v'))
    files+=sorted((ROOT/'rtl').glob('*.sv'))
    files+=[ROOT/'tb/tb_qingyu_soc.sv']
    filelist=build/'soc_files.f'
    filelist.write_text('\n'.join(p.relative_to(ROOT).as_posix() for p in files)+'\n')
    if args.prepare_only: return
    iverilog=shutil.which('iverilog'); vvp=shutil.which('vvp')
    if not iverilog or not vvp: raise SystemExit('iverilog and vvp are required')
    command=[iverilog,'-g2012','-DDISABLE_SV_ASSERTION=1',*(['-DQINGYU_BLOCK_COPY'] if args.block_copy else []),*(['-DQINGYU_READ_AHEAD'] if args.read_ahead else []),*(['-DQINGYU_DOUBLE_BUFFER'] if args.double_buffer else []),*(['-DQINGYU_FAST_TASK'] if args.fast_task else []),'-s','tb_qingyu_soc',
             '-I',vendor/'core','-I',vendor/'perips','-I',vendor/'perips/apb_i2c',
             '-o',build/'soc.vvp','-c',filelist]
    run(command,'compile_soc')
    if args.build_only: return
    log=run([vvp,'-i',build/'soc.vvp','+FIRMWARE=build/firmware64.hex',
         '+SHARED=build/shared.hex',
         '+EXPECTED='+str(vector_root/f'layer{args.layer:02d}/y_row_words.hex').replace('\\','/')],
         'run_soc',timeout=args.timeout)
    text=log.read_text(encoding='utf-8',errors='replace')
    if 'PASS real E203' not in text: raise SystemExit('No SoC PASS marker')
    report={'test':'full E203 SoC firmware integration','layer':args.layer,
            'vector_root':str(vector_root),
            'data_kind':'See vector source manifest; this is a functional integration test',
            'outputs_checked':99*256,
            'passed':True,'log':str(log.relative_to(ROOT)),
            'limits':['not real KWT accuracy','not official evaluation harness',
                      'functional SRAM models','no formal timing/power result']}
    (ROOT/'reports/soc_result.json').write_text(json.dumps(report,indent=2))
    print(text[-2000:])

if __name__=='__main__': main()
