"""Exercise a prepared physical fixture using explicitly local substitute macros.

This runner does not bypass the server's manufacturer-model gate and is never
a server payload. Its result proves local fixture compatibility only.
"""
from datetime import datetime,timezone
import argparse,hashlib,json,re,subprocess
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--bundle',type=Path,required=True)
 p.add_argument('--models',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();bundle=a.bundle.resolve();models=a.models.resolve();out=a.output.resolve()
 out.mkdir(parents=True,exist_ok=False)
 manifest=json.loads((bundle/'manifest.json').read_text())
 for n,h in manifest['files_sha256'].items():assert sha(bundle/n)==h,n
 source=[bundle/n for n in (bundle/'filelists/macro.f').read_text().splitlines()]+[models]
 hashes={str(x):sha(x) for x in source}
 report={'passed':False,'scope':'Physical fixture and exact metric comparison using local functional stand-ins, not vendor timing/PPA',
         'created_utc':datetime.now(timezone.utc).isoformat(),'bundle_manifest_sha256':sha(bundle/'manifest.json'),
         'models_sha256':sha(models),'models_outside_bundle':not models.is_relative_to(bundle),
         'sources_sha256':hashes,'commands':[]}
 assert report['models_outside_bundle']
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 def run(command,name,timeout):
  report['commands'].append(command);save()
  with (out/name).open('w') as log:
   r=subprocess.run(command,cwd=bundle,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
  report[name+'_returncode']=r.returncode;save()
  if r.returncode:raise RuntimeError(f'{name} failed; see {out}')
 try:
  include=['-I'+str(bundle/'vendor/e203_hbirdv2/rtl/e203'/x) for x in ['core','perips','perips/apb_i2c']]
  exe=out/'run.vvp'
  run(['iverilog','-g2012','-DDISABLE_SV_ASSERTION=1','-s',manifest['checker']['top'],*include,'-o',str(exe),*map(str,source)],'compile.log',120)
  run(['vvp',str(exe),'+FIRMWARE=layer00/firmware64.hex','+SHARED=layer00/shared.hex','+EXPECTED=layer00/expected.hex'],'simulation.log',240)
  log=(out/'simulation.log').read_text()
  assert 'PASS real E203' in log and 'PASS official fabric path' in log
  original=json.loads((bundle/'evidence/local_run.json').read_text())['layers'][0]['metrics']
  metrics={}
  for tag,expected in original.items():
   line=next(x for x in log.splitlines() if x.startswith(tag+' '))
   actual={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)}
   assert actual==expected,(tag,actual,expected)
   metrics[tag]=actual
  for path,h in hashes.items():assert sha(Path(path))==h,path
  report.update(passed=True,all_metrics_equal_to_frozen_layer0=True,metrics=metrics)
 finally:
  report['logs_sha256']={x.name:sha(x) for x in out.glob('*.log')};save()
  print(out/'result.json',flush=True)

if __name__=='__main__':main()
