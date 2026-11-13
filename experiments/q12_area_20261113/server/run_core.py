#!/usr/bin/env python3
"""Standalone compute-core A/B; same libraries, same constraints, independent runs."""
import hashlib,json,os,shutil,signal,subprocess,tempfile,time
from pathlib import Path

here=Path(__file__).resolve().parent
identity=json.loads((here/'identity.json').read_text())
for n,h in identity['files'].items():
    assert hashlib.sha256((here/n).read_bytes()).hexdigest()==h,n
desktop=Path.home()/'Desktop'
std=desktop/'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db'
ram128=desktop/'qingyu_sram_corners/RAMSP128X16_tt_1p10v_1p10v_25c.db'
ram1024=desktop/'qingyu_sram_corners/RAMSP1024X16_tt_1p10v_1p10v_25c.db'
for p in (std,ram128,ram1024):assert p.is_file(),str(p)
dc=shutil.which('dc_shell');assert dc
out=Path(tempfile.mkdtemp(prefix='q12_core_area_',dir='/tmp'))
print('Q12_CORE_DIRECTORY='+str(out),flush=True)
report={'source_identity':identity,'libraries':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (std,ram128,ram1024)},
        'period_ns':6.666666667,'scope':'standalone compute core including private SRAM; excludes codec, loader, fabric and rest of SoC',
        'passed':False,'results':[]}
variants=identity.get('variants',['reference','candidate'])
for variant in variants:
    run=out/variant;run.mkdir();env=dict(os.environ,Q12_STD_DB=str(std),Q12_RAM128_DB=str(ram128),Q12_RAM1024_DB=str(ram1024),
        Q12_CORE_SOURCE=str(here/(variant+'.sv')),Q12_PAIR_SOURCE=str(here/'q12_pair_acc.sv'),Q12_SRAM_SOURCE=str(here/'q12_striped_sram.sv'),Q12_VARIANT=variant)
    start=time.monotonic()
    with (run/'dc.log').open('w') as log:
        p=subprocess.Popen([dc,'-f',str(here/'map_core.tcl')],cwd=str(run),env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (run/'process.json').write_text(json.dumps({'pid':p.pid,'command':[dc,'-f',str(here/'map_core.tcl')],'timeout_seconds':2400}))
        try:rc=p.wait(timeout=2400)
        except BaseException:
            try:os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
            raise
    text=(run/'dc.log').read_text(errors='replace')
    result={'variant':variant,'returncode':rc,'seconds':time.monotonic()-start,
            'metrics':(run/'metrics.txt').read_text() if (run/'metrics.txt').is_file() else None,
            'complete_marker':'Q12_CORE_COMPLETE variant='+variant in text}
    report['results'].append(result)
    report['passed']=len(report['results'])==len(variants) and all(r['returncode']==0 and r['metrics'] and r['complete_marker'] for r in report['results'])
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Q12_CORE_RESULT '+json.dumps(result),flush=True)
    if rc:raise SystemExit(rc)
print('Q12_CORE_COMPLETE='+str(out/'result.json'),flush=True)
