"""Compact source-identified comparison; area units remain explicit."""
from pathlib import Path
import hashlib,json,re

known={
 '7e732afb6ae3683ccf5516bc26606d2d3900d14046fe60af030f6f9d486adf7e':'baseline',
 'a3e09c079620c46b91b1cb9ea6ed756264a950c46e2617071ae3dbbe455237ab':'requant_v1',
 '3e53fea269dd62c23642b7bb397234eba0809338061301dbbfe193ba44735c17':'data_hold_v2'}
cores={}
for p in Path('/tmp').glob('q12_core_area_*/result.json'):
 r=json.loads(p.read_text());identity=r['source_identity']['files']
 for v in r['results']:
  digest=identity[v['variant']+'.sv']
  if digest not in known:continue
  report=p.parent/v['variant']/'area.rpt'
  matches=re.findall(r'^\s*Total cell area:\s*([\d.]+)',report.read_text(errors='replace'),re.M)
  metrics=dict(line.split('=',1) for line in (v['metrics'] or '').splitlines() if '=' in line)
  if not matches or not metrics:continue
  label=known[digest]
  cores[label]={'area':float(matches[-1]),'slack_ns':float(metrics['setup_slack_ns']),
       'macros':int(metrics['macro_count']),'macro_area':float(metrics['macro_area_library_units']),
       'returncode':v['returncode'],'complete':v['complete_marker'],'path':str(p.parent/v['variant']),
       'report_sha256':hashlib.sha256(report.read_bytes()).hexdigest()}
for name in ('baseline','requant_v1','data_hold_v2'):
 if name not in cores:print('CORE_PENDING',name);continue
 r=cores[name]
 print('CORE %s area_library=%.6f slack_ns=%.8f macro_count=%d macro_area=%.6f'%(name,r['area'],r['slack_ns'],r['macros'],r['macro_area']))
 if 'baseline' in cores:
  a=cores['baseline']['area'];print('SAVING %s library_area=%.6f percent=%.4f'%(name,a-r['area'],100*(a-r['area'])/a))
 print('CORE_PATH',r['path']);print('AREA_SHA256',r['report_sha256'])
for p in Path('/tmp').glob('q12_area_replay_*/result.json'):
 r=json.loads(p.read_text());digest=r.get('candidate_sha256')
 if digest not in known:continue
 tasks=r.get('tasks',[])
 print('REPLAY',known[digest],'passed',r['passed'],'phase',r['phase'],'tasks',len(tasks),'values',sum(t['values_checked'] for t in tasks))
 print('REPLAY_MEAN',r.get('mean_full_window_cycles'),'THROUGHPUT_IF_150MHZ',r.get('throughput_at_assumed_150mhz'))
 print('CYCLE_DELTAS',[t['cycle_delta'] for t in tasks])
 print('INIT_CHECKS',sum(t.get('initialized_before_use_checks',{}).get('bursts',0) for t in tasks),sum(t.get('initialized_before_use_checks',{}).get('metadata',0) for t in tasks))
 print('REPLAY_PATH',str(p));print('REPLAY_SHA256',hashlib.sha256(p.read_bytes()).hexdigest())
 if r.get('error'):print('ERROR',r['error'])
