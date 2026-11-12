"""Archive exact first-generation SoC sources after all diagnostic tasks pass."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 live=ROOT/'experiments/integration/int8soc'
 corpus_path=ROOT/'build/int8soc_corpus/20261111T172044938227Z/result.json'
 corpus=json.loads(corpus_path.read_text())
 assert corpus['passed'] and corpus['tasks']==72,'Corpus still incomplete'
 assert sha(live/'run_soc.py')==corpus['soc_runner_sha256']
 assert sha(live/'run_corpus_soc.py')==corpus['script_sha256']
 reports=[corpus_path,ROOT/'build/int8soc/20261111T171723244199Z/result.json',
  ROOT/'build/int8soc/20261111T171723243779Z/result.json',
  ROOT/'build/int8stream_mmio/20261111T171826155350Z/result.json']
 for r in corpus['runs']:
  report=ROOT/r['result'];assert sha(report)==r['result_sha256'];reports.append(report)
 for path in reports:
  data=json.loads(path.read_text());assert data.get('passed'),str(path)
  for name,digest in data.get('sources_sha256',{}).items():
   assert sha(ROOT/name)==digest,'Compiled source changed '+name
  if 'simulator_path' in data:assert sha(ROOT/data['simulator_path'])==data['simulator_sha256']
  for row in data.get('layers',[]):
   assert sha(ROOT/row['simulation_log'])==row['simulation_log_sha256']
 destination=ROOT/'experiments/integration/int8soc_baseline_20261112'
 destination.mkdir(exist_ok=False)
 names=['qingyu_int8stream_fio.sv','qingyu_e203_soc_top.v','soc_main.c','tb_int8soc.sv',
  'run_soc.py','run_corpus_soc.py','prepare_top.py','contract.json',
  'tb_int8stream_fio.sv','run_mmio_checks.py','MMIO_TEST_SOURCE_SHA256.json']
 original={str((live/name).relative_to(ROOT)):sha(live/name) for name in names}
 for name in names:shutil.copy2(live/name,destination/name)
 assert original=={str((live/name).relative_to(ROOT)):sha(destination/name) for name in names}
 summary={'schema':'qingyu-initial-int8-soc-source-archive-v1','created_utc':datetime.now(timezone.utc).isoformat(),
  'scope':'Exact source archive of the first real E203 packet integration, with original tested-source path mapping. All original data and results retained; this does not promote current_candidate or prove official loader/PPA.',
  'original_source_sha256':original,'files':{name:sha(destination/name) for name in names},
  'reports':{str(p.relative_to(ROOT)):sha(p) for p in reports},
  'corpus_statistics':{k:corpus[k] for k in ['tasks','min_cpu_setup_to_ack','max_cpu_setup_to_ack','diagnostic_mean_cpu_setup_to_ack','complete_task_output_elements']},
  'external_rtl':'Exact external dependencies are identified by each SoC report sources_sha256 and the existing frozen engine/core/codec/transport manifests.',
  'notes':['The archived contract records its original pending-stage wording; passing stages are documented by these later hashed reports.',
   'Source initializer outside the task window; generated silence and traffic-extreme samples are explicitly selected diagnostics, not an unbiased population mean.',
   'Actual manufacturer macros/150MHz STA/area/whole-SoC energy/official600 evaluation remain unproven.']}
 (destination/'SOURCE_ARCHIVE.json').write_text(json.dumps(summary,indent=2)+'\n')
 print('ARCHIVED',destination,'SHA256',sha(destination/'SOURCE_ARCHIVE.json'))
if __name__=='__main__':main()
