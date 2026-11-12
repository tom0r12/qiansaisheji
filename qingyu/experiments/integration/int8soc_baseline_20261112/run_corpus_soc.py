"""Run the pre-registered varied packet corpus on a hash-verified E203 binary."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,subprocess,sys,hashlib,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--reuse-build',type=Path,required=True)
 p.add_argument('--core-dir',type=Path,default=ROOT/'experiments/arithmetic/winograd_task8_overlap')
 a=p.parse_args()
 manifest_path=ROOT/'build/int8_packet_corpus_20261112/result.json';manifest=json.loads(manifest_path.read_text())
 assert manifest['passed'] and manifest['tasks']==72
 out=ROOT/'build/int8soc_corpus'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
 runner=HERE/'run_soc.py'
 report={'passed':False,'script_sha256':sha(Path(__file__)),'soc_runner_sha256':sha(runner),
  'corpus_manifest_sha256':sha(manifest_path),'core_directory':str(a.core_dir),'tasks':0,'runs':[],
  'scope':'Pre-registered diagnostic corpus with varied speech, silence control and high-traffic input; not an unbiased population mean, official600, factory PPA or official initial-loader timing'}
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 save();print(out,flush=True)
 for item in manifest['results']:
  packet_result=(ROOT/item['path'].replace('\\','/')).resolve()
  assert packet_result.is_relative_to(ROOT) and sha(packet_result)==item['sha256']
  log=out/f'sample{item["sample_index"]:03d}.log'
  command=[sys.executable,str(runner),'--layers','12','--reuse-build',str(a.reuse_build),
           '--images',str(packet_result.parent),'--core-dir',str(a.core_dir),'--jobs','2']
  with log.open('w') as stream:
   result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=1200)
  if result.returncode:raise RuntimeError('SoC corpus subrun failed: '+str(log))
  matches=re.findall(r'^PASS (.+/result.json)$',log.read_text(),re.M)
  assert len(matches)==1
  path=Path(matches[0]);data=json.loads(path.read_text())
  assert data['passed'] and data['sample_index']==item['sample_index'] and len(data['layers'])==12
  report['runs'].append({'sample_index':item['sample_index'],'result':str(path.relative_to(ROOT)),
   'result_sha256':sha(path),'metrics':[r['metrics'] for r in data['layers']]})
  report['tasks']+=12;save()
  print('PASS SoC sample',item['sample_index'],data['mean_cpu_setup_to_ack_cycles'],flush=True)
 assert sha(runner)==report['soc_runner_sha256']
 metrics=[m for r in report['runs'] for m in r['metrics']]
 report.update(passed=True,min_cpu_setup_to_ack=min(m['cpu_setup_to_ack'] for m in metrics),
  max_cpu_setup_to_ack=max(m['cpu_setup_to_ack'] for m in metrics),
  diagnostic_mean_cpu_setup_to_ack=sum(m['cpu_setup_to_ack'] for m in metrics)/len(metrics),
  complete_task_output_elements=report['tasks']*25344)
 save();print('PASS '+str(out/'result.json'),flush=True)
if __name__=='__main__':main()
