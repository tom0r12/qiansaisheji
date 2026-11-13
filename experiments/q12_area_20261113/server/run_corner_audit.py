"""Five available PVT diagnostics on an unchanged mapped v2 SoC.

Uses original mapped SDC, translating only standard-library names if present,
then applies actual benchmark debug straps. No false paths or relaxed periods.
Ideal pre-CTS hold is diagnostic only; it is not physical hold signoff.
"""
from pathlib import Path
import hashlib,json,os,re,shutil,signal,subprocess,tempfile,time
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
matches=[]
for p in Path('/tmp').glob('q12_area_full_*/result.json'):
 r=json.loads(p.read_text())
 if r.get('candidate_sha256')=='3e53fea269dd62c23642b7bb397234eba0809338061301dbbfe193ba44735c17'and r.get('compile_complete'):matches.append(p.parent)
assert len(matches)==1,matches
source=matches[0];out=Path(tempfile.mkdtemp(prefix='q12_corner_audit_',dir='/tmp'))
print('Q12_CORNER_AUDIT_DIRECTORY='+str(out),flush=True)
desktop=Path.home()/'Desktop';stdroot=desktop/'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty'
corners=[('tt25','tt_v1p1_25c','tt_1p10v_1p10v_25c'),('ss125','ss_v0p99_125c','ss_0p99v_0p99v_125c'),('ssm40','ss_v0p99_-40c','ss_0p99v_0p99v_m40c'),('ff125','ff_v1p21_125c','ff_1p21v_1p21v_125c'),('ffm40','ff_v1p21_-40c','ff_1p21v_1p21v_m40c')]
result={'passed':False,'scope':'same v2 netlist, prelayout PVT diagnostics; all paths retained','netlist_sha256':sha(source/'synth/mapped.v'),'sdc_sha256':sha(source/'synth/mapped.sdc'),'corners':{}}
def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
save()
tcl='''set rc [catch {
set link_path [concat [list *] $env(Q12_LIBRARIES)]
read_verilog $env(Q12_NETLIST)
current_design qingyu_e203_soc_top
if {![link_design qingyu_e203_soc_top]} {error "Corner link failed"}
set scclib [get_libs -quiet *scc40nll*]
if {[sizeof_collection $scclib]!=1} {error "One standard-cell corner required"}
set f [open $env(Q12_ORIGINAL_SDC) r];set sdc [read $f];close $f
# Preserve every original numeric timing constraint; only an explicit TT
# standard-library reference is translated to this run's selected corner.
regsub -all -nocase {scc40nll_vhsc40_rvt_tt_v1p1_25c(_basic)?} $sdc [get_object_name $scclib] sdc
set f [open corner.sdc w];puts $f $sdc;close $f
read_sdc corner.sdc
set modes [get_ports {io_pads_dbgmode0_n_i_ival io_pads_dbgmode1_n_i_ival io_pads_dbgmode2_n_i_ival}]
if {[sizeof_collection $modes]!=3} {error "Three benchmark mode straps required"}
set_case_analysis 1 $modes
update_timing
redirect -file check_timing.rpt {check_timing}
redirect -file coverage.rpt {report_analysis_coverage}
redirect -file setup.rpt {report_timing -delay_type max -max_paths 100 -significant_digits 8}
redirect -file hold.rpt {report_timing -delay_type min -max_paths 100 -significant_digits 8}
redirect -file constraints.rpt {report_constraint -all_violators}
redirect -file units.rpt {report_units}
set f [open metrics.txt w]
foreach group {core_clk hfext_clk lfext_clk jtag_clk} {
 foreach kind {max min} {
  set paths [get_timing_paths -group $group -delay_type $kind -max_paths 1]
  if {[sizeof_collection $paths]>0} {puts $f "$group.$kind=[get_attribute $paths slack]"}
 }
}
puts $f "LIBRARIES=[get_object_name [get_libs *]]"
close $f
puts Q12_CORNER_AUDIT_COMPLETE
} message]
if {$rc} {puts "Q12_CORNER_AUDIT_FAILED: $message";puts $errorInfo;exit 2}
exit 0
'''
for label,sc,ram in corners:
 stage=out/label;stage.mkdir();found=list(stdroot.rglob('scc40nll_vhsc40_rvt_'+sc+'_basic.db'));assert len(found)==1,(label,found)
 libs=found+[desktop/('qingyu_sram_corners/RAMSP%dX16_%s.db'%(n,ram))for n in(128,1024,4096)]
 for p in libs:assert p.is_file(),str(p)
 record={'phase':'running','libraries_sha256':{str(p):sha(p)for p in libs}};result['corners'][label]=record;save()
 (stage/'audit.tcl').write_text(tcl)
 env=dict(os.environ,Q12_LIBRARIES=' '.join('{'+str(p)+'}'for p in libs),Q12_NETLIST=str(source/'synth/mapped.v'),Q12_ORIGINAL_SDC=str(source/'synth/mapped.sdc'))
 with(stage/'pt.log').open('w')as log:
  proc=subprocess.Popen([shutil.which('pt_shell'),'-f',str(stage/'audit.tcl')],cwd=str(stage),env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  (stage/'process.json').write_text(json.dumps({'pid':proc.pid}))
  try:rc=proc.wait(timeout=1200)
  except BaseException:
   try:os.killpg(proc.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
   raise
 text=(stage/'pt.log').read_text(errors='replace');record.update(returncode=rc,phase='complete'if rc==0 and'Q12_CORNER_AUDIT_COMPLETE'in text and not re.search(r'^Error:',text,re.M)else'failed')
 if(stage/'metrics.txt').exists():record['metrics']=dict(line.split('=',1)for line in(stage/'metrics.txt').read_text().splitlines())
 record['errors']=re.findall(r'^Error:.*$',text,re.M);save();print(label,json.dumps(record.get('metrics',record)),flush=True)
assert sha(source/'synth/mapped.v')==result['netlist_sha256']and sha(source/'synth/mapped.sdc')==result['sdc_sha256']
print('Q12_CORNER_REPORTS='+str(out/'result.json'),flush=True)
