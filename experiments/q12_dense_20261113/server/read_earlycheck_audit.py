"""Read-only exact-candidate timing and power coverage diagnostics."""
from pathlib import Path
import collections,csv,datetime,json,re
def emit(s=''):
 for line in str(s).splitlines()or['']:print(' '*35+line,flush=True)
roots=list(Path('/tmp').glob('q12_earlycheck_full_*/result.json'));assert len(roots)==1
root=roots[0].parent
print('\033[2J\033[H',end='');emit('Q12 TIMING AUDIT '+datetime.datetime.now().isoformat())
emit('SOURCE '+str(root))
for name in ('check_timing_after.rpt','constraints.rpt','cdc_exception_audit.txt'):
 p=root/'synth'/name;emit('FILE '+name)
 if p.exists():
  lines=[x for x in p.read_text(errors='replace').splitlines()if x.strip()]
  emit('\n'.join(lines[:60]));emit('TOTAL_LINES '+str(len(lines)))
for name in ('timing_max.rpt','timing_min.rpt'):
 p=root/'synth'/name;emit('FILE '+name)
 if p.exists():
  text=p.read_text();emit('\n'.join(x for x in text.splitlines()if re.search(r'Startpoint:|Endpoint:|Path Group:|Path Type:|slack ',x))[:2600])
emit('FORMAL')
f=root/'formal/tool.log'
if f.exists():emit('\n'.join(f.read_text(errors='replace').splitlines()[-6:]))
for p in Path('/tmp').glob('q12_power_recovery_*/result.json'):
 r=json.loads(p.read_text());emit('POWER '+str(p.parent)+' '+r.get('phase',''))
 if r.get('error'):emit(r['error'])
 if r.get('first_tool_error'):emit(r['first_tool_error'])
 if r.get('windows'):emit(json.dumps(r['windows'][-1]))
