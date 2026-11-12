"""Freeze local compact-physical checks and immutable package identities."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def passed(path):
 p=ROOT/path;r=json.loads(p.read_text());assert r['passed'];return {'path':path,'sha256':sha(p)},r
def main():
 records={
  'prefetch8':('20261111T184201356571Z','20261111T183709887253Z','20261111T174454919053Z',416,53),
  'task9':('20261111T184212287047Z','20261111T183727570930Z','20261111T175642268453Z',352,48)}
 result=dict(schema='qingyu-int8soc-compact-server-validation-v1',passed=True,
  scope='Local compact-private full-E203 physical-interface verification and server package preparation',
  manufacturer_models_executed=False,formal_ppa_measured=False,official_loader_included=False,uploaded=False,
  local_model_sha256='cd78caa3d3484f22d397b173e9c6a610c76939f53b7ff332a0dd55354bae9a33',
  local_model_kind='external functional stand-in; writes poison Q; not packaged',variants={},
  limits=['One physical full-SoC task per core; original behavioral 72-task corpus is packaged for subsequent manufacturer regression',
          'Source/TCM preload and pre-parameter boot excluded; official loader boundary OPEN',
          'No official library/macro timing, area, energy, formal or official600 accuracy acceptance'])
 for name,(package,physical,corpus,words,count) in records.items():
  prefix='build/int8soc_compact_server_bundles/'+package;directory=ROOT/prefix
  check,checks=passed(prefix+'/local_package_checks.json');gate,gates=passed(prefix+'/local_model_gate_checks.json')
  phys,pr=passed('build/int8soc_compact_physical_fixture/'+physical+'/result.json')
  corp,cr=passed('build/int8soc_corpus/'+corpus+'/result.json')
  package_path=directory/'package_result.json';packed=json.loads(package_path.read_text());bundle=ROOT/packed['bundle']
  assert sha(ROOT/packed['zip'])==packed['zip_sha256'] and cr['tasks']==72
  assert pr['compact_valid_words']==words and checks['actual_macro_counts']==dict(private128=count,private1024=0,shared4096=64,cpu4096=16)
  for source in (HERE/'templates').rglob('*'):
   if source.is_file() and '__pycache__' not in source.parts:assert sha(source)==sha(bundle/source.relative_to(HERE/'templates'))
  for filename in ['tb_int8soc_behavior.sv','tb_int8soc_macro.sv']:
   assert sha(HERE/filename)==sha(ROOT/'experiments/integration/int8soc_server'/filename)
  shell=['wsl.exe','-d','Ubuntu','--','sh','-n','/mnt/d/芯片设计赛道/qiansaisheji/qingyu/'+prefix+'/qic']
  process=subprocess.run(shell,capture_output=True)
  (directory/'launcher_shell_check.log').write_bytes(process.stdout+process.stderr);assert process.returncode==0
  result['variants'][name]=dict(package=packed,package_result_sha256=sha(package_path),
   package_checks=check,negative_model_activity_gates=gate,physical_fixture=phys,
   physical_metrics=pr['metrics']['INT8SOC_METRICS'],physical_tasks=1,shared_words_preloaded=131072,shared_words_read_back=131072,
   identical_baseline_metrics=pr['identical_baseline_metrics'],actual_macros=checks['actual_macro_counts'],x_valid_words=words,
   baseline_behavioral_corpus=corp,baseline_behavioral_tasks=72,
   launcher_shell_check=dict(exit_code=process.returncode,log_sha256=sha(directory/'launcher_shell_check.log')))
 (HERE/'VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n')
 sources={p.relative_to(HERE).as_posix():sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='SOURCE_SHA256.json'}
 manifest=dict(schema='qingyu-int8soc-compact-server-source-v1',frozen_utc=datetime.now(timezone.utc).isoformat(),files=sources,
  source_boundary='Independent fixture and packaging only. Actual compiled source and physical configuration bound by each package.',
  external_dependencies={'experiments/memory/private_x_compact/SOURCE_SHA256.json':sha(ROOT/'experiments/memory/private_x_compact/SOURCE_SHA256.json'),
                         'experiments/integration/int8soc_server/SOURCE_SHA256.json':sha(ROOT/'experiments/integration/int8soc_server/SOURCE_SHA256.json')})
 (HERE/'SOURCE_SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print('VALIDATION',sha(HERE/'VALIDATION.json'));print('SOURCE',sha(HERE/'SOURCE_SHA256.json'))
if __name__=='__main__':main()
