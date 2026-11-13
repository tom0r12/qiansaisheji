"""Read existing reports without changing the running EDA jobs."""
from pathlib import Path
import json,re
import subprocess

roots=sorted(Path('/tmp').glob('q12_native12_full_*/result.json'))
assert len(roots)==1,roots
root=roots[0].parent
r=json.loads(roots[0].read_text())
print('REPORT_ROOT',root,'PHASE',r['phase'])
for name in ('timing_max.rpt','timing_min.rpt'):
 p=root/'synth'/name
 text=p.read_text()
 print('\nREPORT',p)
 seen=set()
 for block in text.split('Startpoint:')[1:]:
  m=re.search(r'Path Group:\s*(\S+)',block)
  if not m or m[1] in seen:continue
  seen.add(m[1])
  lines=block.splitlines()
  print('Startpoint:'+ '\n'.join(lines[:9]))
  print('\n'.join(lines[-12:]))
print('\nCONSTRAINTS')
p=root/'synth/constraints.rpt'
ct=p.read_text().splitlines()
for i,line in enumerate(ct):
 if 'max_delay/' in line or 'min_delay/' in line:print('\n'.join(ct[i:i+11]))
print('\nFORMAL_LOG_TAIL')
p=root/'formal/tool.log'
if p.exists():print('\n'.join(p.read_text(errors='replace').splitlines()[-20:]))
for p in sorted(root.glob('power_layer*/tool.log')):
 print('POWER_LOG',p,'\n'.join(p.read_text(errors='replace').splitlines()[-4:]))
for k,v in r.get('stages',{}).items():
 if k!='synth':print('RESULT',k,json.dumps(v,sort_keys=True))
identity=json.loads((root/'derived_identity.json').read_text())
vendor=Path(identity['vendor_result'])
vr=json.loads(vendor.read_text())
print('ACTIVITY_FIELDS',json.dumps(vr['tasks'][0].get('activity',{}),sort_keys=True))
print('POWER_DIRECTORY_FILES',[(str(p),[x.name for x in p.iterdir()])for p in root.glob('power_layer*')])
for p in root.rglob('process.json'):
 q=json.loads(p.read_text());print('PROCESS',p)
 print(subprocess.check_output(['ps','-p',str(q['pid']),'-o','pid,ppid,etime,time,pcpu,stat,comm'],universal_newlines=True).strip())
