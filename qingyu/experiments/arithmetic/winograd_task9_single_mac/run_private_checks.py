"""Full three-seed task9 regression through unchanged ASIC SRAM pin wrappers.

The explicit local models poison Q on writes; they are not manufacturer models.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,subprocess,tempfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--cases',type=int,default=22)
 p.add_argument('--seeds',type=int,nargs='+',default=[2371,2477,2551])
 a=p.parse_args();vectors=ROOT/'build/winograd_task8_vectors_20261112'
 vm=json.loads((vectors/'manifest.json').read_text());assert vm['completed'] and 1<=a.cases<=len(vm['cases'])
 for case in vm['cases']:
  for key,name in case['files'].items():assert sha(vectors/name)==case['sha256'][key]
 base=HERE.parent/'winograd_task9'
 assert sha(HERE/'tb_winograd_task8.sv')==sha(base/'tb_winograd_task8.sv'),'Original independent checker changed'
 models=ROOT/'build/bundle_template_checks/20261111T162200Z/local_functional_models.sv'
 assert sha(models)=='cd78caa3d3484f22d397b173e9c6a610c76939f53b7ff332a0dd55354bae9a33'
 sources=[HERE/'winograd_int8_task8.sv',HERE.parent/'winograd_array8/winograd_int8_pair_acc32.sv',
          ROOT/'rtl/asic/qingyu_sram16.sv',models,HERE/'tb_winograd_task8.sv']
 tracked=sources+[Path(__file__),HERE/'contract.json']
 before={x.relative_to(ROOT).as_posix():sha(x) for x in tracked}
 out=ROOT/'build/winograd_task9_single_mac_private'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 out.mkdir(parents=True)
 temporary=Path(tempfile.mkdtemp(prefix='qingyu_task9_single_private_'))
 (temporary/'vectors').symlink_to(vectors,target_is_directory=True)
 report=dict(schema='qingyu-task9-single-mac-asic-standin-v1',passed=False,source_sha256=before,
  vectors_manifest_sha256=sha(vectors/'manifest.json'),original_checker_sha256=sha(base/'tb_winograd_task8.sv'),
  scope='Unmodified task9 complete checker through real ASIC wrapper ports; external local Q-poison functional stand-ins',
  compact_memory_used=False,manufacturer_model=False,full_soc=False,ppa_measured=False,
  temporary_directory=str(temporary),commands=[],simulations=[])
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 def run(argv,log,timeout):
  with (out/log).open('w') as f:r=subprocess.run(list(map(str,argv)),cwd=temporary,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
  report['commands'].append(dict(argv=list(map(str,argv)),returncode=r.returncode,log=log));save()
  if r.returncode:raise RuntimeError(str(out/log))
  return (out/log).read_text()
 save();print(out,flush=True)
 try:
  binary=temporary/'simulation.vvp'
  run(['iverilog','-g2012','-Wall','-s','tb_winograd_task8','-o',binary,*sources],'compile.log',120)
  elaboration=binary.read_text()
  counts={str(n):len(re.findall(r'\.scope module, "macro_ram" "RAMSP'+str(n)+'X16"',elaboration)) for n in [128,1024,4096]}
  assert counts=={'128':21,'1024':9,'4096':0},counts
  report['actual_macro_counts']=counts
  report['simulation_binary_sha256']=sha(binary)
  for seed in a.seeds:
   text=run(['vvp','-i',binary,'+VECTORS='+str(temporary/'vectors'),'+CASES='+str(a.cases),'+SEED='+str(seed)],f'seed_{seed}.log',1800)
   match=re.search(r'^PASS task8 (.+)$',text,re.M);assert match,'no complete PASS'
   metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',match.group(1))}
   assert metrics['real_or_synthetic_cases']==a.cases and metrics['successful']==a.cases+11
   assert metrics['aborted']==7 and metrics['errors']==2 and metrics['resets']==8
   assert metrics['fast_cycles']==9355,'Original task9 no-stall schedule changed'
   tasks=[{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)} for line in text.splitlines() if line.startswith('TASK ')]
   assert len(tasks)==a.cases+13
   assert all(t['cycles']==sum(t[k] for k in ['load','factor','cache','compute','store']) for t in tasks)
   for t in tasks:
    if not t['error']:
     assert t['r_reads']==1584 and t['snapshots']==176 and t['burst_writes']==512
     assert t['overlap_load']>0 and t['overlap_meta']>0
   report['simulations'].append(dict(seed=seed,passed=True,metrics=metrics,tasks=tasks));save()
   print('PASS ASIC seed',seed,metrics,flush=True)
  assert before=={x.relative_to(ROOT).as_posix():sha(x) for x in tracked},'Source changed during run'
  assert sha(vectors/'manifest.json')==report['vectors_manifest_sha256']
  report.update(passed=True,logs_sha256={x.name:sha(x) for x in out.glob('*.log')});save()
  print('RESULT',out/'result.json',flush=True)
 except Exception as e:
  report['error']=str(e);save();raise
if __name__=='__main__':main()
