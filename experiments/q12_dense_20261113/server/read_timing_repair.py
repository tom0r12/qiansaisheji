from pathlib import Path
import json,re
roots=list(Path('/tmp').glob('q12_native12_timing_*/result.json'));assert len(roots)==1
p=roots[0].parent;print('ROOT',p)
r=json.loads(roots[0].read_text());print('RESULT',r['phase'],r.get('worst_setup_ns'),r.get('worst_hold_ns'))
for name in ('timing_min.rpt','check_timing.rpt','constraints.rpt'):
 text=(p/'synth'/name).read_text();print('\nFILE',name)
 if name=='timing_min.rpt':
  seen=set()
  for block in text.split('Startpoint:')[1:]:
   end=re.search(r'Endpoint:\s*(\S+)',block)
   if not end:continue
   key=re.sub(r'\[[0-9]+\]','[]',end[1])
   if key in seen:continue
   seen.add(key);print('Startpoint:'+block)
   if len(seen)>=4:break
 else:print(text[:6000])
for f in Path('/tmp').glob('q12_cell_activity_*/result.json'):
 v=json.loads(f.read_text());print('CELL_ACTIVITY',f,v['phase'],v.get('error'))
 for q in f.parent.glob('qingyu_q12_final_vendor_*/result.json'):
  a=json.loads(q.read_text());print('TASKS',len(a.get('tasks',[])),a.get('phase'))
  if a.get('tasks'):
   act=a['tasks'][0].get('activity',{});saif=q.parent/act.get('saif_relpath','MISSING')
   if saif.is_file():
    s=saif.read_text();print('SAIF',saif,'MACRO_MARKERS',s.count('macro_ram'),'INSTANCE_COUNT',s.count('(INSTANCE'))
