"""MMIO protocol checks with the real INT8 engine and an ordered test RAM endpoint.

This is not an E203/original-fabric throughput run. No fake engine is used.
"""
from __future__ import annotations
import argparse,hashlib,json,re,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--seeds',type=int,nargs='+',default=[17,271,20261112])
 p.add_argument('--short-only',action='store_true')
 a=p.parse_args();out=ROOT/'build/int8stream_mmio'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
 core=ROOT/'experiments/arithmetic/winograd_task8'
 rtl=[HERE/'qingyu_int8stream_fio.sv',ROOT/'experiments/integration/int8stream/qingyu_int8stream_engine.sv',
      ROOT/'experiments/transport/icb_stream_prefix/qingyu_icb_stream_prefix.sv',
      ROOT/'experiments/codec/rice32/rice32_decoder.sv',ROOT/'experiments/codec/rice32/rice32_encoder.sv',
      ROOT/'experiments/transport/rowpair_pack/rowpair_pack.sv',core/'winograd_int8_task8.sv',
      ROOT/'experiments/arithmetic/winograd_array8/winograd_int8_pair_acc32.sv',ROOT/'rtl/qingyu_sram16.sv',HERE/'tb_int8stream_fio.sv']
 packet=ROOT/'build/int8_packets_20261112/layer00';row=json.loads((packet/'manifest.json').read_text())
 for name,h in row['files_sha256'].items():assert sha(packet/name)==h
 for name in ['input.hex','expected_output.hex']:shutil.copyfile(packet/name,out/name)
 files=rtl+[Path(__file__),HERE/'contract.json',packet/'manifest.json',packet/'input.hex',packet/'expected_output.hex']
 before={f.relative_to(ROOT).as_posix():sha(f) for f in files}
 result=out/'result.json';report=dict(schema='qingyu-int8stream-mmio-v1',passed=False,source_sha256_before=before,
  limitations=['Actual engine but synthetic ordered single-clock RAM endpoint; no original-fabric or CPU performance claim',
   'Layer00 validation sample9 generated silence only for complete successful task checks','No PPA or STA'],runs=[])
 def save():result.write_text(json.dumps(report,indent=2)+'\n')
 save()
 try:
  for short in ([True] if a.short_only else [True,False]):
   name='short' if short else 'normal';exe=out/(name+'.vvp');deadline=96 if short else 200000
   cmd=['iverilog','-g2012','-Wall','-s','tb_int8stream_fio',f'-Ptb_int8stream_fio.TIMEOUT_CYCLES={deadline}','-o',str(exe),*map(str,rtl)]
   with (out/(name+'_compile.log')).open('w') as log:proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=120)
   if proc.returncode:raise RuntimeError('Compile failed: '+name)
   for seed in (a.seeds if short else a.seeds[:1]):
    logfile=out/f'{name}_seed{seed}.log'
    command=['vvp',str(exe),f'+SHORT={int(short)}',f'+SEED={seed}','+INPUT=input.hex','+EXPECTED=expected_output.hex',f'+INPUT_WORDS={row["input_words"]}',f'+WRITTEN_WORDS={row["output_written_words"]}']
    with logfile.open('w') as log:run=subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=600)
    text=logfile.read_text();passes=re.findall(r'^PASS int8stream_fio (.*)$',text,re.M)
    ok=run.returncode==0 and len(passes)==1
    report['runs'].append(dict(short=short,seed=seed,passed=ok,log=logfile.name,log_sha256=sha(logfile),
     summary={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',passes[0])} if passes else {},
     normal=[{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',s)} for s in text.splitlines() if s.startswith('MMIO_NORMAL ')]));save()
    print('RUN',name,seed,'PASS' if ok else 'FAIL',flush=True)
    if not ok:raise RuntimeError(text[-4000:])
  report['source_sha256_after']={f.relative_to(ROOT).as_posix():sha(f) for f in files}
  if report['source_sha256_after']!=before:raise RuntimeError('Source changed during verification; rerun from stable sources')
  report['passed']=True
 except Exception as e:report['failure']=str(e);raise
 finally:save();print(result,flush=True)
if __name__=='__main__':main()
