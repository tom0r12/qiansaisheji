"""Reproducible local model/driver/RTL checks. Full vectors are synthetic."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--full-rtl',action='store_true')
    parser.add_argument('--layer',type=int,default=0)
    args=parser.parse_args()
    build=ROOT/'build'; build.mkdir(exist_ok=True)
    records=[]
    def run(name,command,timeout=120):
        start=time.monotonic()
        process=subprocess.run([str(x) for x in command],cwd=ROOT,
              text=True,encoding='utf-8',errors='replace',stdout=subprocess.PIPE,
              stderr=subprocess.STDOUT,timeout=timeout)
        (build/f'{name}.log').write_text(process.stdout,encoding='utf-8')
        record={'name':name,'passed':process.returncode==0,
                'seconds':round(time.monotonic()-start,3),
                'log':f'build/{name}.log'}
        records.append(record)
        print(f'{name}: {"PASS" if record["passed"] else "FAIL"}',flush=True)
        if not record['passed']:
            print(process.stdout[-5000:]); raise SystemExit(process.returncode)
    try:
        run('numeric_unit_tests',[sys.executable,'-m','unittest','model.test_reference','-v'])
        gcc=shutil.which('gcc')
        if not gcc: raise SystemExit('Host gcc required for driver regression')
        run('driver_compile',[gcc,'-std=c99','-Wall','-Wextra','-Werror','-pedantic',
            '-Isw','tb/test_driver.c','sw/qingyu_accel.c','-o','build/driver_test.exe'])
        run('driver_test',[build/'driver_test.exe'])
        iv=shutil.which('iverilog'); vv=shutil.which('vvp')
        if not iv or not vv: raise SystemExit('Icarus Verilog required')
        command=[iv,'-g2012','-s','tb_qingyu_accel','-o','build/accel_test.vvp']
        if not args.full_rtl:
            command+=['-Ptb_qingyu_accel.ROWS=2','-Ptb_qingyu_accel.K=4']
        command+=['rtl/qingyu_sram16.sv','rtl/qingyu_accel.sv','tb/tb_qingyu_accel.sv']
        run('rtl_compile',command)
        command=[vv,'build/accel_test.vvp']
        if args.full_rtl: command+=[f'+VECTORS=tb/vectors/layer{args.layer:02d}']
        run('rtl_full' if args.full_rtl else 'rtl_quick',command,timeout=900)
        run('fio_compile',[iv,'-g2012','-s','tb_fio','-o','build/fio_test.vvp',
            'rtl/qingyu_sram16.sv','rtl/qingyu_accel.sv','rtl/qingyu_fio.sv','tb/tb_fio.sv'])
        run('fio_test',[vv,'build/fio_test.vvp'])
    finally:
        (ROOT/'reports/checks.json').write_text(json.dumps({
            'records':records,'full_rtl_requested':args.full_rtl,
            'layer':args.layer if args.full_rtl else None,
            'data_kind':'SYNTHETIC engineering vectors; no real KWT accuracy claim'
        },indent=2),encoding='utf-8')

if __name__=='__main__': main()
