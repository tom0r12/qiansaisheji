"""Run the frozen queued-producer fixture on six diagnostic packets and both cores."""
from __future__ import annotations
import argparse,concurrent.futures,hashlib,json,statistics,subprocess,threading
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
STUDY=HERE.parent
ROOT=HERE.parents[3]
SAMPLES=[0,9,31,127,202,255]
BUILDS={
 'winograd_task8_prefetch':'build/streaming_loader_profile/20261111T183420388452Z',
 'winograd_task9':'build/streaming_loader_profile/20261111T183525574779Z'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(xs):return dict(min=min(xs),max=max(xs),mean=statistics.mean(xs),sum=sum(xs))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workers',type=int,default=2);a=p.parse_args()
 if a.workers not in [1,2]:p.error('workers must be 1 or 2')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 out=ROOT/'build/streaming_loader_queued_corpus'/stamp;out.mkdir(parents=True)
 source_manifest=STUDY/'test/PROFILE_SOURCE_SHA256.json';frozen=json.loads(source_manifest.read_text())
 dependencies=dict(frozen['external_dependencies'])
 for k,h in frozen['files'].items():dependencies[(source_manifest.parent/k).relative_to(ROOT).as_posix()]=h
 dependencies[source_manifest.relative_to(ROOT).as_posix()]=sha(source_manifest)
 dependencies[Path(__file__).relative_to(ROOT).as_posix()]=sha(Path(__file__))
 def unchanged():
  for k,h in dependencies.items():
   if sha(ROOT/k)!=h:raise ValueError('Frozen input changed: '+k)
 unchanged()
 r=dict(schema='qingyu-queued-loader-diagnostic-corpus-v1',passed=False,created_utc=stamp,source_sha256=dependencies,
  samples=SAMPLES,cores=list(BUILDS),producer_one_per_port=False,core_tasks=72,total_unique_primary_tasks=144,
  timing='case id1 only, fresh coordinated reset before first producer write offer; inclusive through final originating magic ACK',
  limitations=['Six selected diagnostic samples, including generated silence009 and known high-traffic202; not an unbiased dataset mean','No actual E203 or identified official loader;00 is a queued platform producer capability assumption','No new codec/quantization; frozen bounded codec and identical packet images','Unverified150MHz, no STA/area/energy/manufacturer macro/PPA claim','All subsequent cases are functional recovery/control evidence, not cold primary'],
  commands=[],runs=[])
 lock=threading.Lock()
 def save():(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 save()
 def worker(core,sample):
  unchanged()
  label=f'{core}_sample{sample:03d}';log=out/(label+'.log')
  cmd=['python3',str(STUDY/'run_profile.py'),'--images',f'build/int8_packet_corpus_20261112/sample{sample:03d}','--layers','12','--jobs','2','--queued-loader',
       '--core-dir','experiments/arithmetic/'+core,'--reuse-build',BUILDS[core]]
  with lock:r['commands'].append(dict(core=core,sample=sample,argv=cmd,log=log.name));save()
  with log.open('w') as f:proc=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=900)
  if proc.returncode:raise RuntimeError('Frozen runner failed: '+str(log))
  lines=log.read_text().splitlines();paths=[Path(x) for x in lines if x.endswith('/result.json') and x.startswith(str(ROOT))]
  if len(paths)!=1:raise ValueError('Result path missing/ambiguous: '+str(log))
  path=paths[0];q=json.loads(path.read_text())
  if not q['passed'] or q['producer_one_per_port'] or len(q['layers'])!=12:raise ValueError('Incomplete queued run')
  prior=json.loads((ROOT/BUILDS[core]/'result.json').read_text())
  if q['binary_sha256']!=prior['binary_sha256'] or q['build_fingerprint']!=prior['build_fingerprint'] or q['compiled_source_sha256']!=prior['compiled_source_sha256']:raise ValueError('Compiled identity changed')
  tasks=[]
  for row in q['layers']:
   m=row['primary'];v=row['primary_profile'];layer=row['layer'];folder=path.parent
   if m['id']!=1 or v['id']!=1 or m['error'] or m['mode'] or v['producer_limit_one']:raise ValueError('Not reset-cold queued primary')
   if sha(folder/f'layer{layer:02d}.log')!=row['log_sha256']:raise ValueError('Layer log changed')
   for k,h in row['output_dumps_sha256'].items():
    if sha(folder/f'layer{layer:02d}'/k)!=h:raise ValueError('Output artifact changed')
   floor=2*m['source_writes']+m['output_writes']
   if floor!=m['commands'] or floor!=m['responses'] or v['cycles']!=floor+v['blocked_fabric']+v['no_routed_offer']:raise ValueError('Traffic/idle partition differs')
   tasks.append(dict(layer=layer,cold_before_first_offer=True,cycles=m['offer_to_final'],service_floor_cycles=floor,
     excess_cycles=m['offer_to_final']-floor,source_words=m['source_writes'],unique_output_words=m['output_writes']-1,
     blocked_fabric=v['blocked_fabric'],no_routed_offer=v['no_routed_offer'],primary=m,profile=v))
  item=dict(sample=sample,core=core,result=path.relative_to(ROOT).as_posix(),result_sha256=sha(path),binary_sha256=q['binary_sha256'],build_fingerprint=q['build_fingerprint'],
    packet_sha256=q['packet_sha256'],log=log.name,log_sha256=sha(log),cycles=stats([x['cycles'] for x in tasks]),
    service_floor_cycles=stats([x['service_floor_cycles'] for x in tasks]),excess_cycles=stats([x['excess_cycles'] for x in tasks]),tasks=tasks)
  unchanged()
  with lock:r['runs'].append(item);save()
  print(f'PASS {label} mean={item["cycles"]["mean"]}',flush=True)
  return item
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
   futures=[pool.submit(worker,c,s) for c in BUILDS for s in SAMPLES]
   for f in concurrent.futures.as_completed(futures):f.result()
  unchanged();r['runs'].sort(key=lambda x:(x['core'],x['sample']))
  summaries=[]
  for core in BUILDS:
   rows=[x for x in r['runs'] if x['core']==core];tasks=[t for row in rows for t in row['tasks']]
   if len(tasks)!=72:raise ValueError('Incomplete core corpus')
   summaries.append(dict(core=core,unique_cold_tasks=72,cycles=stats([t['cycles'] for t in tasks]),service_floor_cycles=stats([t['service_floor_cycles'] for t in tasks]),
    excess_cycles=stats([t['excess_cycles'] for t in tasks]),blocked_fabric=stats([t['blocked_fabric'] for t in tasks]),no_routed_offer=stats([t['no_routed_offer'] for t in tasks]),
    conditional_diagnostic_tasks_per_second_at_unverified_150mhz=150000000/statistics.mean(t['cycles'] for t in tasks),
    ideal_service_only_tasks_per_second_at_unverified_150mhz=150000000/statistics.mean(t['service_floor_cycles'] for t in tasks)))
  r['diagnostic_summary']=summaries;r['passed']=True
 except Exception as e:r['failure']=str(e);raise
 finally:save();print(out/'result.json',flush=True)
if __name__=='__main__':main()
