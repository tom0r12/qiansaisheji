"""Audit and compare isolated producer-credit profiles against the frozen 01 runs."""
from pathlib import Path
import argparse,hashlib,json
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('results',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 baseline_path=HERE/'VALIDATION.json';baseline=json.loads(baseline_path.read_text())
 base={(r['sample'],r['core']):r for r in baseline['runs']};runs=[];groups={}
 for path in a.results:
  path=path.resolve();r=json.loads(path.read_text());folder=path.parent
  if not r['passed'] or len(r['layers'])!=1:raise ValueError('Only completed single-layer profiles supported')
  packets=[k for k in r['packet_sha256'] if k.endswith('/result.json')]
  if len(packets)!=1:raise ValueError('Packet identity ambiguous')
  sample=Path(packets[0]).parent.name;core=Path(r['core_directory']).name;one=r['producer_one_per_port'];layer=r['layers'][0]
  for k,h in {**r['compiled_source_sha256'],**r['source_sha256'],**r['packet_sha256']}.items():
   if sha(ROOT/k)!=h:raise ValueError('Input changed: '+k)
  if sha(folder/'simv')!=r['binary_sha256'] or sha(folder/'layer00.log')!=layer['log_sha256']:raise ValueError('Binary/log changed')
  for k,h in layer['output_dumps_sha256'].items():
   if sha(folder/'layer00'/k)!=h:raise ValueError('Output changed')
  original=base[(sample,core)];op=ROOT/original['result']
  if sha(op)!=original['result_sha256']:raise ValueError('Original result changed')
  original_result=json.loads(op.read_text())
  if r['packet_sha256']!=original_result['packet_sha256']:raise ValueError('Input identities differ')
  if one and layer['cases'][:4]!=original_result['layers'][0]['cases'][:4]:raise ValueError('01 profile instrumentation changed measured behavior')
  m=layer['primary'];q=layer['primary_profile'];s=layer['serial']
  if m['id']!=1 or q['id']!=1 or q['cycles']!=m['offer_to_final']:raise ValueError('Not reset-cold primary')
  if q['cycles']!=q['loader_accept']+q['read_accept']+q['write_accept']+q['blocked_fabric']+q['no_routed_offer']:raise ValueError('Nonexclusive profile accounting')
  if q['cycles']!=q['pre_start']+q['load_overlap']+q['post_load_tail']:raise ValueError('Stage partition incomplete')
  if m['commands']!=2*m['source_writes']+m['output_writes']:raise ValueError('Missing initial-load traffic')
  if s['producer_window']!=(2*m['source_writes']+1 if one else m['source_writes']+2):raise ValueError('Isolated producer expected service accounting differs')
  item=dict(sample=sample,core=core,producer_one_per_port=one,result=path.relative_to(ROOT).as_posix(),result_sha256=sha(path),
   original_result=original['result'],original_result_sha256=original['result_sha256'],
   original_first_four_case_metrics_match=one,cold_before_first_offer=True,primary=m,profile=q,
   exact_bandwidth_floor_cycles=m['commands'],service_only_max_tasks_per_second_at_unverified_150mhz=150000000/m['commands'],
   conditional_tasks_per_second_at_unverified_150mhz=150000000/q['cycles'],
   occupied_command_fraction=m['commands']/q['cycles'],shared_read_hit_fraction=m['read_hits']/m['source_reads'],
   isolated_serial_producer_cycles=s['producer_window'],serial_control_cold_before_first_offer=False,
   extended_test_summary=layer['summary'],fault_cases=[c for c in layer['cases'] if c['mode']>=3])
  runs.append(item);key=(sample,core)
  if one in groups.setdefault(key,{}):raise ValueError('Duplicate profile')
  groups[key][one]=(item,r)
 comparisons=[]
 for (sample,core),g in groups.items():
  if set(g)!={False,True}:raise ValueError('Missing 01/00 pair')
  b,br=g[True];q,qr=g[False]
  if br['compiled_source_sha256']!=qr['compiled_source_sha256']:raise ValueError('Credit comparison changed RTL/TB sources')
  for k in ['source_writes','source_reads','output_writes','commands','responses','physical_writes']:
   if b['primary'][k]!=q['primary'][k]:raise ValueError('Credit comparison changed transaction flow')
  bs=dict(br['build_signature']);qs=dict(qr['build_signature'])
  bs['options']=[x for x in bs['options'] if not x.startswith('-DLOADER_ONE_PER_PORT=')]
  qs['options']=[x for x in qs['options'] if not x.startswith('-DLOADER_ONE_PER_PORT=')]
  if bs!=qs:raise ValueError('More than producer credit parameter changed')
  comparisons.append(dict(sample=sample,core=core,cycles_01=b['profile']['cycles'],cycles_00=q['profile']['cycles'],
   saved_cycles=b['profile']['cycles']-q['profile']['cycles'],
   no_offer_reduction=b['profile']['no_routed_offer']-q['profile']['no_routed_offer'],
   blocked_fabric_delta=q['profile']['blocked_fabric']-b['profile']['blocked_fabric'],
   queued_remaining_above_service_floor=q['profile']['cycles']-q['exact_bandwidth_floor_cycles']))
 report=dict(schema='qingyu-conditional-loader-credit-profile-v1',passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
  baseline_validation=baseline_path.relative_to(ROOT).as_posix(),baseline_validation_sha256=sha(baseline_path),
  mechanism='Exact same merger/fabric/shared/engine/core/TB sources, only compile define ONE_PER_PORT01 versus00 differs per core/sample pair',
  limitations=['00 is an unknown queued platform producer capability hypothesis, not the current E203 or an identified official loader','Only layer0 of sample000 and202 is profiled; no distribution-wide mean is inferred','Primary id1 follows coordinated reset; back-to-back/serial controls are functional only, not cold-before-offer','Counters of accepted commands/blocked fabric/no routed offer form one exclusive partition; stage counts form another; other stall counters overlap','150MHz is unverified; area, energy and official-loader compliance are not measured','Producer-observed error injection does not validate fabric error routing'],
  runs=runs,comparisons=comparisons)
 a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(comparisons,indent=2));print(sha(a.output))
if __name__=='__main__':main()
