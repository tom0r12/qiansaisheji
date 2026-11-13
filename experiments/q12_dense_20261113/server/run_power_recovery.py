"""Bounded PT compatibility rerun on the exact early-check mapped candidate.

Reads the original cell-aware SAIF. The hierarchy bridge is an identity audit
only; its generated overlay is never supplied to PrimeTime.
"""
from pathlib import Path
import datetime,fcntl,hashlib,json,os,re,shutil,signal,subprocess,sys,tempfile,time

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,r):
 q=p.with_suffix('.tmp');q.write_text(json.dumps(r,indent=2)+'\n');q.replace(p)
lock=Path('/tmp/.q12_power_recovery_v2.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
out=Path(tempfile.mkdtemp(prefix='q12_power_recovery_',dir='/tmp'))
deadline=datetime.datetime(2026,11,13,9,22,tzinfo=datetime.timezone.utc).timestamp()
roots=list(Path('/tmp').glob('q12_earlycheck_full_*/result.json'));assert len(roots)==1
parent=roots[0].parent;package=parent/'derived_inputs';synth=parent/'synth'
report={'phase':'waiting_mapping','accepted':False,'parent':str(parent),'windows':[]}
def save():put(out/'result.json',report)
save();print('POWER_RECOVERY',out,flush=True)
try:
 r=read(roots[0]);assert r['engine_sha256']=='9447724c51ee9e4e80e72818cf1a448002b485fb00956be98d3f1a9f5848d432'
 # Preserve and explicitly delegate the old incompatible power stage.
 original=package/'power_before_compat.tcl'
 if not original.exists():
  shutil.copy2(str(package/'power.tcl'),str(original))
  plan={'reason':'PT 2022 report_units -power unsupported; original cell-aware SAIF needs no overlay',
        'recovery':str(out),'original_power_sha256':sha(original),'rtl_or_timing_changed':False}
  plan['main_power_already_started']=r['phase']!='synthesis_and_vendor'
  put(parent/'power_recovery_plan.json',plan)
  if r['phase']=='synthesis_and_vendor':
   (package/'power.tcl').write_text('# Power delegated to '+str(out)+'; see power_recovery_plan.json\n')
 while True:
  assert time.time()<deadline-180,'Deadline before mapping'
  r=read(roots[0]);stage=r.get('stages',{}).get('synth',{})
  if stage.get('tool_complete')and(synth/'mapped.sdc').exists():break
  if r.get('phase')=='failed':raise RuntimeError(r.get('error','Main flow failed'))
  time.sleep(15)
 assert stage['tool_complete']
 report.update(phase='power_windows',engine_sha256=r['engine_sha256'],netlist_sha256=sha(synth/'mapped.v'),sdc_sha256=sha(synth/'mapped.sdc'),libraries_sha256=r['libraries_sha256'])
 vrec=read(parent/'vendor_completed.json');vf=Path(vrec['vendor_result']);assert sha(vf)==vrec['vendor_result_sha256'];v=read(vf)
 assert v['passed']and v['functional_passed']and len(v['tasks'])==12
 report['vendor_result_sha256']=sha(vf);report['cycles']=vrec['task_cycles']
 sys.path.insert(0,str(package));import audit_reports
 deps=list(Path('/tmp').glob('q12_early_launch_*/saif_macro_bridge.py'));assert len(deps)==1
 sys.path.insert(0,str(deps[0].parent));from saif_macro_bridge import build_macro_overlay
 macros=audit_reports.macro_rows(synth/'macros_mapped.tsv')
 power=original.read_text();assert power.count('report_units -power')==1
 power=power.replace('report_units -power','report_units')
 power=power.replace(' set power_enable_analysis true',' set_host_options -max_cores 4\n set power_enable_analysis true')
 (out/'power.tcl').write_text(power)
 lc=Path(shutil.which('lc_shell')).resolve().parent.parent;assert(lc/'bin/lc_shell').exists()
 env=dict(os.environ,SYNOPSYS_LC_ROOT=str(lc),Q12_PACKAGE=str(package),Q12_LIBRARIES=' '.join(r['libraries_sha256']),Q12_NETLIST=str(synth/'mapped.v'),Q12_SDC=str(synth/'mapped.sdc'))
 report['library_compiler_root']=str(lc);save()
 for i,task in enumerate(v['tasks']):
  assert time.time()<deadline-30,'Deadline during power windows'
  cwd=out/('layer%02d'%i);cwd.mkdir();act=task['activity'];saif=vf.parent/act['saif_relpath']
  assert sha(saif)==act['saif_sha256']and act['scope']=='tb_q12soc/dut'
  text=saif.read_text();duration=int(re.search(r'\(DURATION\s+(\d+)\s*\)',text)[1]);scale=int(re.search(r'\(TIMESCALE\s+(\d+)\s+ps\s*\)',text)[1])
  assert duration*scale==act['duration_ps']==act['end_ps']-act['start_ps']>0
  _unused,mapping=build_macro_overlay(text,macros);assert mapping['macro_count']==116
  mapping['overlay_used']=False;put(cwd/'activity_identity.json',mapping)
  start=time.monotonic()
  with(cwd/'tool.log').open('w')as f:
   p=subprocess.Popen([shutil.which('pt_shell'),'-f',str(out/'power.tcl')],cwd=str(cwd),env=dict(env,Q12_SAIF=str(saif)),stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
   put(cwd/'process.json',{'pid':p.pid})
   try:rc=p.wait(timeout=min(300,deadline-time.time()))
   except subprocess.TimeoutExpired:
    os.killpg(p.pid,signal.SIGTERM)
    try:rc=p.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);rc=p.wait()
  log=(cwd/'tool.log').read_text(errors='replace')
  critical=re.sub(r'^Q12_OPTIONAL_REPORT_BEGIN=([^\n]+)\n.*?^Q12_OPTIONAL_REPORT_END=\1\s*$','',log,flags=re.M|re.S)
  rec={'layer':i,'returncode':rc,'seconds':time.monotonic()-start,'duration_ps':act['duration_ps'],'saif_sha256':sha(saif),'tool_complete':rc==0 and'Q12_FINAL_POWER_REPORTS_COMPLETE'in log and not re.search(r'^Error:',critical,re.M),'accepted':False}
  if(cwd/'power.rpt').exists():
   pr=(cwd/'power.rpt').read_text();unit_lines='\n'.join(x for x in pr.splitlines()if re.search(r'power\s+units?',x,re.I))
   rec['reported_unit_lines']=unit_lines
   try:
    watts=audit_reports.power_value(pr,unit_lines);rec['provisional_unqualified']={'power_w':watts,'energy_uj':watts*act['duration_ps']*1e-6}
   except Exception as e:rec['unit_error']=str(e)
  if rec['tool_complete']:
   try:
    # Keep the strict gate unchanged; release-specific coverage is reviewed separately.
    rec['strict_audit']=audit_reports.power(cwd,act['duration_ps']);rec['accepted']=True
   except Exception as e:rec['acceptance_error']=str(e)
  report['windows'].append(rec);save();print('WINDOW',json.dumps(rec),flush=True)
  if not rec['tool_complete']:
   report['first_tool_error']='\n'.join(x for x in critical.splitlines()if x.startswith('Error:'));save();raise RuntimeError('PT tool failed; inspect exact diagnostics')
 if all('provisional_unqualified'in x for x in report['windows']):
  energy=sum(x['provisional_unqualified']['energy_uj']for x in report['windows'])
  duration=sum(x['duration_ps']for x in report['windows'])
  report.update(mean_energy_uj_unqualified=energy/12,weighted_power_w_unqualified=energy*1e6/duration)
 report.update(phase='reports_complete',accepted=all(x['accepted']for x in report['windows']));save();print('POWER_RECOVERY_COMPLETE',json.dumps(report),flush=True)
except BaseException as e:
 report.update(phase='failed',error=repr(e));save();raise
