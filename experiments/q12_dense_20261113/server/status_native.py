"""Compact read-only status, bound to source identity rather than latest mtime."""
from pathlib import Path
import json,re,subprocess
for p in sorted(list(Path('/tmp').glob('q12_native12_*/result.json'))+list(Path('/tmp').glob('q12_compact12_*/result.json'))):
 try:r=json.loads(p.read_text())
 except (OSError,ValueError):continue
 files=r.get('identity',{}).get('files',{})
 print('RUN',p.parent,'PHASE',r.get('phase'),'CONVERTER',files.get('run_dense.py','')[:12])
 if 'error'in r:print('ERROR',r['error'])
 if 'mean_full_window_cycles'in r:print('MEAN',r['mean_full_window_cycles'],'CONDITIONAL_TPS',r.get('conditional_throughput_150mhz'))
 for v in p.parent.glob('qingyu_q12_final_vendor_*/result.json'):
  q=json.loads(v.read_text());tasks=q.get('tasks',[])
  cycles=[t['metrics']['full_window_cycles']for t in tasks]
  print('VENDOR',q.get('phase'),'TASKS',len(tasks),'CYCLES',cycles)
  if 'error'in q:print('VENDOR_ERROR',q['error'])
  if cycles:print('OBSERVED_MEAN',sum(cycles)/len(cycles))
 if(p.parent/'synth/tool.log').is_file():
  lines=(p.parent/'synth/tool.log').read_text(errors='replace').splitlines()
  print('SYNTH_TAIL',' | '.join(lines[-4:]))
 if(p.parent/'synth/explicit_area_summary.txt').is_file():print((p.parent/'synth/explicit_area_summary.txt').read_text())
 for stage,rec in r.get('stages',{}).items():
  print('STAGE',stage,json.dumps(rec,sort_keys=True))
 for name in ['timing_max.rpt','timing_min.rpt']:
  q=p.parent/'synth'/name
  if q.is_file():
   slacks=re.findall(r'slack\s*\([^)]*\)\s*([-+\d.]+)',q.read_text())
   if slacks:print(name,'MIN_SLACK',min(map(float,slacks)))
for p in sorted(list(Path('/tmp').glob('q12_native_full_launch_*/run.log'))+list(Path('/tmp').glob('q12_compact_full_launch_*/run.log'))+list(Path('/tmp').glob('q12_compact_launch_*/run.log'))):
 print('FULL_LAUNCH',p,' | '.join(p.read_text(errors='replace').splitlines()[-3:]))
