"""Read only PT annotation and unit evidence from the compatibility run."""
from pathlib import Path
import collections,csv,datetime,json,re
def emit(s=''):
 for line in str(s).splitlines()or['']:print(' '*35+line,flush=True)
print('\033[2J\033[H',end='');emit('Q12 POWER COVERAGE '+datetime.datetime.now().isoformat())
for root in Path('/tmp').glob('q12_power_recovery_*'):
 f=root/'result.json'
 if not f.exists():continue
 r=json.loads(f.read_text());emit(str(root)+' '+r['phase'])
 if r.get('error'):emit(r['error'])
 layers=sorted(root.glob('layer*/power.rpt'))
 if not layers:continue
 p=layers[0].parent
 for name in ('power.rpt','activity_after.rpt','read_saif.rpt','check_power.rpt','pin_attributes.rpt'):
  f=p/name;emit('FILE '+name)
  if not f.exists():continue
  text=f.read_text(errors='replace');lines=text.splitlines()
  if name=='pin_attributes.rpt':lines=[x for x in lines if re.search(r'activity|toggle|probability',x,re.I)]
  elif name=='power.rpt':lines=[x for x in lines if re.search(r'Units|Power\s*=|power\s*=|Operating Conditions',x)]
  elif name=='read_saif.rpt':lines=lines[-15:]
  elif name=='check_power.rpt':lines=lines[:40]
  emit('\n'.join(lines))
 f=p/'macro_pin_activity.tsv'
 if f.exists():
  rows=list(csv.DictReader(f.open(),delimiter='\t'));emit('MACRO_INPUTS '+str(len(rows)))
  emit('SOURCE_COUNTS '+str(collections.Counter((x['toggle_source'],x['probability_source'])for x in rows)))
  for row in rows[:3]:emit(str(row))
 emit('WINDOWS '+str(len(r['windows'])))
 if r['windows']:emit(json.dumps(r['windows'][-1]))
