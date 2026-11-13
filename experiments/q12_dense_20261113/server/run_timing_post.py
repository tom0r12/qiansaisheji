"""Exact repaired-netlist equivalence and independently recorded full-window PX."""
from pathlib import Path
import concurrent.futures,datetime,fcntl,hashlib,json,os,re,shutil,signal,subprocess,sys,tempfile,time

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def put(p,r):
 q=p.with_suffix('.tmp');q.write_text(json.dumps(r,indent=2)+'\n');q.replace(p)

lock=Path('/tmp/.q12_timing_post_v1.lock').open('a+')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
out=Path(tempfile.mkdtemp(prefix='q12_timing_post_',dir='/tmp'))
print('Q12_POST_DIRECTORY',out,flush=True)
deadline=datetime.datetime(2026,11,13,9,22,tzinfo=datetime.timezone.utc).timestamp()
report={'phase':'waiting_for_mapping','passed':False,'stages':{},'scope':'TT 1.10V 25C prelayout; not routed/silicon measurement'}
def save():put(out/'result.json',report)
def remaining():
 value=deadline-time.time()
 if value<5:raise TimeoutError('Bounded session reporting deadline')
 return value
def wait_result(pattern,phase):
 while True:
  found=list(Path('/tmp').glob(pattern));assert len(found)<=1,found
  if found:
   r=read(found[0])
   if r.get('phase')==phase:return found[0].parent,r
   if r.get('phase')in ('failed','synthesis_failed'):raise RuntimeError(str(found[0])+': '+str(r.get('error',r)))
  remaining();time.sleep(10)
def command(tool,script,cwd,env,seconds,marker):
 start=time.monotonic();limit=min(seconds,remaining())
 cmd=[shutil.which(tool),'-f',str(script)];assert cmd[0],tool
 with(cwd/'tool.log').open('w')as f:
  p=subprocess.Popen(cmd,cwd=str(cwd),env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  put(cwd/'process.json',{'pid':p.pid,'command':cmd,'timeout_seconds':limit})
  try:rc=p.wait(timeout=limit)
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGTERM)
   try:rc=p.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);rc=p.wait()
 text=(cwd/'tool.log').read_text(errors='replace')
 critical=re.sub(r'^Q12_OPTIONAL_REPORT_BEGIN=([^\n]+)\n.*?^Q12_OPTIONAL_REPORT_END=\1\s*$','',text,flags=re.M|re.S)
 return {'returncode':rc,'seconds':time.monotonic()-start,'tool_complete':rc==0 and marker in text and not re.search(r'^Error:',critical,re.M),'log_sha256':sha(cwd/'tool.log')}
save()
try:
 timing,tr=wait_result('q12_native12_timing_*/result.json','mapping_complete')
 assert tr['rtl_changed']is False
 prior=Path(tr['predecessor']);package=timing/'derived_inputs';synth=timing/'synth'
 assert sha(synth/'mapped.v')==tr['netlist_sha256']
 for name,h in tr['predecessor_artifact_sha256'].items():assert sha(prior/'synth'/name)==h
 for name,h in read(package/'hardware/manifest.json')['sources_sha256'].items():assert sha(package/'hardware'/name)==h,name
 sys.path.insert(0,str(package));import audit_reports
 sys.path.insert(0,str(Path(__file__).parent));from saif_macro_bridge import build_macro_overlay
 macros=audit_reports.macro_rows(synth/'macros_mapped.tsv')
 dbs=list(tr['libraries_sha256'])
 for name,h in tr['libraries_sha256'].items():assert sha(Path(name))==h
 env=dict(os.environ,Q12_PACKAGE=str(package),Q12_LIBRARIES=' '.join(dbs),Q12_NETLIST=str(synth/'mapped.v'),Q12_SDC=str(synth/'mapped.sdc'),Q12_SVF=str(synth/'mapped.svf'),Q12_REFERENCE_NETLIST=str(prior/'synth/mapped.v'))
 report.update(phase='formal_and_activity_wait',timing_result=str(timing/'result.json'),timing_result_sha256=sha(timing/'result.json'),netlist_sha256=tr['netlist_sha256'],area_library_units=tr['area_library_units'],worst_setup_ns=tr['worst_setup_ns'],worst_hold_ns=tr['worst_hold_ns'])
 save()
 formal=(package/'formal.tcl').read_text()
 start=formal.index('    source [file join $env(Q12_PACKAGE) hardware sources.tcl]')
 end=formal.index('    foreach library',start)
 formal=formal[:start]+formal[end:]
 start=formal.index('    # Translate exactly')
 end=formal.index('    read_verilog -i',start)
 formal=formal[:start]+'    read_verilog -r -libname WORK $env(Q12_REFERENCE_NETLIST)\n    set_top r:/WORK/qingyu_e203_soc_top\n'+formal[end:]
 (out/'equivalence.tcl').write_text(formal)
 def verify():
  cwd=out/'formal';cwd.mkdir()
  rec=command('fm_shell',out/'equivalence.tcl',cwd,env,2400,'Q12_FINAL_FORMAL_COMPLETE')
  rec['scope']='Original native12 mapped checkpoint versus repaired checkpoint; RTL-to-original proof separately required'
  rec['proof_artifact_sha256']={n:sha(cwd/n)for n in ('status.rpt','failing.rpt','aborted.rpt','unverified.rpt','unmatched_after_verify.rpt','blackboxes_reference.rpt','blackboxes_implementation.rpt')if(cwd/n).exists()}
  put(cwd/'result.json',rec);return rec
 pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);future=pool.submit(verify)
 try:
  cell,cr=wait_result('q12_cell_activity_*/result.json','activity_complete')
  assert cr['unchanged_rtl_tb_and_cycles']and cr['source_vendor_result_sha256']==tr['vendor_result_sha256']
  vendor_file=Path(cr['vendor_result']);assert sha(vendor_file)==cr['vendor_result_sha256']
  vr=read(vendor_file);vendor=vendor_file.parent
  assert vr['passed']and vr['functional_passed']and len(vr['tasks'])==12
  report.update(phase='formal_and_power',activity_result=str(vendor_file),activity_result_sha256=sha(vendor_file),task_cycles=cr['task_cycles'],mean_task_cycles=cr['mean_task_cycles'],throughput_at_150mhz=150000000/cr['mean_task_cycles']);save()
  power=(package/'power.tcl').read_text()
  needle=' redirect -file read_saif.rpt {read_saif -strip_path tb_q12soc/dut $env(Q12_SAIF)}'
  assert power.count(needle)==1
  power=power.replace(needle,needle+'\n redirect -file read_macro_overlay.rpt {read_saif -strip_path tb_q12soc/dut $env(Q12_MACRO_SAIF)}')
  (out/'power.tcl').write_text(power)
  for index,task in enumerate(vr['tasks']):
   name='power_layer%02d'%index;cwd=out/name;cwd.mkdir();act=task['activity']
   assert act['scope']=='tb_q12soc/dut'and act['timescale_ps']==1
   assert act['end_ps']-act['start_ps']==act['duration_ps']>0
   saif=(vendor/act['saif_relpath']).resolve()
   assert vendor.resolve()in saif.parents and sha(saif)==act['saif_sha256']
   text=saif.read_text();dur=re.search(r'\(DURATION\s+(\d+)\s*\)',text);scale=re.search(r'\(TIMESCALE\s+(\d+)\s+ps\s*\)',text)
   assert dur and scale and int(dur[1])*int(scale[1])==act['duration_ps']
   overlay,mapping=build_macro_overlay(text,macros)
   assert mapping['macro_count']==116 and mapping['changed_activity_values']is False
   overlay_path=cwd/'macro_overlay.saif';overlay_path.write_text(overlay)
   put(cwd/'activity_mapping.json',mapping)
   rec=command('pt_shell',out/'power.tcl',cwd,dict(env,Q12_SAIF=str(saif),Q12_MACRO_SAIF=str(overlay_path)),420,'Q12_FINAL_POWER_REPORTS_COMPLETE')
   rec.update(task=task['task'],duration_ps=act['duration_ps'],accepted=False,saif_sha256=sha(saif),macro_overlay_sha256=sha(overlay_path))
   if rec['tool_complete']:
    try:
     watts=audit_reports.power_value((cwd/'power.rpt').read_text(),(cwd/'power_units.rpt').read_text())
     rec['provisional_unqualified']={'power_w':watts,'energy_uj':watts*act['duration_ps']*1e-6}
    except Exception as e:rec['units_error']=str(e)
    try:rec.update(audit_reports.power(cwd,act['duration_ps']),accepted=True)
    except Exception as e:rec['acceptance_error']=str(e)
   report['stages'][name]=rec;save();print(name,json.dumps(rec),flush=True)
   if future.done():report['stages']['formal']=future.result();save()
  report['phase']='power_reports_complete';save()
 except BaseException as e:
  report['power_error']=str(e);report['phase']='power_failed_formal_pending';save();print('POWER_FAILED',repr(e),flush=True)
 finally:
  try:report['stages']['formal']=future.result()
  except Exception as e:report['stages']['formal']={'tool_complete':False,'error':str(e)}
  pool.shutdown(wait=True)
 previous_formal=prior/'formal/tool.log'
 report['rtl_to_original_formal_tool_complete']=previous_formal.exists()and'Q12_FINAL_FORMAL_COMPLETE'in previous_formal.read_text(errors='replace')
 powers=[v for k,v in report['stages'].items()if k.startswith('power_layer')]
 if len(powers)==12 and all('provisional_unqualified'in v for v in powers):report['mean_energy_uj_unqualified']=sum(v['provisional_unqualified']['energy_uj']for v in powers)/12
 if len(powers)==12 and all(v['accepted']for v in powers):report['mean_energy_uj']=sum(v['energy_uj']for v in powers)/12
 report['phase']='reports_complete';report['review_required']='Review final constraints, pin-activity provenance, formal scope and original proof before declaring complete';save()
 print('Q12_POST_REPORTS_COMPLETE',out/'result.json',flush=True)
except BaseException as e:
 report.update(phase='failed',error=str(e));save();raise
