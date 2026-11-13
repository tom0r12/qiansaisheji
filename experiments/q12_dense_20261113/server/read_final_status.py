"""Read-only concise measurements, preserving full reports on the server."""
from pathlib import Path
import datetime,json,re,subprocess
def emit(s=''):
 for line in str(s).splitlines()or['']:print(' '*35+line,flush=True)
def read(p):return json.loads(p.read_text())
print('\033[2J\033[H',end='')
emit('Q12 VALIDATION '+datetime.datetime.now().isoformat())
for pattern in ('q12_earlycheck_full_*/result.json','q12_power_recovery_*/result.json','q12_compact12_full_*/result.json'):
 for f in Path('/tmp').glob(pattern):
  r=read(f);root=f.parent;emit();emit('RUN '+str(root));emit('PHASE '+str(r.get('phase')))
  for key in ('error','first_tool_error','mean_task_cycles','throughput_at_150mhz','mean_energy_uj_unqualified','weighted_power_w_unqualified'):
   if key in r:emit(key+' '+str(r[key]))
  if 'earlycheck'in str(root):
   for key in ('engine_sha256','netlist_sha256'):emit(key+' '+str(r.get(key)))
   v=root/'vendor_completed.json'
   if v.exists():
    vr=read(v);cycles=vr['task_cycles'];emit('VENDOR 12/12 PASS cycles '+str(cycles));emit('TASKS/S '+str(150000000/(sum(cycles)/12)))
  sr=r.get('stages',{}).get('synth',{})
  for k in ('tool_complete','seconds','worst_reported_setup_ns','worst_reported_hold_ns'):
   if k in sr:emit('SYNTH '+k+' '+str(sr[k]))
  a=root/'synth/explicit_area_summary.txt'
  if a.exists():
   for x in a.read_text().splitlines():
    if x.startswith(('INCREMENTAL_LIBRARY_AREA=','FULL_SOC_LIBRARY_AREA=','FIO_LIBRARY_AREA=','NP3_ARBITER_LIBRARY_AREA=','SHARED_NONMACRO_LIBRARY_AREA=')):emit(x)
  for name in ('synth','formal'):
   log=root/name/'tool.log'
   if log.exists():
    lines=[x.strip()for x in log.read_text(errors='replace').splitlines()if x.strip()];emit(name+' TAIL '+' | '.join(lines[-2:]))
   res=root/name/'result.json'
   if res.exists():emit(name+' RESULT '+json.dumps(read(res))[:650])
  if r.get('windows'):
   emit('POWER WINDOWS '+str(len(r['windows'])))
   for w in r['windows']:emit('L%02d complete=%s P/E=%s audit=%s'%(w['layer'],w['tool_complete'],w.get('provisional_unqualified'),w.get('acceptance_error')))
  if 'recovery'in str(root):
   logs=sorted(root.glob('layer*/tool.log'))
   if logs:emit('PT TAIL '+' | '.join(logs[-1].read_text(errors='replace').splitlines()[-2:]))
for p in Path('/tmp').glob('q12_power_fix_launch_*/run.log'):emit('LAUNCH '+' | '.join(p.read_text(errors='replace').splitlines()[-2:]))
