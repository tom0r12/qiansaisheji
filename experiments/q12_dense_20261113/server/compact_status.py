from pathlib import Path
import json,re,subprocess
for pattern in ('q12_native12_full_*/result.json','q12_compact12_full_*/result.json','q12_native12_timing_*/result.json','q12_cell_activity_*/result.json','q12_earlycheck_full_*/result.json','q12_timing_post_*/result.json'):
 for f in Path('/tmp').glob(pattern):
  r=json.loads(f.read_text());p=f.parent;print('\nRUN',p,'PHASE',r.get('phase'))
  for key in ('error','power_error','worst_setup_ns','worst_hold_ns','mean_task_cycles','mean_energy_uj','mean_energy_uj_unqualified'):
   if key in r:print(key,r[key])
  a=p/'synth/explicit_area_summary.txt'
  if a.exists():print(' | '.join(x for x in a.read_text().splitlines()if x.startswith(('INCREMENTAL_LIBRARY_AREA=','FULL_SOC_LIBRARY_AREA='))))
  for f2 in p.glob('qingyu_q12_final_vendor_*/result.json'):
   v=json.loads(f2.read_text());print('VENDOR',v.get('phase'),len(v.get('tasks',[])),v.get('passed'))
   if v.get('tasks'):
    act=v['tasks'][0].get('activity',{});saif=f2.parent/act.get('saif_relpath','MISSING')
    if saif.is_file():
     text=saif.read_text();print('SAIF_MACRO_MARKERS',text.count('macro_ram'),'INSTANCES',text.count('(INSTANCE'))
  for name in ('synth','formal'):
   log=p/name/'tool.log'
   if log.exists():print(name.upper(),' | '.join(log.read_text(errors='replace').splitlines()[-3:]))
  for name,rec in r.get('stages',{}).items():
   if name.startswith('power'):print(name,rec.get('tool_complete'),rec.get('provisional_unqualified'),rec.get('acceptance_error'))
  for proc in list(p.glob('*/process.json'))+list(p.glob('vendor_process.json')):
   pid=json.loads(proc.read_text())['pid']
   ps=subprocess.run(['ps','-p',str(pid),'-o','pid,etime,time,stat,comm'],stdout=subprocess.PIPE,universal_newlines=True).stdout.splitlines()
   if len(ps)>1:print('PROCESS',proc.parent.name,ps[-1])
for pattern in ('q12_early_launch_*/run.log',):
 for p in Path('/tmp').glob(pattern):print('LAUNCH',p,' | '.join(p.read_text(errors='replace').splitlines()[-5:]))
