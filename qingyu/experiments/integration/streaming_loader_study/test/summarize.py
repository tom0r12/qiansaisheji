"""Recheck retained loader evidence and summarize unique primary tasks, without editing results."""
from __future__ import annotations
import argparse,hashlib,json,statistics
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(values):return dict(min=min(values),max=max(values),mean=statistics.mean(values),sum=sum(values))
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('results',type=Path,nargs='+')
 p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();records=[];seen=set();identities={}
 for name in a.results:
  path=name.resolve();r=json.loads(path.read_text());directory=path.parent
  if not r['passed'] or len(r['layers'])!=12:raise ValueError('Need completed twelve-layer runs')
  packet=[k for k in r['packet_sha256'] if k.endswith('/result.json')]
  if len(packet)!=1:raise ValueError('Ambiguous packet identity')
  sample=Path(packet[0]).parent.name;core=Path(r['core_directory']).name
  key=(sample,core)
  if key in seen:raise ValueError('Duplicate sample/core run')
  seen.add(key)
  for k,h in {**r['compiled_source_sha256'],**r['source_sha256'],**r['packet_sha256']}.items():
   if sha(ROOT/k)!=h:raise ValueError('Input identity changed: '+k)
  if sha(directory/'simv')!=r['binary_sha256']:raise ValueError('Binary changed')
  if sample in identities and identities[sample]!=r['packet_sha256']:raise ValueError('Cross-core input identities differ')
  identities[sample]=r['packet_sha256']
  layers=[];normal_cases=0;fault_cases=0;fault_delays=[];resets=0
  for row in r['layers']:
   layer=row['layer'];log=directory/f'layer{layer:02d}.log'
   if sha(log)!=row['log_sha256']:raise ValueError('Log changed')
   for k,h in row['output_dumps_sha256'].items():
    if sha(directory/f'layer{layer:02d}'/k)!=h:raise ValueError('Output artifact changed')
   primary=row['primary'];serial=row['serial']
   if primary!=row['cases'][0] or serial!=row['cases'][2] or primary['id']!=1:raise ValueError('Primary/serial aliases differ')
   for c in row['cases']:
    if c['mode']<=2:
     normal_cases+=1
     if c['commands']!=c['responses'] or c['commands']!=2*c['source_writes']+c['output_writes'] or c['source_reads']!=c['source_writes']:raise ValueError('Initial-load traffic incomplete')
     if c['offer_to_final']<c['commands']:raise ValueError('Single-bus physical lower bound violated')
    else:
     fault_cases+=1
     if c['mode']!=3:fault_delays.append(c['error_to_done'])
   resets+=row['summary']['hard_resets']
   if any(primary[k]!=serial[k] for k in ['source_writes','source_reads','output_writes','commands','responses']):raise ValueError('Streaming/serial traffic differs')
   layers.append(dict(layer=layer,primary_cold_before_first_offer=True,primary_cold_basis='Fresh simulator process; coordinated initial rst_n reset clears engine/transport/core/merge/shared before case id1 first producer offer',streaming=primary,serial=serial,
                      serial_cold_before_first_offer=False,back_to_back_cold_before_first_offer=False,
                      streaming_cycle_reduction=serial['offer_to_final']-primary['offer_to_final']))
  stream=[x['streaming']['offer_to_final'] for x in layers];serial=[x['serial']['offer_to_final'] for x in layers]
  records.append(dict(sample=sample,core=core,result=path.relative_to(ROOT).as_posix(),result_sha256=sha(path),
   binary_sha256=r['binary_sha256'],build_fingerprint=r['build_fingerprint'],packet_result=packet[0],packet_result_sha256=r['packet_sha256'][packet[0]],
   streaming_offer_cycles=stats(stream),serial_offer_cycles=stats(serial),
   streaming_cycle_reduction_percent=(1-sum(stream)/sum(serial))*100,
   conditional_tasks_per_second_at_unverified_150mhz=150000000/statistics.mean(stream),
   source_writes=stats([x['streaming']['source_writes'] for x in layers]),
   commands=stats([x['streaming']['commands'] for x in layers]),
   service_only_minimum_cycles=stats([x['streaming']['commands'] for x in layers]),
   excess_cycles_over_one_transaction_per_cycle=stats([x['streaming']['offer_to_final']-x['streaming']['commands'] for x in layers]),
   successful_full_memory_checked_cases=normal_cases,successful_output_words_checked=normal_cases*6385,
   expected_producer_fault_cases=fault_cases,coordinated_reset_cases=resets,
   active_fault_to_done_cycles=stats(fault_delays) if fault_delays else None,layers=layers))
 summary=dict(schema='qingyu-conditional-loader-summary-v1',created_utc=datetime.now(timezone.utc).isoformat(),passed=True,
  topology='same-clock conditional producer at original CPU/DMA merger port0; engine port1; NP2 OUT4 ONE_PER_PORT01; unchanged official fabric and opt33 single shared slave',
  timing='Inclusive first real source offer/accept/originating successful ACK to final originating engine magic-write ACK; primary aggregation uses only case id1 after fresh coordinated global reset, twelve unique cold layer tasks per sample/core',
  errors='Faults are injected into the producer-observed ACK result or loader_fault sideband; fabric error wires are not injected and no error-routing coverage is claimed',
  limits=['Conditional producer is not the actual E203 or official platform loader','150MHz conversion is not STA or official throughput','No area, energy, manufacturer SRAM or PPA proof','Only sample000/009/202 diagnostic corpus; sample009 is generated silence','Back-to-back and serial-control cases retain previous private epoch until accepted START: functional recovery/control evidence, not cold-before-first-offer measurements; these cases never enter primary throughput aggregation','Overlapping stall counters must not be added as independent delays'],
  runs=records)
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps([dict(sample=r['sample'],core=r['core'],streaming_mean=r['streaming_offer_cycles']['mean'],serial_mean=r['serial_offer_cycles']['mean'],conditional_tps=r['conditional_tasks_per_second_at_unverified_150mhz']) for r in records],indent=2))
 print(a.output);print(sha(a.output))
if __name__=='__main__':main()
