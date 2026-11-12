"""Additional explicit canonical ties and all256 byte values, immutable quick binary."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,importlib.util,json,shutil,subprocess,re
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,required=True);a=p.parse_args();base=a.base.resolve()
 result=json.loads((base/'result.json').read_text());assert result['passed'] and result['simulator']=='iverilog'
 for name,h in result['source_sha256_before'].items():assert sha(HERE/name)==h
 out=HERE/'runs'/('boundary_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir(parents=True)
 cases=json.loads((base/'cases.json').read_text())
 for c in cases:
  for key in ['raw','coded']:
   assert sha(base/c[key])==c[key+'_sha256'];shutil.copy2(base/c[key],out/c[key])
 writer=load('original_fixed_boundary_writer',ROOT/'experiments/codec/rice32/run_checks.py')
 parser=load('frozen_packet_boundary_parser',ROOT/'model/export_int8_packets.py')
 def add(data,k,delta,row,tag,mode,bits=None):
  i=len(cases);raw=out/f'case{i:04d}.raw.hex';coded=out/f'case{i:04d}.bits.hex';data=np.asarray(data,dtype=np.uint8)
  wire=writer.encode_bytes(data,k,delta) if bits is None else bits
  padded=data.tobytes()+bytes((-data.size)%4)
  raw.write_text(''.join(f'{int.from_bytes(padded[q:q+4],"little"):08x}\n' for q in range(0,len(padded),4)))
  coded.write_text(''.join(f'{v:08x}\n' for v in parser.bits_words(wire)))
  cases.append(dict(id=i,mode=mode,symbols=data.size,k=k,delta=int(delta),row=row,bits=len(wire),declared=len(wire),raw=raw.name,coded=coded.name,tag=tag,raw_sha256=sha(raw),coded_sha256=sha(coded)))
 for k,tie_value in [(2,10),(3,16),(5,32)]:
  data=np.full((1,32),tie_value,dtype=np.uint8);mode=3 if k==3 else 2
  assert writer.encode_bytes(data,k,False)=='1'+f'{tie_value:08b}'*32
  add(data,k,False,16,f'exact_raw_tie_k{k}',mode)
  if k!=3:
   u=2*tie_value;forced='0'+('1'*(u>>k)+'0'+f'{u&((1<<k)-1):0{k}b}')*32
   assert len(forced)==257
   add(data,k,False,16,f'reject_forced_rice_tie_k{k}',1,forced)
  data=np.arange(256,dtype=np.uint8).reshape(16,16)
  for delta in [False,True]:add(data,k,delta,16,f'every_byte_k{k}_delta{int(delta)}',mode)
 (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 (out/'manifest.txt').write_text(''.join(f"{c['id']} {c['mode']} {c['symbols']} {c['k']} {c['delta']} {c['row']} {c['bits']} {c['declared']} {c['raw']} {c['coded']}\n" for c in cases))
 report=dict(schema='qingyu-fixed-codec-boundaries-v1',passed=False,base_result_sha256=sha(base/'result.json'),source_sha256=result['source_sha256_before'],script_sha256=sha(Path(__file__)),cases_sha256=sha(out/'cases.json'),runs=[])
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 save()
 try:
  for variant in ['fixed','bounded_reference']:
   binary=base/(variant+'.vvp');report.setdefault('binary_sha256',{})[variant]=sha(binary)
   for seed in [41,419,20261112]:
    log=out/f'{variant}_seed{seed}.log'
    with log.open('w') as f:q=subprocess.run(['vvp',str(binary),'+MANIFEST=manifest.txt',f'+SEED={seed}'],cwd=out,stdout=f,stderr=subprocess.STDOUT,timeout=180)
    text=log.read_text();ok=q.returncode==0 and 'PASS rice32_fixed400' in text
    report['runs'].append(dict(variant=variant,seed=seed,passed=ok,log_sha256=sha(log),tail=text[-500:]));save();print(variant,seed,'PASS' if ok else 'FAIL',flush=True)
    if not ok:raise RuntimeError(text[-2000:])
  for name,h in result['source_sha256_before'].items():assert sha(HERE/name)==h
  report['passed']=True
 finally:save();print(out/'result.json',flush=True)
if __name__=='__main__':main()
