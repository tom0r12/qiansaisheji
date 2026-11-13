"""Read-only bounded live status, formatted for unedited evidence screenshots."""
from pathlib import Path
import datetime,json,re,time
def emit(s=''):
 for line in str(s).splitlines()or['']:print(' '*44+line[:145],flush=True)
def read(p):return json.loads(p.read_text())
for step in range(240):
 print('\033[2J\033[H',end='',flush=True)
 emit('Q12 ENGINEERING VALIDATION - '+datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
 emit('150 MHz | official TT 1.10 V 25 C | full matrix, no output codec')
 stop=False
 for pattern in ('q12_earlycheck_full_*/result.json','q12_power_probe_*/result.json','q12_compact12_full_*/result.json'):
  for p in Path('/tmp').glob(pattern):
   r=read(p);root=p.parent;emit();emit('RUN '+str(root));emit('PHASE '+str(r.get('phase')))
   for key in ('error','power_error','mean_task_cycles','throughput_at_150mhz','mean_energy_uj','mean_energy_uj_unqualified','acceptance_error','units_error','provisional_unqualified'):
    if key in r:emit(key+' '+str(r[key]))
   if 'earlycheck'in str(root):
    emit('engine_sha256 '+str(r.get('engine_sha256')))
    for q in root.glob('qingyu_q12_final_vendor_*/result.json'):
     v=read(q);emit('VENDOR phase=%s tasks=%d passed=%s'%(v.get('phase'),len(v.get('tasks',[])),v.get('passed')))
    for name in ('synth','formal'):
     log=root/name/'tool.log'
     if log.exists():
      lines=[x.strip()for x in log.read_text(errors='replace').splitlines()if x.strip()]
      emit(name.upper()+': '+' | '.join(lines[-2:]))
    f=root/'formal/result.json'
    if f.exists():
     v=read(f);emit('FORMAL complete=%s accepted=%s'%(v.get('tool_complete'),v.get('passed')))
    powers=[(k,v)for k,v in r.get('stages',{}).items()if k.startswith('power_layer')]
    emit('POWER windows completed '+str(len(powers)))
    if powers:emit(str(powers[-1]))
    if r.get('phase')in('failed','reports_complete'):stop=True
   if 'power_probe'in str(root):
    emit('PROBE ONLY - superseded checkpoint; excludes final score claim')
    if 'tool_complete'in r:emit('tool_complete '+str(r['tool_complete']))
    log=root/'tool.log'
    if log.exists():emit('PT '+ ' | '.join(log.read_text(errors='replace').splitlines()[-2:]))
   area=root/'synth/explicit_area_summary.txt'
   if area.exists():
    emit(' | '.join(x for x in area.read_text().splitlines()if x.startswith(('INCREMENTAL_LIBRARY_AREA=','FULL_SOC_LIBRARY_AREA='))))
   sr=r.get('stages',{}).get('synth',{})
   for key in ('worst_reported_setup_ns','worst_reported_hold_ns'):
    if key in sr:emit(key+' '+str(sr[key]))
 emit();emit('Read-only monitor; Ctrl+C stops this display, not the EDA jobs.')
 if stop:break
 if datetime.datetime.utcnow()>=datetime.datetime(2026,11,13,9,23):break
 time.sleep(15)
