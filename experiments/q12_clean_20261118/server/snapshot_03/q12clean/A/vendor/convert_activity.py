"""Convert each actual VCD's exact full-task timestamps; preserve partial/failure evidence."""
from pathlib import Path
from decimal import Decimal
import argparse,json,re,hashlib,shutil,subprocess,os,signal
UNIT_PS={'s':Decimal('1e12'),'ms':Decimal('1e9'),'us':Decimal('1e6'),'ns':Decimal('1e3'),'ps':Decimal(1),'fs':Decimal('.001')}
def digest(path):
 h=hashlib.sha256()
 with path.open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def saif_header(text,expected):
 ts=re.search(r'\(TIMESCALE\s+([\d.]+)\s+(fs|ps|ns|us|ms|s)\s*\)',text)
 duration=re.search(r'\(DURATION\s+([\d.]+)\s*\)',text)
 if not ts or not duration:raise ValueError('SAIF window header missing')
 unit=Decimal(ts[1])*UNIT_PS[ts[2]]
 observed=Decimal(duration[1])*unit
 if unit!=1:raise ValueError('SAIF must retain exact 1ps timescale')
 if observed!=Decimal(expected):raise ValueError('SAIF duration differs from exact full timestamp window')
 return str(observed)
def convert(run_dir,timeout):
 report=json.loads((run_dir/'result.json').read_text())
 if not(report.get('functional_passed')or report.get('passed'))or not report.get('activity_requested'):raise ValueError('Successful explicit functional activity run required')
 tool=shutil.which('vcd2saif')
 if not tool:raise ValueError('vcd2saif is not on PATH')
 if timeout<1:raise ValueError('Positive SAIF timeout required')
 result={'passed':False,'phase':'conversion','scope':'Actual full-window RTL/manufacturer activity only; mapped coverage and power must be separately verified.','source_result_sha256':digest(run_dir/'result.json'),'frozen_result_sha256':report['frozen_result_sha256'],'manifest_sha256':report['manifest_sha256'],'tool':str(Path(tool).resolve()),'tool_sha256':digest(Path(tool).resolve()),'tasks':[]}
 evidence=run_dir/'activity_conversion.json'
 def save():evidence.write_text(json.dumps(result,indent=2)+'\n')
 save();current=None
 try:
  for task in report['tasks']:
   current=task['task'];a=task['activity'];vcd=Path(a['vcd']);case=run_dir/task['directory']
   if vcd.resolve().parent!=case.resolve():raise ValueError('Activity path belongs to wrong task')
   if vcd.stat().st_size!=a['bytes']:raise ValueError('VCD size changed')
   with vcd.open(errors='replace')as f:header=f.read(65536)
   m=re.search(r'\$timescale\s+(\d+)\s*(fs|ps|ns|us|ms|s)\s+\$end',header)
   if not m:raise ValueError('VCD timescale not found')
   unit=Decimal(m[1])*UNIT_PS[m[2]]
   if unit!=1:raise ValueError('VCD must retain exact 1ps precision')
   if a['end_ps']-a['start_ps']!=a['duration_ps']:raise ValueError('VCD timestamp arithmetic mismatch')
   saif=case/'full_runtime.saif';log=case/'vcd2saif.log'
   if saif.exists():raise ValueError('Refuse overwrite of existing SAIF; preserve prior evidence')
   vcd_hash=digest(vcd)
   cmd=[tool,'-64','-input',str(vcd),'-output',str(saif),'-time',str(a['start_ps']),str(a['end_ps'])]
   pending={'task':current,'passed':False,'phase':'conversion','command':cmd,'start_ps':a['start_ps'],'end_ps':a['end_ps']}
   (case/'activity_result.json').write_text(json.dumps(pending,indent=2)+'\n')
   with log.open('w')as f:
    p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    try:rc=p.wait(timeout=timeout)
    except BaseException:
     try:os.killpg(p.pid,signal.SIGTERM)
     except ProcessLookupError:pass
     try:p.wait(timeout=5)
     except subprocess.TimeoutExpired:
      try:os.killpg(p.pid,signal.SIGKILL)
      except ProcessLookupError:pass
      p.wait()
     raise
   if rc or not saif.is_file()or saif.stat().st_size<100:raise ValueError('SAIF conversion failed: '+str(log))
   if re.search(r'(?im)^\s*(?:Fatal:|Error:|Error-\[)',log.read_text(errors='replace')):raise ValueError('SAIF converter logged an error')
   with saif.open(errors='replace')as f:s=f.read(65536)
   observed=saif_header(s,a['duration_ps'])
   if not re.search(r'\(INSTANCE\s+tb_q12soc\b',s)or not re.search(r'\(INSTANCE\s+dut\b',s):raise ValueError('Expected tb_q12soc/dut SAIF hierarchy missing')
   if digest(vcd)!=vcd_hash:raise ValueError('VCD mutated during conversion')
   record={'task':current,'passed':True,'phase':'complete','command':cmd,'activity':{'saif_relpath':saif.relative_to(run_dir).as_posix(),'saif_sha256':digest(saif),'vcd_sha256':vcd_hash,'start_ps':a['start_ps'],'end_ps':a['end_ps'],'duration_ps':int(observed),'scope':'tb_q12soc/dut','timescale_ps':1},'log_sha256':digest(log)}
   (case/'activity_result.json').write_text(json.dumps(record,indent=2)+'\n')
   result['tasks'].append(record);save()
   print('Q12_FINAL_SAIF '+current+' '+str(saif),flush=True)
  result.update(passed=True,phase='complete');save();return result
 except BaseException as exc:
  result.update(passed=False,phase='failed',failed_task=current,error=str(exc));save()
  if current is not None:(case/'activity_result.json').write_text(json.dumps({'passed':False,'phase':'failed','task':current,'error':str(exc)},indent=2)+'\n')
  raise
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('run_dir',type=Path);p.add_argument('--timeout',type=int,default=1800);a=p.parse_args()
 print(json.dumps(convert(a.run_dir.resolve(),a.timeout),indent=2))
