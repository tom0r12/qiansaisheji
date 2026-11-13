"""Same-library decoder A/B and exact-candidate full-SoC activity capture."""
from pathlib import Path
import hashlib,json,os,shutil,signal,subprocess,tempfile,time
here=Path(__file__).resolve().parent
identity=json.loads((here/'identity.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
for n,h in identity['files'].items():assert sha(here/n)==h,n
known=Path('/tmp/q12_final_s4_36usr_20261113')
matches=[p.parent for p in known.glob('*/manifest.json') if sha(p)==identity['baseline_vendor_manifest_sha256']]
assert len(matches)==1,matches
baseline=matches[0];manifest=read(baseline/'manifest.json')
for n,h in manifest['files_sha256'].items():assert sha(baseline/n)==h,n
out=Path(tempfile.mkdtemp(prefix='q12_decoder_window_',dir='/tmp'))
print('Q12_DECODER_WINDOW_DIRECTORY='+str(out),flush=True)
report={'candidate':'q12_requant_data_hold_decoder_window_v3','passed':False,'phase':'prepare','identity':identity,'stages':{}}
def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
def run(cmd,cwd,env,timeout,filename):
 with (cwd/filename).open('w')as log:
  process=subprocess.Popen(cmd,cwd=str(cwd),env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  (cwd/'process.json').write_text(json.dumps({'pid':process.pid,'command':cmd,'started':time.time()}))
  try:rc=process.wait(timeout=timeout)
  except BaseException:
   try:os.killpg(process.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:process.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
   raise
  if rc:raise RuntimeError('Stage failed: '+str(cwd/filename))
package=out/'vendor_inputs';shutil.copytree(str(baseline),str(package))
overrides={'src/q12/core_datareset/q12_task4.sv':'q12_task4.sv','src/q12/decoder2/q12_rice_decoder.sv':'q12_rice_decoder.sv'}
for dest,source in overrides.items():shutil.copy2(str(here/source),str(package/dest))
actual={n:sha(package/n)for n in manifest['files_sha256']}
assert set(n for n,h in actual.items()if h!=manifest['files_sha256'][n])==set(overrides)
manifest['files_sha256']=actual
manifest['derived_candidate']={'name':report['candidate'],'baseline_manifest_sha256':identity['baseline_vendor_manifest_sha256'],'changed_files':overrides}
(package/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(out/'derived_identity.json').write_text(json.dumps({'baseline_manifest_sha256':identity['baseline_vendor_manifest_sha256'],'actual_manifest_sha256':sha(package/'manifest.json'),'candidate_files':identity['files'],'overrides':overrides},indent=2)+'\n')
report['derived_vendor_manifest_sha256']=sha(package/'manifest.json');save()
desktop=Path.home()/'Desktop'
std=desktop/'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db'
assert std.is_file()
dc=shutil.which('dc_shell');assert dc
try:
 for label,source in [('baseline',baseline/'src/q12/decoder2/q12_rice_decoder.sv'),('candidate',here/'q12_rice_decoder.sv')]:
  report['phase']='decoder_'+label;save()
  stage=out/('decoder_'+label);stage.mkdir()
  env=dict(os.environ,Q12_STD_DB=str(std),Q12_DECODER_SOURCE=str(source))
  run([dc,'-f',str(here/'map_decoder.tcl')],stage,env,2400,'dc.log')
  text=(stage/'dc.log').read_text(errors='replace')
  assert 'Q12_DECODER_COMPLETE' in text and '\nError:'not in text
  metrics=dict(line.split('=',1)for line in (stage/'metrics.txt').read_text().splitlines())
  report['stages'][label]={'source_sha256':sha(source),'metrics':metrics};save()
  print(label,json.dumps(metrics),flush=True)
 report['phase']='vendor_activity';save()
 run([shutil.which('python3'),str(package/'run_vendor.py'),'--tasks','12','--saif','--work-root',str(out)],out,dict(os.environ),18000,'vendor.log')
 runs=list(out.glob('qingyu_q12_final_vendor_*/result.json'));assert len(runs)==1
 vendor=read(runs[0]);assert vendor['passed']and vendor['functional_passed']and len(vendor['tasks'])==12
 assert vendor['manifest_sha256']==report['derived_vendor_manifest_sha256']
 assert all(t['cycles_delta_from_behavioral']==0 for t in vendor['tasks'])
 report.update(phase='activity_complete',functional_passed=True,vendor_result=str(runs[0]),vendor_result_sha256=sha(runs[0]),mean_full_window_cycles=vendor['mean_full_window_cycles'])
 report['throughput_at_assumed_150mhz']=150000000/vendor['mean_full_window_cycles']
 report['limits']=['Whole-SoC mapping and timing still required','Activity captured; no power value until same-version mapped PX','Baseline NP3 interface acceptance remains OPEN']
 save();print('Q12_DECODER_WINDOW_ACTIVITY_COMPLETE='+str(out/'result.json'),flush=True)
except BaseException as exc:
 report.update(phase='failed',error=str(exc));save();raise
