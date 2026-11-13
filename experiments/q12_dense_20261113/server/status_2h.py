"""Read-only progress summary for the bounded timing/area/power session."""
from pathlib import Path
import json,re,subprocess
for prefix in ('q12_native12_full_','q12_compact12_full_','q12_native12_timing_','q12_c25_timing_full_','q12_power_recover_','q12_timing_post_','q12_cell_activity_'):
 for f in sorted(Path('/tmp').glob(prefix+'*/result.json')):
  r=json.loads(f.read_text());p=f.parent
  print('\nRUN',p,'PHASE',r.get('phase'))
  for k in ('error','worst_setup_ns','worst_hold_ns','reported_setup_hold_nonnegative','mean_energy_uj','mean_energy_uj_unqualified'):
   if k in r:print(k,r[k])
  q=p/'synth/explicit_area_summary.txt'
  if q.exists():print('\n'.join(x for x in q.read_text().splitlines()if 'INCREMENTAL_'in x or 'FULL_SOC_'in x))
  for stage,v in r.get('stages',{}).items():
   print('STAGE',stage,json.dumps({k:v[k]for k in ('tool_complete','passed','accepted','seconds','acceptance_error','provisional_unqualified')if k in v},sort_keys=True))
  logs=list(p.glob('synth/tool.log'))+list(p.glob('formal/tool.log'))+list(p.glob('power_layer*/tool.log'))+list(p.glob('vendor.log'))
  for q in logs:
   print('TAIL',q.relative_to(p),' | '.join(q.read_text(errors='replace').splitlines()[-3:]))
  for q in p.glob('*/process.json'):
   v=json.loads(q.read_text())
   print('PROCESS',q.parent.name,subprocess.run(['ps','-p',str(v['pid']),'-o','pid,etime,time,pcpu,stat,comm'],stdout=subprocess.PIPE,universal_newlines=True).stdout.strip().replace('\n',' | '))
for pattern in ('q12_timing_launch_*/run.log','q12_c25_timing_launch_*/run.log','q12_cell_launch_*/run.log','q12_post_launch_*/run.log'):
 for q in Path('/tmp').glob(pattern):print('LAUNCH_LOG',q,'\n'.join(q.read_text(errors='replace').splitlines()[-10:]))
