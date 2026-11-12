"""Fixed-format narrow codec, independent wire goldens, immutable72task packets and bounded baseline."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,re,shutil,subprocess,tempfile
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ORIGINAL=ROOT/'experiments/codec/rice32'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def words(path,values):path.write_text(''.join(f'{int(w):08x}\n' for w in values))
def raw_words(data):
 data=bytes(data);data+=bytes((-len(data))%4)
 return [int.from_bytes(data[i:i+4],'little') for i in range(0,len(data),4)]
def bit_string(values,n):return ''.join(f'{b:08b}' for w in values for b in int(w).to_bytes(4,'little'))[:n]

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--quick',action='store_true')
 p.add_argument('--no-reference',action='store_true')
 p.add_argument('--sim',choices=['iverilog','verilator'],default='verilator')
 p.add_argument('--seeds',type=int,nargs='+',default=[17,271,20261112])
 a=p.parse_args();out=HERE/'runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
 freeze_path=ORIGINAL/'SOURCE_SHA256.json';freeze=json.loads(freeze_path.read_text())
 assert sha(freeze_path)=='d3398aec80ffa79b58609997c387f41e8225491661807dd1faa8550b13f9443b'
 for f,h in freeze['files'].items():assert sha(ORIGINAL/f)==h
 writer=module('frozen_original_writer',ORIGINAL/'run_checks.py')
 parser_path=ROOT/'model/export_int8_packets.py';parser=module('independent_packet_parser',parser_path)
 frozen_format=ROOT/'build/global_codec_budget_20261112/frozen_global_codecs.json'
 assert sha(frozen_format)=='e5e2618ef86c7cf237fde66785b5981c0245c55ecd6cb262031405f620ba0d28'
 provenance={str(freeze_path.relative_to(ROOT)):sha(freeze_path),str(parser_path.relative_to(ROOT)):sha(parser_path),
             str(frozen_format.relative_to(ROOT)):sha(frozen_format)}
 cases=[];rng=np.random.default_rng(20261112)
 def add(value,k,delta,row,tag,mode=0,bits=None,declared=None):
  value=np.asarray(value,dtype=np.uint8)
  generated=writer.encode_bytes(value,k,delta)
  payload=generated if bits is None else bits
  i=len(cases);raw=out/f'case{i:04d}.raw.hex';coded=out/f'case{i:04d}.bits.hex'
  words(raw,raw_words(value.tobytes()));words(coded,parser.bits_words(payload))
  cases.append(dict(id=i,mode=mode,symbols=value.size,k=k,delta=int(delta),row=row,bits=len(payload),
                    declared=len(payload) if declared is None else declared,raw=raw.name,coded=coded.name,tag=tag,
                    raw_sha256=sha(raw),coded_sha256=sha(coded)))
 lengths=[1,3,4,15,16,31,32,33,63,64,65,255,256,257] if not a.quick else [1,16,33,65]
 for length in lengths:
  for k in [2,3,5]:add(rng.integers(0,256,(1,length),dtype=np.uint8),k,False,16,f'random_tail{length}_k{k}',3 if k==3 else 2)
 for row in [16,64]:
  value=rng.integers(0,256,(3,row),dtype=np.uint8);value[1]=value[0];value[2]=(value[1].astype(np.uint16)+1).astype(np.uint8)
  for k in [2,3,5]:
   if k!=3 or row==16:add(value,k,True,row,f'delta_row{row}_k{k}',mode=3 if k==3 else 2)
 for k in [2,3,5]:
  for v in [0,128,127]:add(np.full((1,48),v,dtype=np.uint8),k,False,32,f'extreme{v}_k{k}',3 if k==3 else 2)
 # First Rice group has exactly flag1 + 4*(31+1+3) =141 bits;
 # remainder28 zero symbols makes252 payload bits, strictly less than256 raw.
 maximum=np.zeros((16,32),dtype=np.uint8);maximum[:,:4]=128
 add(maximum,3,False,16,'maximum_encoder_append141',3)
 for k in [2,5]:
  add(np.zeros((1,32),dtype=np.uint8),k,False,16,f'all_ones_long_prefix_k{k}',1,'0'+'1'*256)
  add(np.zeros((1,32),dtype=np.uint8),k,False,16,f'noncanonical_raw_k{k}',1,'1'+'0'*256)
  good=writer.encode_bytes(np.zeros((1,32),dtype=np.uint8),k,False)
  add(np.zeros((1,32),dtype=np.uint8),k,False,16,f'truncated_semantic_k{k}',1,good[:-1])
  add(np.zeros((1,32),dtype=np.uint8),k,False,16,f'declared_length_mismatch_k{k}',1,good,len(good)+1)
  add(np.zeros((1,33),dtype=np.uint8),k,False,16,f'missing_symbol_k{k}',1,good)
  add(np.zeros((1,32),dtype=np.uint8),k,True,32,f'invalid_delta_width_k{k}',1,good)
  add(np.zeros((1,32),dtype=np.uint8),k,False,16,f'nonzero_padding_k{k}',1,good)
  c=cases[-1];f=out/c['coded'];v=[int(x,16) for x in f.read_text().split()];v[-1]|=1;words(f,v);c['coded_sha256']=sha(f)
  add(np.zeros((1,31),dtype=np.uint8),k,False,16,f'missing_last_then_drain_k{k}',1,'0'*64,32)
  add(np.zeros((1,32),dtype=np.uint8),k,False,16,f'final_one_bit_k{k}',2)
 add(np.zeros((1,32),dtype=np.uint8),3,False,16,'encoder_final_one_bit',3)
 # Four maximum k2 symbols require265 bits including header. The whole long
 # block is deliberately noncanonical; parser must progress then reject it.
 add(np.zeros((1,64),dtype=np.uint8),2,False,16,'decode_group265_then_noncanonical',1,'0'+('1'*63+'0'+'11')*4+'000'*28)
 task_count=0
 if not a.quick:
  corpus_path=ROOT/'build/int8_packet_corpus_20261112/result.json';corpus=json.loads(corpus_path.read_text())
  assert corpus['passed'] and corpus['tasks']==72
  provenance[str(corpus_path.relative_to(ROOT))]=sha(corpus_path)
  for bundle in corpus['results']:
   result_path=ROOT/bundle['path'].replace('\\','/');assert sha(result_path)==bundle['sha256']
   report=json.loads(result_path.read_text());assert report['passed'] and len(report['layers'])==12
   provenance[str(result_path.relative_to(ROOT))]=sha(result_path)
   for task in report['layers']:
    base=result_path.parent/f'layer{task["layer"]:02d}'
    assert json.loads((base/'manifest.json').read_text())==task
    for name,h in task['files_sha256'].items():assert sha(base/name)==h;provenance[str((base/name).relative_to(ROOT))]=h
    inp=[int(v,16) for v in (base/'input.hex').read_text().split()]
    output=[int(v,16) for v in (base/'expected_output.hex').read_text().split()]
    x,w,_,_=parser.read_input(inp);y=parser.read_output(output)
    dense=b''.join(int(v,16).to_bytes(4,'little') for v in (base/'expected_dense.hex').read_text().split())
    assert y.tobytes()==dense
    offset=202
    streams=[('x',x,2,True,64,inp[1],2)]
    streams += [(f'w{g}',w[:,32*g:32*(g+1)],5,False,32,inp[2+g],2) for g in range(8)]
    for tag,value,k,delta,row,n,mode in streams:
     count=(n+31)//32;wire=bit_string(inp[offset:offset+count],n);offset+=count
     assert wire==writer.encode_bytes(value,k,delta)
     add(value,k,delta,row,f'sample{bundle["sample_index"]}_layer{task["layer"]}_{tag}',mode,wire)
    assert offset==len(inp)
    for tile,n in enumerate(output[1:17]):
     value=y[:,16*tile:16*(tile+1)];wire=bit_string(output[17+398*tile:17+398*tile+(n+31)//32],n)
     assert wire==writer.encode_bytes(value,3,True)
     add(value,3,True,16,f'sample{bundle["sample_index"]}_layer{task["layer"]}_y{tile}',3,wire)
    task_count+=1
   print('CORPUS',bundle['sample_index'],'PASS',flush=True)
  assert task_count==72
 (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 (out/'manifest.txt').write_text(''.join(f"{c['id']} {c['mode']} {c['symbols']} {c['k']} {c['delta']} {c['row']} {c['bits']} {c['declared']} {c['raw']} {c['coded']}\n" for c in cases))
 sources=[HERE/'rice32_encoder.sv',HERE/'rice32_decoder.sv',HERE/'tb_rice32_fixed.sv']
 tracked=sources+[HERE/'contract.json',Path(__file__)]
 hashes={f.name:sha(f) for f in tracked}
 result=out/'result.json';r=dict(schema='qingyu-rice32-fixed-check-v1',passed=False,quick=a.quick,simulator=a.sim,
  source_sha256_before=hashes,provenance_sha256=provenance,
  case_manifest_sha256=sha(out/'cases.json'),real_tasks=task_count,real_streams=25*task_count,
  history_bits=dict(encoder=128,decoder=512,total=640),reservoir_bits=dict(encoder=256,decoder=320,bounded_total=1024,reduction=448),lint=[],runs=[],
  limits=['Accepted payload bit equivalence; changed buffering may change cycles/readiness; only encoderk3/decoderk2,5 accepted','No PPA/STA or whole-system performance claim'])
 def save():result.write_text(json.dumps(r,indent=2)+'\n')
 save()
 try:
  for name,capacity in [('encoder',16),('decoder',64)]:
   rtl=HERE/f'rice32_{name}.sv';xml=out/f'{name}_elaboration.xml'
   for mode,command in [('lint',['verilator','--lint-only','-Wall']),('elaboration',['verilator','--xml-only','--xml-output',str(xml)])]:
    cmd=[*command,'--top-module',f'rice32_{name}',str(rtl)]
    log=out/f'{name}_{mode}.log'
    with log.open('w') as f:proc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
    r['lint'].append(dict(module=name,kind=mode,returncode=proc.returncode));save()
    if proc.returncode:raise RuntimeError('Lint/elaboration failed '+str(log))
   tree=ET.parse(xml).getroot();net=tree.find('netlist');mod=net.find('module')
   var=next(v for v in mod.findall('var') if v.get('name')=='history')
   types={v.get('id'):v for v in net.find('typetable')};dtype=types[var.get('dtype_id')]
   assert dtype.tag=='unpackarraydtype'
   bounds=[int(c.get('name').split('h')[-1],16) for c in dtype.find('range').findall('const')]
   assert abs(bounds[0]-bounds[1])+1==capacity
  bounded=ROOT/'experiments/codec/rice32_bounded'
  freeze_b=json.loads((bounded/'SOURCE_SHA256.json').read_text())
  assert sha(bounded/'SOURCE_SHA256.json')=='e1774bf4beaadc71d2a332dea21fac27b30fc5fb0d3810f0f8ea42cf1bb8c22f'
  for name,h in freeze_b['files'].items():assert sha(bounded/name)==h
  for variant in ['fixed']+([] if a.no_reference else ['bounded_reference']):
   rtl_sources=sources if variant=='fixed' else [bounded/'rice32_encoder.sv',bounded/'rice32_decoder.sv',sources[-1]]
   definitions=[] if variant=='fixed' else ['-DFIXED_CODEC_REFERENCE']
   if a.sim=='iverilog':
    exe=out/(variant+'.vvp');cmd=['iverilog','-g2012','-Wall',*definitions,'-s','tb_rice32_fixed','-o',str(exe),*map(str,rtl_sources)];run=['vvp',str(exe)]
   else:
    obj=Path(tempfile.mkdtemp(prefix='qingyu_fixed_codec_'))/'obj'
    cmd=['verilator','--binary','--timing','--assert','-Wno-fatal',*definitions,'--top-module','tb_rice32_fixed','-j','2','--Mdir',str(obj),*map(str,rtl_sources)]
    run=[str(out/('Vtb_'+variant))]
   with (out/(variant+'_compile.log')).open('w') as log:proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=900)
   if proc.returncode:raise RuntimeError('Compile failed '+variant)
   if a.sim=='verilator':shutil.copy2(obj/'Vtb_rice32_fixed',run[0])
   for seed in a.seeds:
    log=out/f'{variant}_seed{seed}.log'
    with log.open('w') as f:proc=subprocess.run([*run,f'+SEED={seed}','+MANIFEST=manifest.txt'],cwd=out,stdout=f,stderr=subprocess.STDOUT,timeout=900)
    text=log.read_text();passes=re.findall(r'^PASS rice32_fixed (.*)$',text,re.M);ok=proc.returncode==0 and len(passes)==1
    r['runs'].append(dict(variant=variant,seed=seed,passed=ok,log=log.name,log_sha256=sha(log),
     summary={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',passes[0])} if passes else {},
     coverage={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',next((x for x in text.splitlines() if x.startswith('COVER ')),''))},
     cases=[{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)} for line in text.splitlines() if line.startswith('CASE ')]));save()
    print('RUN',variant,seed,'PASS' if ok else 'FAIL',flush=True)
    if not ok:raise RuntimeError(text[-5000:])
  if not a.no_reference:
   comparisons=[]
   for seed in a.seeds:
    fixed=next(x for x in r['runs'] if x['variant']=='fixed' and x['seed']==seed)
    ref=next(x for x in r['runs'] if x['variant']=='bounded_reference' and x['seed']==seed)
    assert len(fixed['cases'])==len(ref['cases'])
    for f,b in zip(fixed['cases'],ref['cases']):
     assert all(f[k]==b[k] for k in ['id','stalls','symbols','bits'])
     comparisons.append(dict(seed=seed,id=f['id'],tag=cases[f['id']]['tag'],stalls=f['stalls'],encoder_cycles=f['enc_cycles'],encoder_delta=f['enc_cycles']-b['enc_cycles'],decoder_cycles=f['dec_cycles'],decoder_delta=f['dec_cycles']-b['dec_cycles']))
   (out/'cycle_comparison.json').write_text(json.dumps(comparisons,indent=2)+'\n')
   r['cycle_comparison_sha256']=sha(out/'cycle_comparison.json')
  for name,h in freeze_b['files'].items():assert sha(bounded/name)==h
  r['source_sha256_after']={f.name:sha(f) for f in tracked};assert r['source_sha256_after']==hashes
  assert all(sha(ROOT/name)==h for name,h in provenance.items())
  assert all(sha(ORIGINAL/name)==h for name,h in freeze['files'].items())
  r['passed']=True
 except Exception as e:r['failure']=str(e);raise
 finally:save();print(result,flush=True)

if __name__=='__main__':main()
