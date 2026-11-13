"""Exact native12 full-SoC mapping, equivalence, timing and twelve-window PX."""
from pathlib import Path
import concurrent.futures,fcntl,hashlib,json,os,re,shutil,signal,subprocess,sys,tempfile,time
BASE_PACKAGE='7298386858c65eea09b3aa0a475bcdfa9fcb030e0c4c4bcc15f3ad70ef02a876'
EXPECTED={'q12_task4.sv': '9d27b146bb61f3641d05cad2a615121cc23d3e6a936c0013489d5daa6c01e402', 'q12_rice_decoder.sv': '65a2c8e2b9ee54c6be330d55d7e857ae0544bdbb1d09fe6c44cced5b5b52d8bf', 'q12_stream_engine_overlap.sv': '90b1661e15ab3ad1baf6ff8cd9945e917920254e51955af693cd13d4fe1f5814', 'q12_icb_stream_prefix.sv': '0dd56f2e7aec082157eb5708e4350f0f33c611ea96c892e7c4ba913c4a11edef', 'q12_dense12_writer.sv': '3d770374be8fc8370956edbd4c4d2952c0ed5599acc7684c1f620ee2eb3528a4', 'run_dense.py': 'a63d7606a2761e54f397c1ef54d7041a9d4704a03ae428de54afe65f0e1b26c3'}
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def put(p,r):
 q=p.with_suffix('.tmp');q.write_text(json.dumps(r,indent=2)+'\n');q.replace(p)

lock=Path('/tmp/.q12_compact12_full_90b1661e15ab.lock').open('a+')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
print('WAITING_FOR_EXACT_NATIVE12_ACTIVITY',flush=True)
deadline=time.monotonic()+21600
while True:
 candidates=[]
 for p in Path('/tmp').glob('q12_compact12_*/result.json'):
  r=read(p);files=r.get('identity',{}).get('files',{})
  if all(files.get(n)==h for n,h in EXPECTED.items()):
   if r.get('phase')=='failed':raise RuntimeError('Vendor predecessor failed: '+str(p))
   if r.get('phase')=='activity_complete' and r.get('functional_passed'):candidates.append((p,r))
 if candidates:break
 if time.monotonic()>deadline:raise TimeoutError('No successful source-matched vendor activity')
 time.sleep(10)
assert len(candidates)==1,candidates
predecessor,pre=candidates[0];vendor_file=Path(pre['vendor_result']);vendor=vendor_file.parent;vr=read(vendor_file)
assert sha(vendor_file)==pre['vendor_result_sha256'] and vr['passed'] and vr['functional_passed']
assert len(vr['tasks'])==12
assert pre['mean_full_window_cycles']>0
vendor_sources=predecessor.parent/'vendor_inputs'
baseline=[p.parent for p in Path('/tmp/q12_final_s4_36usr_20261113').glob('*/package_identity.json')if sha(p)==BASE_PACKAGE]
assert len(baseline)==1,baseline
baseline=baseline[0];original=read(baseline/'package_identity.json')
for n,h in original['files'].items():assert sha(baseline/n)==h,n
# Keep only one of our full-SoC DC jobs active at a time.
print('WAITING_FOR_NATIVE12_SYNTHESIS',flush=True)
deadline=time.monotonic()+21600
while True:
 prior=[read(p)for p in Path('/tmp').glob('q12_native12_full_*/result.json')]
 assert len(prior)==1,prior
 if prior[0].get('stages',{}).get('synth',{}).get('tool_complete'):break
 if prior[0].get('phase')=='failed':raise RuntimeError('Native12 synthesis failed; diagnose before repeating')
 if time.monotonic()>deadline:raise TimeoutError('Previous synthesis has not completed')
 time.sleep(15)
out=Path(tempfile.mkdtemp(prefix='q12_compact12_full_',dir='/tmp'))
print('Q12_COMPACT_FULL_DIRECTORY='+str(out),flush=True)
package=out/'derived_inputs';shutil.copytree(str(baseline),str(package))
overrides={'hardware/src/output/eda/q12_candidate/core_datareset/q12_task4.sv': ('src/q12/core_datareset/q12_task4.sv', '9d27b146bb61f3641d05cad2a615121cc23d3e6a936c0013489d5daa6c01e402'), 'hardware/src/output/eda/q12_candidate/decoder2/q12_rice_decoder.sv': ('src/q12/decoder2/q12_rice_decoder.sv', '65a2c8e2b9ee54c6be330d55d7e857ae0544bdbb1d09fe6c44cced5b5b52d8bf'), 'hardware/src/output/eda/q12_candidate/integration/q12_stream_engine_overlap.sv': ('src/q12/integration/q12_stream_engine_overlap.sv', '90b1661e15ab3ad1baf6ff8cd9945e917920254e51955af693cd13d4fe1f5814'), 'hardware/src/output/eda/q12_candidate/integration/q12_icb_stream_prefix.sv': ('src/q12/integration/q12_icb_stream_prefix.sv', '0dd56f2e7aec082157eb5708e4350f0f33c611ea96c892e7c4ba913c4a11edef'), 'hardware/src/output/eda/q12_candidate/encoder_bounded/q13_rice_encoder.sv': ('src/q12/encoder_bounded/q13_rice_encoder.sv', '3d770374be8fc8370956edbd4c4d2952c0ed5599acc7684c1f620ee2eb3528a4')}
for dest,(source,digest)in overrides.items():
 assert sha(vendor_sources/source)==digest
 shutil.copy2(str(vendor_sources/source),str(package/dest))
actual={n:sha(package/n)for n in original['files']}
assert set(n for n,h in actual.items()if h!=original['files'][n])==set(overrides)
# Only compile effort changes; the full hierarchy, macro inventory, all ports,
# clocks, I/O budgets and absence of timing exceptions remain the same.
mapping=(package/'map.tcl').read_text()
assert mapping.count('compile -map_effort medium')==1
mapping=mapping.replace('compile -map_effort medium','compile -map_effort high')
mapping=mapping.replace(' puts Q12_COMPILE_BEGIN',' set_fix_hold [all_clocks]\n puts Q12_COMPILE_BEGIN')
# Preserve unrestricted diagnostics, then analyze the same documented
# functional debug straps as the task testbench. No false paths are introduced.
modes='set modes [get_ports {io_pads_dbgmode0_n_i_ival io_pads_dbgmode1_n_i_ival io_pads_dbgmode2_n_i_ival}]\n if {[sizeof_collection $modes]!=3} {error "Three debug straps required"}\n set_case_analysis 1 $modes\n'
mapping=mapping.replace(' redirect -file area.rpt', ' redirect -file unrestricted_setup.rpt {report_timing -delay_type max -max_paths 100 -significant_digits 8}\n '+modes+' redirect -file area.rpt')
(package/'map.tcl').write_text(mapping)
power=(package/'power.tcl').read_text();needle=' read_sdc $env(Q12_SDC)'
assert needle in power
power=power.replace(needle,needle+'\n '+modes)
(package/'power.tcl').write_text(power)
# Update exact expected macro counts in all independent checkers, retaining
# every source, path, unit, coverage, and formal equivalence gate.
changes={
 'audit.tcl':[('All 116 macros','All 112 macros'),('RAMSP128X16 30','RAMSP128X16 26'),('$stage 30 6 80','$stage 26 6 80')],
 'hardware/report_explicit_area.tcl':[('RAMSP128X16 30','RAMSP128X16 26')],
 'audit_reports.py':[("'RAMSP128X16':30","'RAMSP128X16':26"),('len(macros)!=116','len(macros)!=112')],
 'validate_activity.py':[("'RAMSP128X16':30","'RAMSP128X16':26"),('not30/6/80','not26/6/80'),("'macro_instance_paths_matched':116","'macro_instance_paths_matched':112"),('116macro','112macro')],
 'formal_audit.py':[("'RAMSP128X16': 30","'RAMSP128X16': 26"),('30/6/80','26/6/80')]
}
for name,pairs in changes.items():
 p=package/name;s=p.read_text()
 for a,b in pairs:
  assert a in s,(name,a);s=s.replace(a,b)
 p.write_text(s)
hw=read(package/'hardware/manifest.json')
hw['baseline_expected_macros']=hw['expected_macros'];hw['expected_macros']={'RAMSP128X16':26,'RAMSP1024X16':6,'RAMSP4096X16':80}
hw['baseline_soc_result_sha256']=hw['soc_result_sha256'];hw['soc_result_sha256']=sha(vendor_file)
for n in hw['sources_sha256']:hw['sources_sha256'][n]=sha(package/'hardware'/n)
put(package/'hardware/manifest.json',hw)
identity={'candidate':'q12_x12_w10_y12_native_write_priority_compact_weights','baseline_package_identity_sha256':BASE_PACKAGE,
 'baseline_files':original['files'],'macro_inventory_change':'Private weights only: 30/6/80 to 26/6/80; all checkers remain exact','actual_files':{n:sha(package/n)for n in original['files']},
 'rtl_overrides':overrides,'synthesis_change':'map_effort high with hold repair; original clock/I-O budgets and hierarchy; reports use task debug straps 111; raw setup retained',
 'vendor_result':str(vendor_file),'vendor_result_sha256':sha(vendor_file)}
put(out/'derived_identity.json',identity)
desktop=Path.home()/'Desktop'
std=desktop/'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db'
dbs=[std]+[desktop/('qingyu_sram_corners/RAMSP%dX16_tt_1p10v_1p10v_25c.db'%n)for n in(128,1024,4096)]
for p in dbs:assert p.is_file(),p
env=dict(os.environ,Q12_PACKAGE=str(package),Q12_LIBRARIES=' '.join(str(p)for p in dbs))
env.update(dict(zip(['Q12_STD_DB','Q12_RAM128_DB','Q12_RAM1024_DB','Q12_RAM4096_DB'],map(str,dbs))))
sys.path.insert(0,str(package))
import audit_reports,formal_audit
from validate_activity import check_saif
report={'passed':False,'phase':'synthesis','identity_sha256':sha(out/'derived_identity.json'),
 'vendor_result_sha256':sha(vendor_file),'mean_full_window_cycles':pre['mean_full_window_cycles'],
 'conditional_throughput_150mhz':150000000/pre['mean_full_window_cycles'],
 'libraries_sha256':{str(p):sha(p)for p in dbs},'stages':{},
 'limits':['Official TT prelayout model, not routed or silicon measurement','NP3 organizer acceptance remains OPEN']}
def save():put(out/'result.json',report)
def command(tool,script,cwd,localenv,seconds,marker):
 cmd=[shutil.which(tool),'-f',str(script)];assert cmd[0],tool
 start=time.monotonic()
 with(cwd/'tool.log').open('w')as log:
  process=subprocess.Popen(cmd,cwd=str(cwd),env=localenv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  put(cwd/'process.json',{'pid':process.pid,'command':cmd,'deadline_seconds':seconds})
  try:rc=process.wait(timeout=seconds)
  except BaseException:
   try:os.killpg(process.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:process.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
   raise
 text=(cwd/'tool.log').read_text(errors='replace')
 critical=re.sub(r'^Q12_OPTIONAL_REPORT_BEGIN=([^\n]+)\n.*?^Q12_OPTIONAL_REPORT_END=\1\s*$','',text,flags=re.M|re.S)
 return {'returncode':rc,'seconds':time.monotonic()-start,'tool_complete':rc==0 and marker in text and not re.search(r'^Error:',critical,re.M),
 'log_sha256':sha(cwd/'tool.log')}
save();synth=out/'synth';synth.mkdir()
try:
 report['stages']['synth']=command('dc_shell',package/'map.tcl',synth,env,14400,'Q12_FINAL_SYNTH_COMPLETE');save()
 assert report['stages']['synth']['tool_complete'],'Mapping failed'
 report['stages']['synth'].update(audit_reports.synth(synth));save()
 env.update(Q12_NETLIST=str(synth/'mapped.v'),Q12_SDC=str(synth/'mapped.sdc'),Q12_SVF=str(synth/'mapped.svf'))
 report['phase']='formal_and_power';save()
 def formal():
  cwd=out/'formal';cwd.mkdir()
  # Rebind this auditor to the new completed vendor result; source, library,
  # netlist and every diagnostic gate remain fully enforced.
  formal_audit.BASELINE_SHA256=sha(vendor_file)
  formal_audit.bind_inputs(package,synth,cwd,dbs)
  rec=command('fm_shell',package/'formal.tcl',cwd,env,10800,'Q12_FINAL_FORMAL_COMPLETE')
  rec['audit']=formal_audit.audit(cwd,synth,log_path=cwd/'tool.log')
  rec['passed']=rec['tool_complete']and rec['audit']['accepted'];return rec
 # Power can run while equivalence is being checked; its result is not promoted
 # to qualified performance without the independent equivalence outcome.
 with concurrent.futures.ThreadPoolExecutor(max_workers=1)as pool:
  future=pool.submit(formal)
  macros=audit_reports.macro_rows(synth/'macros_mapped.tsv')
  for index,task in enumerate(vr['tasks']):
   name='power_layer%02d'%index;cwd=out/name;cwd.mkdir();activity=task['activity']
   assert activity['scope']=='tb_q12soc/dut'and activity['timescale_ps']==1
   assert activity['end_ps']-activity['start_ps']==activity['duration_ps']>0
   saif=(vendor/activity['saif_relpath']).resolve();assert vendor.resolve()in saif.parents and sha(saif)==activity['saif_sha256']
   put(cwd/'activity_preflight.json',check_saif(saif,activity['start_ps'],activity['end_ps'],macros))
   rec=command('pt_shell',package/'power.tcl',cwd,dict(env,Q12_SAIF=str(saif)),1800,'Q12_FINAL_POWER_REPORTS_COMPLETE')
   rec.update(task=task['task'],saif_sha256=sha(saif),duration_ps=activity['duration_ps'],accepted=False)
   if rec['tool_complete']:
    try:
     watts=audit_reports.power_value((cwd/'power.rpt').read_text(),(cwd/'power_units.rpt').read_text())
     rec['provisional_unqualified']={'power_w':watts,'energy_uj':watts*activity['duration_ps']*1e-6}
    except Exception as e:rec['units_error']=str(e)
    try:rec.update(audit_reports.power(cwd,activity['duration_ps']),accepted=True)
    except Exception as e:rec['acceptance_error']=str(e)
   report['stages'][name]=rec;save();print(name,json.dumps(rec),flush=True)
  try:report['stages']['formal']=future.result()
  except Exception as e:report['stages']['formal']={'passed':False,'error':str(e)}
 report['phase']='reports_complete';save()
 powers=[v for k,v in report['stages'].items()if k.startswith('power_layer')]
 if len(powers)==12 and all('provisional_unqualified'in p for p in powers):
  report['mean_energy_uj_unqualified']=sum(p['provisional_unqualified']['energy_uj']for p in powers)/12
 if len(powers)==12 and all(p['accepted']for p in powers):report['mean_energy_uj']=sum(p['energy_uj']for p in powers)/12
 report['passed']=False;report['review_required']='Review functional-mode timing, all hold/constraint checks, formal and activity evidence before promotion'
 report['area_limit_mm2']=0.448646862835;report['throughput_requirement_cycles']=25000
 save();print('Q12_COMPACT_FULL_REPORTS_COMPLETE='+str(out/'result.json'),flush=True)
except BaseException as e:
 report.update(phase='failed',error=str(e));save();raise
