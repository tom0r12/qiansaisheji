"""Repeat identical tasks with explicit library/celldefine debug visibility."""
from pathlib import Path
import fcntl,hashlib,json,os,re,shutil,signal,subprocess,tempfile,time,sys
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def put(p,r):
 q=p.with_suffix('.tmp');q.write_text(json.dumps(r,indent=2)+'\n');q.replace(p)
lock=Path('/tmp/.q12_native12_cell_activity_v1.lock').open('a+')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
matches=[]
for p in Path('/tmp').glob('q12_native12_*/result.json'):
 r=read(p)
 if r.get('phase')=='activity_complete'and r.get('identity',{}).get('files',{}).get('run_dense.py')=='491bc0cb2d24ca7fb230c0bd5d70b545012d2b3a7272a8b71d8016cd32c89b8b':matches.append((p,r))
assert len(matches)==1,matches
parent,previous=matches[0];previous_vendor=Path(previous['vendor_result']);old=read(previous_vendor)
assert sha(previous_vendor)==previous['vendor_result_sha256']and old['functional_passed']and len(old['tasks'])==12
out=Path(tempfile.mkdtemp(prefix='q12_cell_activity_',dir='/tmp'));package=out/'vendor_inputs'
shutil.copytree(str(parent.parent/'vendor_inputs'),str(package))
manifest=read(package/'manifest.json')
for name,h in manifest['files_sha256'].items():assert sha(package/name)==h,name
original_sources={n:sha(package/n)for n in manifest['source_order']}
runner=(package/'run_vendor.py').read_text()
needle="'-debug_access+all','-top'"
assert runner.count(needle)==1
runner=runner.replace(needle,"'-debug_access+all','-debug_region+cell+lib','-top'")
(package/'run_vendor.py').write_text(runner)
manifest['activity_instrumentation']={'baseline_vendor_result':str(previous_vendor),'baseline_vendor_result_sha256':sha(previous_vendor),
 'change':'VCS -debug_region+cell+lib; RTL, TB, stimuli and expected outputs unchanged'}
manifest['files_sha256']={n:sha(package/n)for n in manifest['files_sha256']}
put(package/'manifest.json',manifest)
report={'phase':'vendor_replay','passed':False,'source_vendor_result':str(previous_vendor),
 'source_vendor_result_sha256':sha(previous_vendor),'rtl_and_tb_sha256':original_sources,
 'instrumentation':'-debug_access+all -debug_region+cell+lib','stages':{}}
put(out/'result.json',report);print('Q12_CELL_ACTIVITY_DIRECTORY',out,flush=True)
try:
 with(out/'vendor.log').open('w')as log:
  cmd=[sys.executable,str(package/'run_vendor.py'),'--tasks','12','--saif','--work-root',str(out)]
  p=subprocess.Popen(cmd,cwd=str(out),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  put(out/'process.json',{'pid':p.pid,'command':cmd})
  try:rc=p.wait(timeout=2400)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);rc=p.wait(timeout=30)
 assert rc==0,'Cell-visible replay failed; see vendor.log'
 results=list(out.glob('qingyu_q12_final_vendor_*/result.json'));assert len(results)==1
 vr=read(results[0]);assert vr['passed']and vr['functional_passed']and len(vr['tasks'])==12
 before=[t['metrics']['full_window_cycles']for t in old['tasks']]
 after=[t['metrics']['full_window_cycles']for t in vr['tasks']]
 assert before==after,(before,after)
 assert {n:sha(package/n)for n in original_sources}==original_sources
 report.update(phase='activity_complete',passed=True,vendor_result=str(results[0]),vendor_result_sha256=sha(results[0]),task_cycles=after,
               mean_task_cycles=sum(after)/12,unchanged_rtl_tb_and_cycles=True)
 put(out/'result.json',report);print('Q12_CELL_ACTIVITY_COMPLETE',json.dumps(report),flush=True)
except BaseException as e:
 report.update(phase='failed',error=str(e));put(out/'result.json',report);raise
