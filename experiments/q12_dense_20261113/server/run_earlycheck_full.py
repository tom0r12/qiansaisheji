"""Full candidate rerun after removing the output-fault ready/abort feedback."""
from pathlib import Path
import concurrent.futures,datetime,fcntl,hashlib,json,os,re,shutil,signal,subprocess,sys,tempfile,time
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def put(p,r):
 q=p.with_suffix('.tmp');q.write_text(json.dumps(r,indent=2)+'\n');q.replace(p)
lock=Path('/tmp/.q12_earlycheck_full_v1.lock').open('a+')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
out=Path(tempfile.mkdtemp(prefix='q12_earlycheck_full_',dir='/tmp'))
print('Q12_EARLYCHECK_DIRECTORY',out,flush=True)
deadline=datetime.datetime(2026,11,13,9,22,tzinfo=datetime.timezone.utc).timestamp()
report={'phase':'preparation','passed':False,'stages':{},'scope':'TT 1.1V 25C prelayout, exact full-task windows'}
def save():put(out/'result.json',report)
def command(tool,script,cwd,env,seconds,marker):
 remaining=deadline-time.time();assert remaining>10,'Session deadline'
 cmd=[shutil.which(tool),'-f',str(script)];assert cmd[0],tool
 start=time.monotonic()
 with(cwd/'tool.log').open('w')as f:
  p=subprocess.Popen(cmd,cwd=str(cwd),env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  put(cwd/'process.json',{'pid':p.pid,'command':cmd})
  try:rc=p.wait(timeout=min(seconds,remaining))
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGTERM)
   try:rc=p.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);rc=p.wait()
 text=(cwd/'tool.log').read_text(errors='replace')
 critical=re.sub(r'^Q12_OPTIONAL_REPORT_BEGIN=([^\n]+)\n.*?^Q12_OPTIONAL_REPORT_END=\1\s*$','',text,flags=re.M|re.S)
 return {'returncode':rc,'seconds':time.monotonic()-start,'tool_complete':rc==0 and marker in text and not re.search(r'^Error:',critical,re.M),'log_sha256':sha(cwd/'tool.log')}
save()
try:
 roots=list(Path('/tmp').glob('q12_native12_full_*/derived_identity.json'));assert len(roots)==1
 prior=roots[0].parent;identity=read(roots[0]);assert identity['candidate']=='q12_x12_w10_y12_native_write_priority'
 original_vendor_file=Path(identity['vendor_result']);assert sha(original_vendor_file)==identity['vendor_result_sha256']
 original_vendor=read(original_vendor_file);assert original_vendor['functional_passed']
 original_inputs=original_vendor_file.parent.parent/'vendor_inputs'
 package=out/'derived_inputs';shutil.copytree(str(prior/'derived_inputs'),str(package))
 vendor_package=out/'vendor_inputs';shutil.copytree(str(original_inputs),str(vendor_package))
 for name,h in read(vendor_package/'manifest.json')['files_sha256'].items():assert sha(vendor_package/name)==h,name
 old='wire invalid_core_output=formatter_input && formatter_in_ready &&'
 new='wire invalid_core_output=formatter_input &&'
 names=[package/'hardware/src/output/eda/q12_candidate/integration/q12_stream_engine_overlap.sv',vendor_package/'src/q12/integration/q12_stream_engine_overlap.sv']
 for p in names:
  assert sha(p)=='90b1661e15ab3ad1baf6ff8cd9945e917920254e51955af693cd13d4fe1f5814'
  text=p.read_text();assert text.count(old)==1;p.write_text(text.replace(old,new))
 assert sha(names[0])==sha(names[1])
 report['engine_sha256']=sha(names[0]);report['parent_vendor_sha256']=sha(original_vendor_file)
 runner=vendor_package/'run_vendor.py';text=runner.read_text();needle="'-debug_access+all','-top'";assert text.count(needle)==1
 runner.write_text(text.replace(needle,"'-debug_access+all','-debug_region+cell+lib','-top'"))
 vm=read(vendor_package/'manifest.json');vm['files_sha256']={n:sha(vendor_package/n)for n in vm['files_sha256']};put(vendor_package/'manifest.json',vm)
 hw=read(package/'hardware/manifest.json');hw['sources_sha256']={n:sha(package/'hardware'/n)for n in hw['sources_sha256']};put(package/'hardware/manifest.json',hw)
 dbs=list(read(prior/'result.json')['libraries_sha256'])
 env=dict(os.environ,Q12_PACKAGE=str(package),Q12_LIBRARIES=' '.join(dbs),Q12_STD_DB=dbs[0],Q12_RAM128_DB=dbs[1],Q12_RAM1024_DB=dbs[2],Q12_RAM4096_DB=dbs[3])
 report['libraries_sha256']={n:sha(n)for n in dbs}
 modes='set modes [get_ports {io_pads_dbgmode0_n_i_ival io_pads_dbgmode1_n_i_ival io_pads_dbgmode2_n_i_ival}]\nif {[sizeof_collection $modes]!=3} {error "Three debug straps required"}\nset_case_analysis 1 $modes\n'
 clocks='''remove_output_delay [get_ports loader_clk]
create_generated_clock -name loader_export_clk -source [get_pins u_e203_subsys_top/qingyu_bus_clk] -master_clock core_clk -divide_by 1 [get_ports loader_clk]
set_clock_uncertainty -setup 0.1 [get_clocks loader_export_clk]
set_clock_uncertainty -hold 0.02 [get_clocks loader_export_clk]
set_clock_transition 0.1 [get_clocks loader_export_clk]
set_fix_hold [all_clocks]
set_fix_multiple_port_nets -all -buffer_constants
set cpu_hierarchy [get_cells -hierarchical -filter {is_hierarchical == true && full_name =~ u_e203_subsys_top/u_e203_subsys_main/u_e203_cpu_top/*}]
set_boundary_optimization $cpu_hierarchy true
'''
 hold='''
write -format ddc -hierarchy -output before_hold.ddc
redirect -file before_hold.rpt {report_timing -delay_type min -max_paths 20 -significant_digits 8}
set async_first [get_pins -quiet __nonexistent_q12_pin__]
foreach_in_collection cell [get_cells -hierarchical -filter {full_name =~ *u_in_stage/r_ls_clk_sync_reg*}] {
 if {[regexp {r_ls_clk_sync_reg\[0\]$} [get_object_name $cell]]} {
  set async_first [add_to_collection $async_first [get_pins -of_objects $cell -filter {direction == in && full_name =~ */D}]]
 }
}
if {[sizeof_collection $async_first]!=4} {error "Exactly four PWM first-stage synchronizer D pins required"}
set_false_path -from [get_ports lfextclk] -to $async_first
set f [open cdc_exception_audit.txt w]
foreach_in_collection pin $async_first {puts $f [get_object_name $pin]}
close $f
set_fix_hold [all_clocks]
puts Q12_HOLD_REPAIR_BEGIN
if {![compile -incremental_mapping -only_hold_time]} {error "Hold-only mapping failed"}
puts Q12_HOLD_REPAIR_END
'''
 mapping=(package/'map.tcl').read_text()
 assert mapping.count('compile -map_effort high')==1
 mapping=mapping.replace(' puts Q12_COMPILE_BEGIN',modes+clocks+'\n puts Q12_COMPILE_BEGIN')
 mapping=mapping.replace('compile -map_effort high','compile_ultra -no_autoungroup')
 mapping=mapping.replace(' puts Q12_COMPILE_END',' puts Q12_COMPILE_END\n'+hold)
 mapping=mapping.replace(' set package $env(Q12_PACKAGE)',' set_host_options -max_cores 4\n set package $env(Q12_PACKAGE)')
 (package/'map.tcl').write_text(mapping)
 sys.path.insert(0,str(package));import audit_reports,formal_audit
 sys.path.insert(0,str(Path(__file__).parent));from saif_macro_bridge import build_macro_overlay
 pool=concurrent.futures.ThreadPoolExecutor(max_workers=2)
 def vendor():
  with(out/'vendor.log').open('w')as f:
   p=subprocess.Popen([sys.executable,str(vendor_package/'run_vendor.py'),'--tasks','12','--saif','--work-root',str(out)],cwd=str(out),stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
   put(out/'vendor_process.json',{'pid':p.pid})
   try:rc=p.wait(timeout=min(2400,deadline-time.time()))
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);rc=p.wait(timeout=20)
  assert rc==0,'Vendor replay failed'
  results=list(out.glob('qingyu_q12_final_vendor_*/result.json'));assert len(results)==1
  v=read(results[0]);assert v['passed']and v['functional_passed']and len(v['tasks'])==12
  before=[t['metrics']['full_window_cycles']for t in original_vendor['tasks']];after=[t['metrics']['full_window_cycles']for t in v['tasks']]
  assert before==after,(before,after)
  rec={'tool_complete':True,'vendor_result':str(results[0]),'vendor_result_sha256':sha(results[0]),'task_cycles':after,'same_cycles_as_parent':True}
  put(out/'vendor_completed.json',rec);return rec
 fv=pool.submit(vendor)
 report['phase']='synthesis_and_vendor';save();synth=out/'synth';synth.mkdir()
 report['stages']['synth']=command('dc_shell',package/'map.tcl',synth,env,2800,'Q12_FINAL_SYNTH_COMPLETE');save()
 assert report['stages']['synth']['tool_complete'],'Full mapping failed'
 report['stages']['synth'].update(audit_reports.synth(synth));save()
 report['stages']['vendor']=fv.result();vrec=report['stages']['vendor'];vendor_file=Path(vrec['vendor_result']);vr=read(vendor_file);vendor_root=vendor_file.parent
 hw['soc_result_sha256']=sha(vendor_file);put(package/'hardware/manifest.json',hw)
 report.update(mean_task_cycles=sum(vrec['task_cycles'])/12,throughput_at_150mhz=150000000/(sum(vrec['task_cycles'])/12),netlist_sha256=sha(synth/'mapped.v'))
 env.update(Q12_NETLIST=str(synth/'mapped.v'),Q12_SDC=str(synth/'mapped.sdc'),Q12_SVF=str(synth/'mapped.svf'))
 def formal():
  cwd=out/'formal';cwd.mkdir();formal_audit.BASELINE_SHA256=sha(vendor_file)
  formal_audit.bind_inputs(package,synth,cwd,dbs)
  rec=command('fm_shell',package/'formal.tcl',cwd,env,1800,'Q12_FINAL_FORMAL_COMPLETE')
  rec['audit']=formal_audit.audit(cwd,synth,log_path=cwd/'tool.log');rec['passed']=rec['tool_complete']and rec['audit']['accepted'];put(cwd/'result.json',rec);return rec
 ff=pool.submit(formal);report['phase']='formal_and_power';save()
 try:
  power=(package/'power.tcl').read_text();needle=' redirect -file read_saif.rpt {read_saif -strip_path tb_q12soc/dut $env(Q12_SAIF)}';assert power.count(needle)==1
  power=power.replace(needle,needle+'\n redirect -file read_macro_overlay.rpt {read_saif -strip_path tb_q12soc/dut $env(Q12_MACRO_SAIF)}');(out/'power.tcl').write_text(power)
  macros=audit_reports.macro_rows(synth/'macros_mapped.tsv')
  for i,task in enumerate(vr['tasks']):
   name='power_layer%02d'%i;cwd=out/name;cwd.mkdir();act=task['activity'];saif=vendor_root/act['saif_relpath']
   assert sha(saif)==act['saif_sha256']and act['scope']=='tb_q12soc/dut'and act['end_ps']-act['start_ps']==act['duration_ps']>0
   text=saif.read_text();d=re.search(r'\(DURATION\s+(\d+)\s*\)',text);s=re.search(r'\(TIMESCALE\s+(\d+)\s+ps\s*\)',text)
   assert d and s and int(d[1])*int(s[1])==act['duration_ps']
   overlay,mapping=build_macro_overlay(text,macros);assert mapping['macro_count']==116
   overlay_file=cwd/'macro_overlay.saif';overlay_file.write_text(overlay);put(cwd/'activity_mapping.json',mapping)
   rec=command('pt_shell',out/'power.tcl',cwd,dict(env,Q12_SAIF=str(saif),Q12_MACRO_SAIF=str(overlay_file)),300,'Q12_FINAL_POWER_REPORTS_COMPLETE');rec.update(accepted=False,duration_ps=act['duration_ps'])
   if rec['tool_complete']:
    try:
     watts=audit_reports.power_value((cwd/'power.rpt').read_text(),(cwd/'power_units.rpt').read_text());rec['provisional_unqualified']={'power_w':watts,'energy_uj':watts*act['duration_ps']*1e-6}
    except Exception as e:rec['units_error']=str(e)
    try:rec.update(audit_reports.power(cwd,act['duration_ps']),accepted=True)
    except Exception as e:rec['acceptance_error']=str(e)
   report['stages'][name]=rec;save();print(name,json.dumps(rec),flush=True)
 except BaseException as e:report['power_error']=str(e);save();print('POWER_FAILED',repr(e),flush=True)
 report['stages']['formal']=ff.result();pool.shutdown(wait=True)
 powers=[v for k,v in report['stages'].items()if k.startswith('power_layer')]
 if len(powers)==12 and all('provisional_unqualified'in v for v in powers):report['mean_energy_uj_unqualified']=sum(v['provisional_unqualified']['energy_uj']for v in powers)/12
 if len(powers)==12 and all(v['accepted']for v in powers):report['mean_energy_uj']=sum(v['energy_uj']for v in powers)/12
 report['phase']='reports_complete';report['review_required']='Review all timing loops, constraints, formal scope and activity provenance before acceptance';save()
 print('Q12_EARLYCHECK_REPORTS_COMPLETE',out/'result.json',flush=True)
except BaseException as e:
 report.update(phase='failed',error=str(e));save();raise
