from pathlib import Path
import json,re,hashlib

for prefix in ('q12_quant_package_','q12_area_package_','q12_core_package_'):
    files=sorted(Path('/tmp').glob(prefix+'*/run.log'),key=lambda p:p.stat().st_mtime)
    for p in files[-2:]:
        print('LAUNCH_LOG='+str(p))
        for line in p.read_text(errors='replace').splitlines():
            if 'DIRECTORY=' in line or 'Traceback' in line or 'Error:' in line or 'ValueError' in line:print(line)
for prefix in ('q12_quant_area_','q12_area_replay_','q12_core_area_'):
    files=sorted(Path('/tmp').glob(prefix+'*/result.json'),key=lambda p:p.stat().st_mtime)
    for p in files[-2:]:
        r=json.loads(p.read_text());print('RESULT='+str(p))
        if 'results' in r:
            for v in r['results']:
                name=v.get('top',v.get('variant'));base=p.parent/name
                area=base/'area.rpt';text=area.read_text(errors='replace') if area.is_file() else ''
                matches=re.findall(r'^\s*Total cell area:\s*([\d.]+)',text,re.M)
                print(json.dumps(v));print('REPORT_CELL_AREA='+str(matches))
                if area.is_file():print('AREA_REPORT_SHA256='+hashlib.sha256(area.read_bytes()).hexdigest())
        else:
            print(json.dumps({k:r.get(k) for k in ('candidate','passed','phase','error','mean_full_window_cycles','throughput_at_assumed_150mhz')}))
            print('TASKS='+str(len(r.get('tasks',[])))+' VALUES='+str(sum(t['values_checked'] for t in r.get('tasks',[]))))
            print('CYCLE_DELTAS='+str([t['cycle_delta'] for t in r.get('tasks',[])]))
            print('RESULT_SHA256='+hashlib.sha256(p.read_bytes()).hexdigest())
            if r.get('init_monitor_sha256'):print('INIT_CHECK_COUNTS='+str([t.get('initialized_before_use_checks') for t in r.get('tasks',[])]))
    if prefix=='q12_core_area_' and not files:
        logs=sorted(Path('/tmp').glob(prefix+'*/*/dc.log'),key=lambda p:p.stat().st_mtime)
        for p in logs[-1:]: print('CORE_PROGRESS_LOG='+str(p));print('\n'.join(p.read_text(errors='replace').splitlines()[-8:]))
