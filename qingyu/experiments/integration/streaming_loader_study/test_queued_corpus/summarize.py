"""Persist validated diagnostic corpus evidence and common-sample01 comparisons."""
from pathlib import Path
import argparse,hashlib,json,statistics
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('result',type=Path);a=p.parse_args()
 path=a.result.resolve();r=json.loads(path.read_text())
 if not r['passed'] or len(r['runs'])!=12 or r['producer_one_per_port']:raise ValueError('Incomplete queued corpus')
 for k,h in r['source_sha256'].items():
  if sha(ROOT/k)!=h:raise ValueError('Source changed')
 baseline_path=HERE.parent/'test/VALIDATION.json';baseline=json.loads(baseline_path.read_text())
 meta_path=HERE/'METADATA_BOUND.json';meta=json.loads(meta_path.read_text())
 for k,h in meta['input_sha256'].items():
  if sha(ROOT/k)!=h:raise ValueError('Metadata source changed')
 runs=[];by={}
 for row in r['runs']:
  rp=ROOT/row['result'];q=json.loads(rp.read_text())
  if sha(rp)!=row['result_sha256'] or not q['passed']:raise ValueError('Original result changed')
  if sha(rp.parent/'simv')!=q['binary_sha256']:raise ValueError('Binary changed')
  for k,h in {**q['compiled_source_sha256'],**q['source_sha256'],**q['packet_sha256']}.items():
   if sha(ROOT/k)!=h:raise ValueError('Original inputs changed')
  for lr in q['layers']:
   if sha(rp.parent/f'layer{lr["layer"]:02d}.log')!=lr['log_sha256']:raise ValueError('Original log changed')
   for k,h in lr['output_dumps_sha256'].items():
    if sha(rp.parent/f'layer{lr["layer"]:02d}'/k)!=h:raise ValueError('Output artifact changed')
  tasks=[{k:v for k,v in t.items() if k not in ['primary','profile']} for t in row['tasks']]
  if len(tasks)!=12 or any(not t['cold_before_first_offer'] for t in tasks):raise ValueError('Missing cold tasks')
  record={k:v for k,v in row.items() if k not in ['packet_sha256','log','log_sha256','tasks']};record['tasks']=tasks
  runs.append(record);by[(row['core'],row['sample'])]=(row,q)
 comparisons=[]
 for b in baseline['runs']:
  sample=int(b['sample'][6:]);core=b['core'];row,q=by[(core,sample)];bp=ROOT/b['result']
  if sha(bp)!=b['result_sha256']:raise ValueError('01 baseline changed')
  old=json.loads(bp.read_text())
  if old['packet_sha256']!=q['packet_sha256']:raise ValueError('01/00 packets differ')
  for name,h in old['compiled_source_sha256'].items():
   if '/test/tb_' in name:continue
   if q['compiled_source_sha256'].get(name)!=h:raise ValueError('01/00 hardware source differs')
  for t,oldrow in zip(row['tasks'],old['layers']):
   if t['service_floor_cycles']!=oldrow['primary']['commands']:raise ValueError('01/00 task traffic differs')
  comparisons.append(dict(sample=sample,core=core,baseline_result=b['result'],baseline_result_sha256=b['result_sha256'],queued_result=row['result'],queued_result_sha256=row['result_sha256'],
   mean_cycles01=b['streaming_offer_cycles']['mean'],mean_cycles00=row['cycles']['mean'],
   saved_mean_cycles=b['streaming_offer_cycles']['mean']-row['cycles']['mean']))
 target=150000000/10450;scenarios=[]
 for s in r['diagnostic_summary']:
  m=s['cycles']['mean'];saving=meta['average_service_floor_reduction_one_extra_header']
  scenarios.append(dict(core=s['core'],diagnostic_mean_cycles=m,target_cycle_budget_at_unverified_150mhz=target,
   gap_cycles=m-target,lossless_metadata_floor_reduction_with_one_format_word=saving,
   hypothetical_mean_if_elapsed_saved_exactly_floor_delta=m-saving,hypothetical_remaining_gap=m-saving-target,
   warning='Budget scenario only; parser/control/throughput and actual elapsed benefit are unimplemented'))
 out=dict(schema='qingyu-queued-loader-diagnostic-validation-v1',passed=True,result=path.relative_to(ROOT).as_posix(),result_sha256=sha(path),
  profile_baseline_manifest='experiments/integration/streaming_loader_study/test/PROFILE_SOURCE_SHA256.json',profile_baseline_manifest_sha256=sha(HERE.parent/'test/PROFILE_SOURCE_SHA256.json'),
  total_unique_cold_primary_tasks=144,unique_primary_tasks_per_core=72,total_normal_control_cases=576,normal_output_words_checked=576*6385,
  total_masters=2,producer_one_per_port=False,compiled_binary_reused=True,codec='frozen rice32_bounded',
  timing=r['timing'],limitations=r['limitations'],diagnostic_summary=r['diagnostic_summary'],runs=runs,common_three_sample_01_00_comparisons=comparisons,
  metadata_bound='METADATA_BOUND.json',metadata_bound_sha256=sha(meta_path),metadata_scenarios=scenarios)
 dest=HERE/'VALIDATION.json';dest.write_text(json.dumps(out,indent=2)+'\n')
 names=['run_corpus.py','audit_metadata.py','summarize.py','README.md','METADATA_BOUND.json','VALIDATION.json']
 manifest=dict(schema='qingyu-queued-loader-corpus-source-v1',frozen=True,files={n:sha(HERE/n) for n in names},external_dependencies=r['source_sha256'],
  raw_result=path.relative_to(ROOT).as_posix(),raw_result_sha256=sha(path),validation_sha256=sha(dest))
 (HERE/'SOURCE_SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps(comparisons,indent=2));print('VALIDATION '+sha(dest));print('SOURCE '+sha(HERE/'SOURCE_SHA256.json'));print('RAW '+sha(path))
if __name__=='__main__':main()
