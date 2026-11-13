"""Read-only timing audit of the mapped v2 netlist, with documented mode straps.

No recompile, timing exceptions, netlist edits, or area reductions are performed.
"""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,tempfile

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
matches=[]
for p in Path('/tmp').glob('q12_area_full_*/result.json'):
 r=json.loads(p.read_text())
 if r.get('candidate_sha256')=='3e53fea269dd62c23642b7bb397234eba0809338061301dbbfe193ba44735c17' and r.get('compile_complete'):matches.append(p.parent)
assert len(matches)==1,matches
source=matches[0];out=Path(tempfile.mkdtemp(prefix='q12_mode_audit_',dir='/tmp'))
print('Q12_MODE_AUDIT_DIRECTORY='+str(out),flush=True)
desktop=Path.home()/'Desktop'
stdroot=desktop/'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty'
std=stdroot/'1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db'
libs=[std]+[desktop/('qingyu_sram_corners/RAMSP%dX16_tt_1p10v_1p10v_25c.db'%n)for n in(128,1024,4096)]
record={'mapped_ddc':str(source/'synth/mapped.ddc'),'mapped_ddc_sha256':sha(source/'synth/mapped.ddc'),
 'libraries_sha256':{str(p):sha(p)for p in libs},'mode':'debug straps = 111, matching task testbench; no false paths',
 'available_standard_libraries':[str(p)for p in stdroot.rglob('*.db')],
 'available_sram_libraries':[str(p)for p in(desktop/'qingyu_sram_corners').glob('*.db')]}
(out/'identity.json').write_text(json.dumps(record,indent=2)+'\n')
tcl='''set rc [catch {
set target_library [list $env(Q12_STD_DB)]
set link_library [concat [list *] $env(Q12_LIBRARIES) [list dw_foundation.sldb]]
foreach db $env(Q12_LIBRARIES) {read_db $db}
read_ddc $env(Q12_DDC)
current_design qingyu_e203_soc_top
if {![link]} {error "Link failed"}
redirect -file unrestricted_setup.rpt {report_timing -delay_type max -max_paths 100 -significant_digits 8}
set modes [get_ports {io_pads_dbgmode0_n_i_ival io_pads_dbgmode1_n_i_ival io_pads_dbgmode2_n_i_ival}]
if {[sizeof_collection $modes]!=3} {error "Expected exactly three mode straps"}
set_case_analysis 1 $modes
redirect -file functional_setup.rpt {report_timing -delay_type max -max_paths 100 -significant_digits 8}
redirect -file functional_hold.rpt {report_timing -delay_type min -max_paths 100 -significant_digits 8}
redirect -file functional_constraints.rpt {report_constraint -all_violators}
redirect -file functional_check_timing.rpt {check_timing}
redirect -file functional_case.rpt {report_case_analysis}
redirect -file cpu_path.rpt {report_timing -delay_type max -from [get_cells -hierarchical -filter {full_name =~ *ifu_lo_ir_dfflr*}] -max_paths 1 -significant_digits 8 -nets -transition_time -capacitance}
set f [open metrics.txt w]
foreach clock {core_clk hfext_clk lfext_clk jtag_clk} {
 set paths [get_timing_paths -group $clock -delay_type max -max_paths 1]
 if {[sizeof_collection $paths]>0} {puts $f "$clock=[get_attribute $paths slack]"}
}
close $f
puts Q12_MODE_AUDIT_COMPLETE
} message]
if {$rc} {puts "Q12_MODE_AUDIT_FAILED: $message";puts $errorInfo;exit 2}
exit 0
'''
(out/'audit.tcl').write_text(tcl)
env=dict(os.environ,Q12_STD_DB=str(std),Q12_LIBRARIES=' '.join('{'+str(p)+'}'for p in libs),Q12_DDC=record['mapped_ddc'])
with(out/'dc.log').open('w')as log:
 p=subprocess.Popen([shutil.which('dc_shell'),'-f',str(out/'audit.tcl')],cwd=str(out),env=env,stdout=log,stderr=subprocess.STDOUT)
 (out/'process.json').write_text(json.dumps({'pid':p.pid}))
 rc=p.wait(timeout=900)
assert sha(source/'synth/mapped.ddc')==record['mapped_ddc_sha256']
text=(out/'dc.log').read_text(errors='replace')
print('AUDIT_RC',rc,'COMPLETE','Q12_MODE_AUDIT_COMPLETE'in text,flush=True)
if(out/'metrics.txt').exists():print((out/'metrics.txt').read_text(),flush=True)
