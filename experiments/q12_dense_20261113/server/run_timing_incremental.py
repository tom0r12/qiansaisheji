"""Independent timing repair from the exact native12 mapped checkpoint."""
from pathlib import Path
import fcntl,hashlib,json,os,re,shutil,subprocess,tempfile,time,signal

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def put(p,r):
 q=p.with_suffix('.tmp');q.write_text(json.dumps(r,indent=2)+'\n');q.replace(p)

lock=Path('/tmp/.q12_native12_timing_repair_v1.lock').open('a+')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
matches=[]
for p in Path('/tmp').glob('q12_native12_full_*/result.json'):
 r=read(p)
 if r.get('stages',{}).get('synth',{}).get('tool_complete'):matches.append(p)
assert len(matches)==1,matches
prior=matches[0].parent
prior_id=read(prior/'derived_identity.json')
assert prior_id['candidate']=='q12_x12_w10_y12_native_write_priority'
out=Path(tempfile.mkdtemp(prefix='q12_native12_timing_',dir='/tmp'))
print('Q12_TIMING_DIRECTORY',out,flush=True)
package=out/'derived_inputs';shutil.copytree(str(prior/'derived_inputs'),str(package))
for n,h in read(package/'hardware/manifest.json')['sources_sha256'].items():assert sha(package/'hardware'/n)==h,n
sources={n:sha(prior/'synth'/n)for n in ('mapped.v','mapped.ddc','mapped.sdc','mapped.svf')}
desktop=Path.home()/'Desktop'
dbs=[desktop/'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db']
dbs += [desktop/('qingyu_sram_corners/RAMSP%dX16_tt_1p10v_1p10v_25c.db'%n)for n in (128,1024,4096)]
env=dict(os.environ,Q12_PACKAGE=str(package),Q12_LIBRARIES=' '.join(map(str,dbs)),Q12_STD_DB=str(dbs[0]),Q12_DDC=str(prior/'synth/mapped.ddc'))
report={'phase':'synthesis','passed':False,'predecessor':str(prior),'predecessor_identity_sha256':sha(prior/'derived_identity.json'),
 'predecessor_artifact_sha256':sources,'vendor_result':prior_id['vendor_result'],'vendor_result_sha256':prior_id['vendor_result_sha256'],
 'rtl_changed':False,'mean_full_window_cycles':read(prior/'result.json')['mean_full_window_cycles'],
 'clock_period_ns':6.666666667,'libraries_sha256':{str(p):sha(p)for p in dbs},
 'constraints_changes':['Functional debug straps 111 applied before incremental optimization; same task mode',
 'Exported loader_clk classified as a generated clock, not synchronous data output; all data I/O budgets unchanged',
 'Only lfextclk to four PWM synchronizer first-stage D pins excluded as asynchronous; stages 0-to-1 and 1-to-2 remain timed'],
 'limits':['TT prelayout with ideal clocks, not routed timing signoff','Official precision and loader acceptance remain open'],'stages':{}}
put(out/'result.json',report)
tcl=r'''set rc [catch {
set_host_options -max_cores 4
set target_library [list $env(Q12_STD_DB)]
set synthetic_library dw_foundation.sldb
set link_library [concat [list *] $env(Q12_LIBRARIES) [list dw_foundation.sldb]]
foreach db $env(Q12_LIBRARIES) {read_db $db}
set_svf mapped.svf
read_ddc $env(Q12_DDC)
current_design qingyu_e203_soc_top
if {![link]} {error "Checkpoint link failed"}
source [file join $env(Q12_PACKAGE) audit.tcl]
q12_inventory before
redirect -file inherited_setup.rpt {report_timing -delay_type max -max_paths 30 -significant_digits 8}
redirect -file inherited_hold.rpt {report_timing -delay_type min -max_paths 30 -significant_digits 8}
set modes [get_ports {io_pads_dbgmode0_n_i_ival io_pads_dbgmode1_n_i_ival io_pads_dbgmode2_n_i_ival}]
if {[sizeof_collection $modes]!=3} {error "Three debug straps required"}
set_case_analysis 1 $modes
set export_clock [get_ports loader_clk]
if {[sizeof_collection $export_clock]!=1} {error "One forwarded loader clock required"}
remove_output_delay $export_clock
create_generated_clock -name loader_export_clk -source [get_pins u_e203_subsys_top/qingyu_bus_clk] -master_clock core_clk -divide_by 1 $export_clock
set_clock_uncertainty -setup 0.1 [get_clocks loader_export_clk]
set_clock_uncertainty -hold 0.02 [get_clocks loader_export_clk]
set_clock_transition 0.1 [get_clocks loader_export_clk]
# Existing input_stage.v lines 41-52 implements a three-flop asynchronous
# low-speed-clock synchronizer. Its first stage has no synchronous phase
# relationship to lfextclk. Keep the two metastability-resolution stages timed.
set async_first [get_pins -quiet __nonexistent_q12_pin__]
foreach_in_collection cell [get_cells -hierarchical -filter {full_name =~ *u_in_stage/r_ls_clk_sync_reg*}] {
 if {[regexp {r_ls_clk_sync_reg\[0\]$} [get_object_name $cell]]} {
  set async_first [add_to_collection $async_first [get_pins -of_objects $cell -filter {direction == in && full_name =~ */D}]]
 }
}
if {[sizeof_collection $async_first]!=4} {error "Exactly four existing PWM CDC first-stage D pins required"}
redirect -file pwm_async_before.rpt {report_timing -from [get_ports lfextclk] -to $async_first -delay_type min -max_paths 4 -significant_digits 8}
set_false_path -from [get_ports lfextclk] -to $async_first
set f [open cdc_exception_audit.txt w]
puts $f "Only lfextclk to existing three-stage PWM synchronizer first D pins:"
foreach_in_collection pin $async_first {puts $f [get_object_name $pin]}
close $f
set_fix_hold [all_clocks]
set_fix_multiple_port_nets -all -buffer_constants
# Preserve every hierarchy and SRAM instance path for area and SAIF audits.
set hierarchy [get_cells -hierarchical -filter {is_hierarchical == true}]
set_ungroup $hierarchy false
set cpu_hierarchy [get_cells -hierarchical -filter {is_hierarchical == true && full_name =~ u_e203_subsys_top/u_e203_subsys_main/u_e203_cpu_top/*}]
set_boundary_optimization $cpu_hierarchy true
redirect -file before_constraints.rpt {report_constraint -all_violators}
redirect -file case_analysis.rpt {report_case_analysis}
puts Q12_INCREMENTAL_BEGIN
if {![compile_ultra -incremental -no_autoungroup]} {error "Incremental mapping failed"}
puts Q12_INCREMENTAL_END
if {![link]} {error "Repaired link failed"}
write -format verilog -hierarchy -output mapped.v
write -format ddc -hierarchy -output mapped.ddc
write_sdc mapped.sdc
set_svf -off
q12_inventory mapped
source [file join $env(Q12_PACKAGE) hardware report_explicit_area.tcl]
q12_report_explicit_area
redirect -file area.rpt {report_area -hierarchy}
redirect -file timing_max.rpt {report_timing -delay_type max -max_paths 100 -significant_digits 8}
redirect -file timing_min.rpt {report_timing -delay_type min -max_paths 100 -significant_digits 8}
redirect -file constraints.rpt {report_constraint -all_violators -significant_digits 8}
redirect -file check_timing.rpt {check_timing}
redirect -file check_design.rpt {check_design}
redirect -file clocks.rpt {report_clock -attributes}
redirect -file units.rpt {report_units}
puts Q12_TIMING_REPAIR_COMPLETE
} message]
if {$rc} {puts "Q12_TIMING_REPAIR_FAILED: $message";puts $errorInfo;exit 2}
exit 0
'''
(out/'repair.tcl').write_text(tcl)
synth=out/'synth';synth.mkdir()
with(synth/'tool.log').open('w')as log:
 p=subprocess.Popen([shutil.which('dc_shell'),'-f',str(out/'repair.tcl')],cwd=str(synth),env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 put(synth/'process.json',{'pid':p.pid})
 start=time.monotonic()
 try:rc=p.wait(timeout=3600)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGTERM);rc=p.wait(timeout=30)
 elapsed=time.monotonic()-start
text=(synth/'tool.log').read_text(errors='replace')
ok=rc==0 and 'Q12_TIMING_REPAIR_COMPLETE'in text and not re.search(r'^Error:',text,re.M)
report['stages']['synth']={'returncode':rc,'seconds':elapsed,'tool_complete':ok,'log_sha256':sha(synth/'tool.log')}
if ok:
 for name,key in [('timing_max.rpt','worst_setup_ns'),('timing_min.rpt','worst_hold_ns')]:
  vals=re.findall(r'slack\s*\([^)]*\)\s*([-+\d.]+)',(synth/name).read_text());assert vals,name
  report[key]=min(map(float,vals))
 report['area_library_units']={k:float(v)for k,v in re.findall(r'^([A-Z0-9_]+)=([-+\d.eE]+)$',(synth/'explicit_area_summary.txt').read_text(),re.M)}
 report['netlist_sha256']=sha(synth/'mapped.v')
 report['reported_setup_hold_nonnegative']=report['worst_setup_ns']>=0 and report['worst_hold_ns']>=0
report['phase']='mapping_complete'if ok else'synthesis_failed'
for n,h in sources.items():assert sha(prior/'synth'/n)==h,'Predecessor altered'
put(out/'result.json',report)
print(json.dumps(report,sort_keys=True),flush=True)
