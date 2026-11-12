"""Conditional real-loader-write packet integration through the unchanged official memory fabric.

Run with Python in WSL. A bounded same-clock model occupies the existing CPU-side
merger port. Initial writes are real and measured, but this is not an actual
E203 CPU or an identified official platform loader.
"""
from __future__ import annotations
import argparse,hashlib,json,re,shutil,subprocess,tempfile
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_freeze(directory):
 path=directory/'SOURCE_SHA256.json';m=json.loads(path.read_text())
 for name,h in m['files'].items():
  f=(directory/name).resolve()
  if not f.is_relative_to(directory.resolve()) or sha(f)!=h:raise ValueError('Frozen dependency differs: '+str(f))
 for name,h in m.get('external_dependencies',{}).items():
  if sha(ROOT/name)!=h:raise ValueError('Frozen external dependency differs: '+name)
 return path
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--images',type=Path,default=ROOT/'build/int8_packet_corpus_20261112/sample009')
 p.add_argument('--layers',type=int,default=12)
 p.add_argument('--core-dir',type=Path,default=ROOT/'experiments/arithmetic/winograd_task8_prefetch')
 p.add_argument('--jobs',type=int,default=2)
 p.add_argument('--fault-checks',action='store_true',help='Add producer error, delayed ACK, random stalls, restart and coordinated reset checks on the first layer')
 p.add_argument('--seed',type=int,default=3719)
 p.add_argument('--reuse-build',type=Path)
 a=p.parse_args()
 if not 1<=a.layers<=12 or not 1<=a.jobs<=2:p.error('layers 1..12 and jobs 1..2 required')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 out=ROOT/'build/streaming_loader_study'/stamp;out.mkdir(parents=True)
 images=a.images.resolve();core=a.core_dir.resolve()
 packet_result=images/'result.json';packets=json.loads(packet_result.read_text())
 if not packets.get('passed') or sorted(r['layer'] for r in packets['layers'])!=list(range(12)):raise ValueError('Need all twelve independently validated real packets')
 rows={r['layer']:r for r in packets['layers']}
 packet_hashes={packet_result.relative_to(ROOT).as_posix():sha(packet_result)}
 for layer,row in rows.items():
  base=images/f'layer{layer:02d}';manifest=json.loads((base/'manifest.json').read_text())
  if manifest!=row:raise ValueError('Layer/result manifest differs')
  if row['output_allocation_words']!=6385 or not 202<row['input_words']<=5905:raise ValueError('Unsupported packet dimensions')
  packet_hashes[(base/'manifest.json').relative_to(ROOT).as_posix()]=sha(base/'manifest.json')
  for name,h in row['files_sha256'].items():
   if sha(base/name)!=h:raise ValueError('Packet file differs')
   packet_hashes[(base/name).relative_to(ROOT).as_posix()]=h
 freezes=[verify_freeze(ROOT/d) for d in ['experiments/codec/rice32_bounded','experiments/transport/rowpair_pack','experiments/transport/icb_stream_prefix','experiments/h1500v/opt33_readcache']]
 freezes.append(verify_freeze(core))
 if sha(ROOT/'experiments/codec/rice32/SOURCE_SHA256.json')!=packets['codec_source_manifest_sha256']:raise ValueError('Packet codec identity differs')
 vendor=ROOT/'vendor/e203_hbirdv2';inventory=ROOT/'reports/e203-source-manifest.json';pinned=json.loads(inventory.read_text())
 if not pinned['ready'] or pinned['commit']!='9f3e34f337f5d0a1236a285871ffa2032491617a':raise ValueError('Unvalidated official vendor')
 vendor_files=[];headers=[]
 for f in sorted((vendor/'rtl').rglob('*')):
  if f.is_file() and f.suffix in ['.v','.sv','.vh','.svh']:
   entry=pinned['files'][f.relative_to(vendor).as_posix()]
   if not entry['matches_commit'] or sha(f)!=entry['sha256']:raise ValueError('Original fabric/vendor changed')
   (vendor_files if f.suffix in ['.v','.sv'] else headers).append(f)
 rtl=[HERE/'engine/qingyu_int8stream_engine.sv',ROOT/'experiments/transport/icb_stream_prefix/qingyu_icb_stream_prefix.sv',
      ROOT/'experiments/codec/rice32_bounded/rice32_decoder.sv',ROOT/'experiments/codec/rice32_bounded/rice32_encoder.sv',
      ROOT/'experiments/transport/rowpair_pack/rowpair_pack.sv',core/'winograd_int8_task8.sv',
      ROOT/'experiments/arithmetic/winograd_array8/winograd_int8_pair_acc32.sv',ROOT/'rtl/qingyu_sram16.sv',
      ROOT/'experiments/h1500v/opt33_readcache/rtl/qingyu_shared_sram.sv']
 rtl.append(ROOT/'experiments/h1500v/opt33_readcache/rtl/qingyu_icb_merge.sv')
 tb=HERE/'test/tb_streaming_loader.sv';compiled=vendor_files+headers+rtl+[tb]
 before={f.relative_to(ROOT).as_posix():sha(f) for f in compiled}
 tracked={f.relative_to(ROOT).as_posix():sha(f) for f in freezes+[Path(__file__),HERE/'contract.json']}
 r=dict(schema='qingyu-conditional-streaming-loader-checks-v1',passed=False,created_utc=stamp,compiled_source_sha256=before,source_sha256=tracked,
        packet_sha256=packet_hashes,vendor_commit=pinned['commit'],vendor_manifest_sha256=sha(inventory),
        core_directory=core.relative_to(ROOT).as_posix(),data_kind='real KWT quantized x8_w8_y8_h0 serialized packets',
        measurement=dict(start='first real producer write offer; also first accept and originating ACK',end='final originating magic-write response handshake',first_read_also_reported=True,
                         excluded='actual E203 and official-loader implementation overhead; source initialization is not preloaded'),
        limitations=['No PPA/STA or manufacturer SRAM proof','Conditional same-clock producer, not actual CPU or official loader','Official loader start remains unresolved'],commands=[],layers=[])
 def save():(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 def run(cmd,log,cwd=ROOT,timeout=900):
  r['commands'].append(dict(argv=list(map(str,cmd)),cwd=str(cwd),log=log.relative_to(out).as_posix()));save()
  with log.open('w') as f:proc=subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
  if proc.returncode:raise RuntimeError('Failed; see '+str(log))
  return log.read_text(errors='replace')
 def check_unchanged():
  for name,h in {**before,**tracked,**packet_hashes}.items():
   if sha(ROOT/name)!=h:raise ValueError('Input changed during verification: '+name)
 try:
  version=subprocess.run(['verilator','--version'],capture_output=True,text=True,check=True).stdout.strip();r['verilator_version']=version
  includes=['-I'+str(vendor/'rtl/e203'/d) for d in ['core','perips','perips/apb_i2c']]
  options=['--binary','--timing','--autoflush','--timescale-override','1ns/1ps','--top-module','tb_streaming_loader','--prefix','Vloader',
           '-Wno-fatal','-DDISABLE_SV_ASSERTION=1','-j',str(a.jobs),'-CFLAGS','-O1']
  signature=dict(tool=version,options=options,includes=[str(Path(x[2:]).relative_to(ROOT)) for x in includes],
                 sources=[f.relative_to(ROOT).as_posix() for f in vendor_files+rtl+[tb]],source_hashes=before,mdir='<BUILD_DIRECTORY>')
  r['build_fingerprint']=hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest();r['build_signature']=signature
  binary=out/'simv'
  if a.reuse_build:
   old=a.reuse_build.resolve();oldresult=old/'result.json';prior=json.loads(oldresult.read_text())
   if not prior['passed'] or prior['build_fingerprint']!=r['build_fingerprint'] or sha(old/'simv')!=prior['binary_sha256']:raise ValueError('Reuse build/source/options/binary mismatch')
   shutil.copy2(old/'simv',binary);r['reused_build']=dict(result=oldresult.relative_to(ROOT).as_posix(),result_sha256=sha(oldresult))
  else:
   build=Path(tempfile.mkdtemp(prefix='qingyu_loader_build_'));r['build_directory']=str(build)
   run(['verilator',*options,'--Mdir',str(build),*includes,*map(str,vendor_files+rtl+[tb])],out/'compile.log')
   check_unchanged();shutil.copy2(build/'Vloader',binary)
  r['binary_sha256']=sha(binary);save()
  for layer in range(12):
   dst=out/f'layer{layer:02d}';dst.mkdir()
   for name in ['input.hex','expected_output.hex','manifest.json']:shutil.copyfile(images/f'layer{layer:02d}'/name,dst/name)
  for layer in range(a.layers):
   next_layer=(layer+1)%12;row=rows[layer];nxt=rows[next_layer];base=out/f'layer{layer:02d}'
   cmd=[str(binary),'+INPUT=input.hex','+EXPECTED=expected_output.hex',f'+NEXT_INPUT=../layer{next_layer:02d}/input.hex',f'+NEXT_EXPECTED=../layer{next_layer:02d}/expected_output.hex',
        f'+INPUT_WORDS={row["input_words"]}',f'+OUTPUT_WORDS={row["output_written_words"]}',f'+NEXT_INPUT_WORDS={nxt["input_words"]}',f'+NEXT_OUTPUT_WORDS={nxt["output_written_words"]}',
        f'+FAULT_CHECKS={int(a.fault_checks and layer==0)}',f'+SEED={a.seed}',f'+verilator+seed+{a.seed}']
   text=run(cmd,out/f'layer{layer:02d}.log',cwd=base,timeout=180)
   passes=re.findall(r'^PASS conditional_loader (.*)$',text,re.M)
   if len(passes)!=1:raise ValueError('No unique complete integration PASS')
   summary={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',passes[0])}
   cases=[{k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)} for line in text.splitlines() if line.startswith('LOADER_CASE ')]
   if len(cases)!=(15 if a.fault_checks and layer==0 else 4):raise ValueError('Incomplete normal/recovery cases')
   primary=cases[0];secondary=cases[1]
   if [c['serial'] for c in cases[:4]]!=[0,0,1,1]:raise ValueError('Serial/streaming control cases incomplete')
   if any(c['offer_to_final']<c['commands'] for c in cases[:4]):raise ValueError('Initial-load window violates single-bus service floor')
   if any(c['mode'] or c['error'] for c in [primary,secondary]):raise ValueError('Primary task failed')
   dumps={}
   for case in cases:
    if case['mode']<=2:
     dump=base/f'case{case["id"]}_output.hex'
     words=[int(w,16) for w in re.sub(r'//[^\n]*','',dump.read_text()).split()]
     expected_words=[int(w,16) for w in (images/f'layer{next_layer if case["next"] else layer:02d}'/'expected_output.hex').read_text().split()]
     if words!=expected_words:raise ValueError('Retained output artifact differs')
     dumps[dump.name]=sha(dump)
   r['layers'].append(dict(layer=layer,next_layer=next_layer,passed=True,summary=summary,primary=primary,back_to_back=secondary,cases=cases,serial=cases[2],serial_back_to_back=cases[3],
                           log_sha256=sha(out/f'layer{layer:02d}.log'),output_dumps_sha256=dumps));save()
   print(f'PASS layer={layer} cycles={primary["offer_to_final"]} next={next_layer} cycles={secondary["offer_to_final"]}',flush=True)
  check_unchanged()
  if sha(binary)!=r['binary_sha256']:raise ValueError('Binary changed')
  r['passed']=True
 except Exception as e:r['failure']=str(e);raise
 finally:save();print(out/'result.json',flush=True)
if __name__=='__main__':main()

