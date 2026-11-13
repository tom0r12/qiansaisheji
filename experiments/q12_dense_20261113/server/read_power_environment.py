from pathlib import Path
import json,os,shutil,re
def out(s):
 for line in str(s).splitlines():print(' '*35+line[:150])
print('\033[2J\033[H',end='')
for name in ('pt_shell','lc_shell','dc_shell'):out('TOOL '+name+' '+str(shutil.which(name)))
for key in ('SYNOPSYS_LC_ROOT','SYNOPSYS','SYNOPSYS_PT_ROOT'):out(key+' '+str(os.environ.get(key)))
pt=Path(shutil.which('pt_shell')).resolve();out('PT_REAL '+str(pt))
for root in list(pt.parents)[:4]:
 if root==Path('/'):continue
 for pattern in ('lc*/bin/lc_shell','lc/*/bin/lc_shell','*/lc*/bin/lc_shell','*/LC*/bin/lc_shell'):
  for q in root.glob(pattern):out('LC_CANDIDATE '+str(q))
for root in Path('/tmp').glob('q12_power_probe_*'):
 for name in ('power.rpt','power_units.rpt','units.rpt','activity_after.rpt','read_macro_overlay.rpt'):
  p=root/name
  if p.exists():
   out('FILE '+str(p));text=p.read_text(errors='replace')
   if name=='power.rpt':out('\n'.join(x for x in text.splitlines()if re.search('Total Power|Internal Power|Switching Power|Leakage Power',x)))
   elif name in('units.rpt','power_units.rpt'):out('\n'.join(text.splitlines()[-15:]))
   else:out('\n'.join(text.splitlines()[-8:]))
for p in Path('/tmp').glob('q12_earlycheck_full_*/result.json'):out('CURRENT '+p.read_text()[:180])
