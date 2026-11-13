#!/usr/bin/env python3
"""Derived full-SoC mapping; baseline stays read-only and keeps its identity."""
from pathlib import Path
import hashlib,json,os,re,shutil,signal,subprocess,tempfile,time

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
here=Path(__file__).resolve().parent
identity=read(here/'identity.json')
candidate=here/'q12_task4.sv'
assert sha(candidate)==identity['candidate_sha256']
known=Path('/tmp/q12_final_s4_36usr_20261113')
packages=[p.parent for p in known.glob('*/package_identity.json') if sha(p)==identity['baseline_package_identity_sha256']]
if len(packages)!=1:raise ValueError('Exact baseline assessment package not found: '+str(packages))
baseline=packages[0];m=read(baseline/'package_identity.json')
for n,h in m['files'].items():
    if sha(baseline/n)!=h:raise ValueError('Baseline assessment changed: '+n)
source='hardware/src/output/eda/q12_candidate/core_datareset/q12_task4.sv'
assert sha(baseline/source)==identity['baseline_source_sha256']
# Require the exact candidate's completed 12-task manufacturer replay first.
replays=[]
for p in Path('/tmp').glob('q12_area_replay_*/result.json'):
    r=read(p)
    if r.get('candidate_sha256')==identity['candidate_sha256'] and r.get('passed') and len(r.get('tasks',[]))==12 and all(t['cycle_delta']==0 for t in r['tasks']):replays.append(p)
if len(replays)!=1:raise ValueError('Expected one successful source-matched 12-task replay')
out=Path(tempfile.mkdtemp(prefix='q12_area_full_',dir='/tmp'))
print('Q12_AREA_FULL_DIRECTORY='+str(out),flush=True)
package=out/'derived_inputs';shutil.copytree(str(baseline),str(package))
shutil.copy2(str(candidate),str(package/source))
actual={n:sha(package/n) for n in m['files']}
changed=[n for n,h in actual.items() if h!=m['files'][n]]
assert changed==[source],changed
# The copied frozen manifest is retained as provenance only, not claimed as a
# verification manifest for the new design. This new manifest binds actual files.
derived={'candidate':'q12_area_requant_data_hold_v2','baseline_package_identity_sha256':sha(baseline/'package_identity.json'),
         'baseline_files':m['files'],'actual_files':actual,'changed_files':changed,
         'vendor_replay':str(replays[0]),'vendor_replay_sha256':sha(replays[0])}
(out/'derived_identity.json').write_text(json.dumps(derived,indent=2)+'\n')
desktop=Path.home()/'Desktop'
std=desktop/'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db'
ramroot=desktop/'qingyu_sram_corners'
libs=[std]+[ramroot/('RAMSP%dX16_tt_1p10v_1p10v_25c.db'%size) for size in (128,1024,4096)]
for p in libs:assert p.is_file(),str(p)
dc=shutil.which('dc_shell');assert dc
env=dict(os.environ,Q12_PACKAGE=str(package),Q12_STD_DB=str(libs[0]),Q12_RAM128_DB=str(libs[1]),Q12_RAM1024_DB=str(libs[2]),Q12_RAM4096_DB=str(libs[3]))
run=out/'synth';run.mkdir()
report={'candidate':derived['candidate'],'candidate_sha256':sha(candidate),'passed':False,'phase':'synthesis',
        'vendor_replay':str(replays[0]),'library_sha256':{str(p):sha(p) for p in libs},
        'limitations':['Full-SoC functional replay passed; mapped timing/area still require completed reports',
                       'No same-candidate power or energy result yet','NP3 boundary organizer acceptance remains OPEN'],
        'command':[dc,'-f',str(package/'map.tcl')],'timeout_seconds':10800}
def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
save();start=time.monotonic()
with (run/'dc.log').open('w') as log:
    proc=subprocess.Popen(report['command'],cwd=str(run),env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    report['pid']=proc.pid;save()
    try:rc=proc.wait(timeout=10800)
    except BaseException as exc:
        try:os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        report.update(phase='failed',error=str(exc));save();raise
text=(run/'dc.log').read_text(errors='replace')
critical=re.sub(r'^Q12_OPTIONAL_REPORT_BEGIN=([^\n]+)\n.*?^Q12_OPTIONAL_REPORT_END=\1\s*$','',text,flags=re.M|re.S)
complete=rc==0 and 'Q12_FINAL_SYNTH_COMPLETE' in text and not re.search(r'^Error:',critical,re.M)
report.update(returncode=rc,seconds=time.monotonic()-start,compile_complete=complete,phase='mapped' if complete else 'failed')
area=run/'explicit_area_summary.txt'
if area.is_file():report['area_library_units']=dict(line.split('=',1) for line in area.read_text().splitlines() if '=' in line)
timing=run/'timing_max.rpt'
if timing.is_file():report['reported_setup_slacks_ns']=[float(v) for v in re.findall(r'slack\s*\([^)]*\)\s*([-+\d.]+)',timing.read_text())]
report['mapped_timing_nonnegative']=bool(report.get('reported_setup_slacks_ns')) and min(report['reported_setup_slacks_ns'])>=0
for n,h in actual.items():
    if sha(package/n)!=h:raise ValueError('Derived inputs changed: '+n)
report['mapping_and_sampled_setup_passed']=complete and report['mapped_timing_nonnegative']
report['passed']=False
report['review_required']=['Check all timing constraints and hold reports','Audit incremental area scope and clock coverage','Same-version equivalence and power analysis remain outstanding']
save();print('Q12_AREA_FULL_RESULT='+str(out/'result.json'),flush=True)
