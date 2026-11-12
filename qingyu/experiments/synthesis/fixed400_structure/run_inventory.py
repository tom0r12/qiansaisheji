"""Inventory only fixed400 netlists whose exact generated behavior already passed."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import hashlib,json,subprocess,tempfile,shutil,re
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def number(x):return int(x,2) if isinstance(x,str) else int(x)
def canonical(text,path):
 escaped=''.join(chr(v) if v<128 else f"${v:02x}" for v in str(path).encode('utf8'))
 pattern='$func$'+escaped+':'
 hits=0
 def rename(match):
  nonlocal hits
  token=match.group(0)
  if pattern in token:hits+=1;return token.replace(pattern,'$func$<source>:')
  return token
 text=re.sub(r'\\[^\s]+',rename,text)
 if hits==0:raise ValueError('No exact source-location identifiers found')
 return text,hits

def main():
 candidate=ROOT/'experiments/codec/rice32_fixed400';manifest=candidate/'SOURCE_SHA256.json';frozen=json.loads(manifest.read_text())
 for n,h in frozen['files'].items():assert sha(candidate/n)==h
 frontend=candidate/'runs/frontend_20261111T183220713810Z';proof=json.loads((frontend/'result.json').read_text());assert proof['passed']
 assert all(x['passed'] for x in proof['stages'])
 for n in ['rice32_encoder.sv','rice32_decoder.sv']:assert sha(candidate/n)==proof['source_sha256'][n]
 out=ROOT/'build/fixed400_structure'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
 report=dict(schema='qingyu-fixed400-simulation-bound-structure-v1',passed=False,script_sha256=sha(Path(__file__)),candidate_manifest_sha256=sha(manifest),frontend_result_sha256=sha(frontend/'result.json'),yosys_version=subprocess.check_output(['yosys','-V'],text=True).strip(),results=[],limits=['Exact optimized netlist identity binds finite four-state functional/held/error testing; not formal equivalence signoff.','Unmapped RTLIL cells, inferred memory and retained bits are not official-library gates, mm2, timing or energy.','The old generic/bounded encoder task-inout inventory remains rejected and is not used for a resource ratio.'])
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 save();print(out,flush=True)
 try:
  for unit in ['encoder','decoder']:
   case=out/unit;case.mkdir();work=Path(tempfile.mkdtemp(prefix='qingyu_fixed400_structure_'))
   # Preserve the exact passed sv2v bytes but use ASCII temporary paths so
   # Yosys0.33 does not emit malformed non-ASCII source escapes into JSON.
   name=unit+'_sv2v.v';assert sha(frontend/name)==proof['generated_artifacts_sha256'][name]
   src=work/name;shutil.copy2(frontend/name,src);shutil.copy2(src,case/name)
   net=work/(unit+'_yosys.v');data=work/'structure.json';ys=case/'inventory.ys'
   ys.write_text(f'read_verilog {src}\nhierarchy -check -top rice32_{unit}\nproc\nopt\nwreduce\nopt\nmemory_collect\nopt_clean\ncheck -assert\nstat -width\nwrite_json {data}\nwrite_verilog -noattr {net}\n')
   with (case/'yosys.log').open('w') as log:subprocess.run(['yosys','-Q','-T','-s',str(ys)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
   shutil.copy2(net,case/net.name);shutil.copy2(data,case/data.name)
   expected=proof['generated_artifacts_sha256'][net.name]
   old_text,old_count=canonical((frontend/net.name).read_text(),frontend/name)
   new_text,new_count=canonical(net.read_text(),src)
   if old_text!=new_text or old_count!=new_count:raise ValueError('Netlist differs beyond exact source-location identifier renaming; reject '+unit)
   (case/'canonical.v').write_text(new_text)
   mod=json.loads(data.read_text())['modules']['rice32_'+unit];types=Counter();ff=Counter();mem=[];mult=[]
   for name,cell in mod['cells'].items():
    kind=cell['type'];pars=cell['parameters'];types[kind]+=1
    if re.match(r'^\$(?:a|s)?dff',kind):ff[kind]+=number(pars['WIDTH'])
    if re.match(r'^\$(?:a)?dlatch',kind):raise ValueError('Unexpected latch')
    if kind=='$mem_v2':mem.append(dict(name=name,width=number(pars['WIDTH']),words=number(pars['SIZE']),read_ports=number(pars['RD_PORTS']),write_ports=number(pars['WR_PORTS'])))
    if kind=='$mul':mult.append({k:number(pars[k]) for k in ['A_WIDTH','B_WIDTH','Y_WIDTH','A_SIGNED','B_SIGNED']})
   item=dict(unit=unit,simulation_proven_netlist_sha256=expected,netlist_byte_identity=sha(net)==expected,netlist_identity_except_source_location_identifiers=True,source_location_renamed_tokens=new_count,canonical_sha256=sha(case/'canonical.v'),rtl_cells_by_type=dict(sorted(types.items())),flip_flop_bits_by_type=dict(sorted(ff.items())),flip_flop_bits=sum(ff.values()),unmapped_memories=mem,unmapped_memory_bits=sum(x['width']*x['words'] for x in mem),generic_multipliers=mult,artifacts_sha256={x.name:sha(x) for x in case.iterdir() if x.is_file()},warnings=[x for x in (case/'yosys.log').read_text().splitlines() if x.startswith('Warning:')])
   report['results'].append(item);save();print(unit,'FF',item['flip_flop_bits'],'unmapped_memory_bits',item['unmapped_memory_bits'],'proven netlist identical',flush=True)
  # The newly emitted, unmodified netlists also run the original finite test.
  tb=frontend/'tb_netlist.sv';shadow=frontend/'reference_rice32_encoder.sv'
  assert sha(tb)==proof['generated_artifacts_sha256'][tb.name]
  assert sha(shadow)==sha(candidate/'runs/20261111T183200398601Z/reference_rice32_encoder.sv')
  exe=out/'structure_checked.vvp'
  with (out/'compile.log').open('w') as log:subprocess.run(['iverilog','-g2012','-s','tb_rice32_fixed400','-o',str(exe),str(out/'encoder/encoder_yosys.v'),str(out/'decoder/decoder_yosys.v'),str(shadow),str(tb)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
  with (out/'simulation.log').open('w') as log:subprocess.run(['vvp',str(exe),'+MANIFEST=manifest.txt','+SEED=17'],cwd=candidate/'runs/20261111T183200398601Z',stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
  assert 'PASS rice32_fixed400' in (out/'simulation.log').read_text()
  report['new_netlist_simulation_passed']=True;report['simulation_log_sha256']=sha(out/'simulation.log')
  for n,h in frozen['files'].items():assert sha(candidate/n)==h
  report['passed']=True
 except Exception as e:report['failure']=str(e);raise
 finally:save();print(out/'result.json',flush=True)
if __name__=='__main__':main()
