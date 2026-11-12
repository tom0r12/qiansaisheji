"""Persist completed local INT8 physical/package evidence without altering it."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def evidence(path):
 p=ROOT/path;r=json.loads(p.read_text());assert r['passed'];return {'path':path,'sha256':sha(p)},r
def main():
 records={
  'prefetch8':('20261111T180240444050Z','20261111T174803874627Z','20261111T174454919053Z'),
  'task9':('20261111T180709439563Z','20261111T175811744904Z','20261111T175642268453Z')}
 result=dict(schema='qingyu-int8soc-server-validation-v1',passed=True,scope='Local physical-interface functional verification and server package preparation',
  manufacturer_models_executed=False,formal_ppa_measured=False,official_loader_included=False,
  local_model_sha256='cd78caa3d3484f22d397b173e9c6a610c76939f53b7ff332a0dd55354bae9a33',
  local_model_kind='external functional stand-in; write Q poisoned; never copied into bundle',variants={},
  review_fixes=['Power artifact hash must agree with actual file, reviewed identity and passed simulation row','Explicit vendor include hashes in Tcl, plus whole copied manifest checked after assessment'],
  limitations=['Shared/TCM preload excluded; official loader boundary OPEN','No manufacturer timing model or official-library EDA execution','No new area, STA, energy or official600 accuracy claim','Upload/remote execution is managed separately by the main workflow'])
 for name,(package,physical,corpus) in records.items():
  prefix='build/int8soc_server_bundles/'+package
  check,checks=evidence(prefix+'/local_package_checks.json');gate,gates=evidence(prefix+'/local_model_gate_checks.json')
  phys,pr=evidence('build/int8soc_physical_fixture/'+physical+'/result.json')
  corp,cr=evidence('build/int8soc_corpus/'+corpus+'/result.json')
  package_path=ROOT/prefix/'package_result.json';packed=json.loads(package_path.read_text())
  assert sha(ROOT/packed['zip'])==packed['zip_sha256'] and cr['tasks']==72
  result['variants'][name]=dict(package=packed,package_result_sha256=sha(package_path),package_checks=check,negative_model_activity_gates=gate,
   physical_fixture=phys,physical_metrics=pr['metrics']['INT8SOC_METRICS'],shared_words_read_back=131072,
   physical_metrics_identical_to_behavioral=pr['identical_baseline_metrics'],actual_macros=checks['actual_macro_counts'],
   real_cpu_72_task_corpus=corp,cpu_setup_range=[cr['min_cpu_setup_to_ack'],cr['max_cpu_setup_to_ack']],diagnostic_mean_cpu_cycles=cr['diagnostic_mean_cpu_setup_to_ack'])
 result['superseded_package']=dict(path='build/int8soc_server_bundles/20261111T175542803501Z/qingyu_int8soc_validation.zip',sha256='851075f701566b85b1be901649c8bd50913f64937930849043fb29ceb15a006f',reason='R2 strengthens activity/assessment source binding; old artifact retained, not the current power entry')
 result['retained_failed_fixture']=dict(path='build/int8soc_physical_fixture/20261111T174625832811Z/result.json',reason='Icarus rejected non-ASCII absolute readmemh paths; inputs are now copied and referenced by relative filenames')
 (HERE/'VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n')
 sources={p.relative_to(HERE).as_posix():sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='SOURCE_SHA256.json'}
 manifest=dict(schema='qingyu-int8soc-server-source-v1',frozen_utc=datetime.now(timezone.utc).isoformat(),files=sources,
  source_boundary='Only this independent fixture/packaging directory. Candidate/source identities are separately bound by each immutable package.',external_dependencies={})
 (HERE/'SOURCE_SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print('VALIDATION',sha(HERE/'VALIDATION.json'));print('SOURCE',sha(HERE/'SOURCE_SHA256.json'))
if __name__=='__main__':main()
