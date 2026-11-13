"""One-window annotation probe on the superseded checkpoint; not a final score."""
from pathlib import Path
import fcntl,hashlib,json,os,re,shutil,subprocess,sys,tempfile,signal
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
lock=Path('/tmp/.q12_power_annotation_probe_v1.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
t=list(Path('/tmp').glob('q12_native12_timing_*/result.json'));c=list(Path('/tmp').glob('q12_cell_activity_*/result.json'));assert len(t)==len(c)==1
tr=read(t[0]);cr=read(c[0]);assert tr['phase']=='mapping_complete'and cr['phase']=='activity_complete'
assert tr['vendor_result_sha256']==cr['source_vendor_result_sha256']
synth=t[0].parent/'synth';package=t[0].parent/'derived_inputs';v=Path(cr['vendor_result']);assert sha(v)==cr['vendor_result_sha256']
act=read(v)['tasks'][0]['activity'];saif=v.parent/act['saif_relpath'];assert sha(saif)==act['saif_sha256']
out=Path(tempfile.mkdtemp(prefix='q12_power_probe_',dir='/tmp'));print('PROBE',out,flush=True)
sys.path.insert(0,str(package));import audit_reports
deps=list(Path('/tmp').glob('q12_early_launch_*/saif_macro_bridge.py'));assert len(deps)==1
sys.path.insert(0,str(deps[0].parent));from saif_macro_bridge import build_macro_overlay
overlay,mapping=build_macro_overlay(saif.read_text(),audit_reports.macro_rows(synth/'macros_mapped.tsv'))
assert mapping['macro_count']==116
(out/'macro_overlay.saif').write_text(overlay);(out/'activity_mapping.json').write_text(json.dumps(mapping,indent=2)+'\n')
power=(package/'power.tcl').read_text();needle=' redirect -file read_saif.rpt {read_saif -strip_path tb_q12soc/dut $env(Q12_SAIF)}';assert power.count(needle)==1
power=power.replace(needle,needle+'\n redirect -file read_macro_overlay.rpt {read_saif -strip_path tb_q12soc/dut $env(Q12_MACRO_SAIF)}');(out/'power.tcl').write_text(power)
env=dict(os.environ,Q12_PACKAGE=str(package),Q12_LIBRARIES=' '.join(tr['libraries_sha256']),Q12_NETLIST=str(synth/'mapped.v'),Q12_SDC=str(synth/'mapped.sdc'),Q12_SAIF=str(saif),Q12_MACRO_SAIF=str(out/'macro_overlay.saif'))
report={'phase':'annotation_probe','scope':'Superseded native12 checkpoint with hold violation; NOT final-candidate energy','passed':False}
(out/'result.json').write_text(json.dumps(report))
with(out/'tool.log').open('w')as f:
 p=subprocess.Popen([shutil.which('pt_shell'),'-f',str(out/'power.tcl')],cwd=str(out),env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 (out/'process.json').write_text(json.dumps({'pid':p.pid}))
 try:rc=p.wait(timeout=300)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);rc=p.wait(timeout=20)
log=(out/'tool.log').read_text(errors='replace');report.update(returncode=rc,phase='reports_complete',tool_complete=rc==0 and'Q12_FINAL_POWER_REPORTS_COMPLETE'in log,macro_mapping_count=mapping['macro_count'])
if report['tool_complete']:
 try:
  watts=audit_reports.power_value((out/'power.rpt').read_text(),(out/'power_units.rpt').read_text());report['provisional_unqualified']={'power_w':watts,'energy_uj':watts*act['duration_ps']*1e-6}
 except Exception as e:report['units_error']=str(e)
 try:report['audit']=audit_reports.power(out,act['duration_ps']);report['annotation_accepted']=True
 except Exception as e:report['acceptance_error']=str(e)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('PROBE_RESULT',json.dumps(report),flush=True)
