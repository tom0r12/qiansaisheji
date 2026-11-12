"""Exercise the actual private macro wrapper with explicitly local four-state stand-ins.

These models only check the pin mapping, single-port storage and read latency;
they are not foundry functional/timing models and provide no PPA evidence.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,subprocess,tempfile

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--core-dir',type=Path,default=ROOT/'experiments/arithmetic/winograd_task8_overlap')
 p.add_argument('--cases',type=int,default=12)
 p.add_argument('--seed',type=int,default=2371)
 a=p.parse_args();core=(ROOT/a.core_dir).resolve()
 manifest=json.loads((core/'SOURCE_SHA256.json').read_text())
 for name,digest in manifest['files'].items():assert sha(core/name)==digest
 for name,digest in manifest.get('external_dependencies',{}).items():assert sha(ROOT/name)==digest
 vectors=ROOT/'build/winograd_task8_vectors_20261112';vm=json.loads((vectors/'manifest.json').read_text())
 assert vm['completed'] and 1<=a.cases<=len(vm['cases'])
 for case in vm['cases']:
  for key,name in case['files'].items():assert sha(vectors/name)==case['sha256'][key]
 out=ROOT/'build/int8_private_macro'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
 temporary=Path(tempfile.mkdtemp(prefix='qingyu_int8_macro_'))
 (temporary/'vectors').symlink_to(vectors,target_is_directory=True)
 models=ROOT/'build/bundle_template_checks/20261111T162200Z/local_functional_models.sv'
 assert sha(models)=='cd78caa3d3484f22d397b173e9c6a610c76939f53b7ff332a0dd55354bae9a33','local stand-in changed'
 sources=[core/'winograd_int8_task8.sv',ROOT/'experiments/arithmetic/winograd_array8/winograd_int8_pair_acc32.sv',
  ROOT/'rtl/asic/qingyu_sram16.sv',models,core/'tb_winograd_task8.sv']
 before={str(s.relative_to(ROOT)):sha(s) for s in sources}
 report={'passed':False,'schema':'qingyu-int8-private-macro-functional-standin-v1',
  'core_directory':str(core.relative_to(ROOT)),'sources_sha256':before,
  'script_sha256':sha(Path(__file__)),'vectors_manifest_sha256':sha(vectors/'manifest.json'),
  'core_source_manifest_sha256':sha(core/'SOURCE_SHA256.json'),'seed':a.seed,'cases':a.cases,
  'scope':'Actual ASIC private wrapper mapping using local synchronous #1 read/Q=X-on-write RAMSP stand-ins; four-state Icarus; no foundry model, STA or PPA',
  'temporary_directory':str(temporary),'commands':[]}
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 def run(argv,name,timeout):
  with (out/name).open('w') as log:r=subprocess.run(list(map(str,argv)),cwd=temporary,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
  report['commands'].append({'argv':list(map(str,argv)),'returncode':r.returncode,'log':name});save()
  if r.returncode:raise RuntimeError(str(out/name))
 save();print(out,flush=True)
 try:
  binary=temporary/'simulation.vvp'
  run(['iverilog','-g2012','-Wall','-s','tb_winograd_task8','-o',binary,*sources],'compile.log',120)
  run(['vvp',binary,'+VECTORS='+str(temporary/'vectors'),'+CASES='+str(a.cases),'+SEED='+str(a.seed)],'simulation.log',1200)
  text=(out/'simulation.log').read_text()
  match=re.search(r'^PASS task8 (.+)$',text,re.M);assert match,'no complete PASS'
  metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',match.group(1))}
  assert metrics['real_or_synthetic_cases']==a.cases and metrics['successful']==a.cases+11
  tasks=[{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)} for line in text.splitlines() if line.startswith('TASK ')]
  assert all(t['cycles']==sum(t[k] for k in ['load','factor','cache','compute','store']) for t in tasks)
  assert before=={str(s.relative_to(ROOT)):sha(s) for s in sources},'source changed'
  report.update(passed=True,metrics=metrics,tasks=tasks,logs_sha256={s.name:sha(s) for s in out.glob('*.log')});save()
  print('PASS '+str(out/'result.json'),flush=True)
 except Exception as e:report['error']=str(e);save();raise
if __name__=='__main__':main()
