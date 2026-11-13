"""Server-only source-frozen full-SoC mapping and same-window power assessment."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,shutil,signal,subprocess,sys,tempfile,time
import audit_reports
import formal_audit
from validate_activity import check_saif
HERE=Path(__file__).resolve().parent
STD='scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db'
RAMS=['RAMSP128X16_tt_1p10v_1p10v_25c.db','RAMSP1024X16_tt_1p10v_1p10v_25c.db','RAMSP4096X16_tt_1p10v_1p10v_25c.db']
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def put(p,obj):
    q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(obj,indent=2)+'\n');q.replace(p)
def verify():
    m=read(HERE/'package_identity.json')
    for n,h in m['files'].items():
        if sha(HERE/n)!=h:raise ValueError('Package/source changed '+n)
    hw=read(HERE/'hardware/manifest.json')
    if sha(HERE/'hardware/manifest.json')!=m['hardware_manifest_sha256'] or hw['soc_result_sha256']!=m['baseline_result_sha256']:raise ValueError('Hardware identity mismatch')
    r=read(HERE/'hardware/evidence/behavioral_soc12.json')
    if not r['passed'] or not r['blocking_wait'] or len(r['tasks'])!=12 or sha(HERE/'hardware/evidence/behavioral_soc12.json')!=m['baseline_result_sha256']:raise ValueError('Wrong exact candidate')
    if len(r['source_identity']['experimental_overrides'])!=6:raise ValueError('Exact codec/rowpair/core overrides absent')
    return m
def mapping_fingerprint(manifest):
    subset={n:h for n,h in manifest['files'].items()if n.startswith('hardware/')or n in ['map.tcl','audit.tcl']}
    return hashlib.sha256(json.dumps(subset,sort_keys=True).encode()).hexdigest()
def stop_owned(p):
    if p.poll()is not None:return
    try:os.killpg(p.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGKILL);p.wait()
def command(cmd,cwd,env,seconds,log,marker,optional_reports=False):
    start=time.time()
    with log.open('w')as f:
        p=subprocess.Popen(cmd,cwd=str(cwd),env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        put(cwd/'process.json',{'pid':p.pid,'command':cmd,'started_utc':datetime.datetime.utcnow().isoformat()+'Z','deadline_seconds':seconds})
        try:
            while p.poll()is None:
                if time.time()-start>seconds:raise TimeoutError('Stage deadline reached after %ds'%seconds)
                time.sleep(5)
        except BaseException:
            stop_owned(p);raise
    text=log.read_text(errors='replace')
    errors=re.findall(r'^Error:.*$',text,re.M)
    critical_text=re.sub(r'^Q12_OPTIONAL_REPORT_BEGIN=([^\n]+)\n.*?^Q12_OPTIONAL_REPORT_END=\1\s*$', '',text,flags=re.M|re.S)if optional_reports else text
    if p.returncode or not re.search(r'^'+re.escape(marker)+r'\s*$',text,re.M)or re.search(r'^Error:',critical_text,re.M):raise RuntimeError('EDA stage failed; inspect '+str(log))
    return {'elapsed_seconds':time.time()-start,'returncode':p.returncode,'log_sha256':sha(log),'tool_diagnostics':errors}
def libraries(args):
    desktop=Path.home()/'Desktop'
    standard=args.std_db or desktop/'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v'/STD
    sr=args.sram_root or desktop/'qingyu_sram_corners'
    files=[standard]+[sr/n for n in RAMS]
    for p,n in zip(files,[STD]+RAMS):
        if not p.is_file() or p.name!=n:raise ValueError('Matching official TT DB required: '+str(p))
    if 'smic_official'not in str(standard) or 'SCC40NLL'not in str(standard):raise ValueError('Official SCC40NLL installation path required')
    return [p.resolve()for p in files]
def task_saif(task,vendor):
    a=task['activity']
    if a.get('scope')!='tb_q12soc/dut' or a.get('timescale_ps')!=1:raise ValueError('Unexpected activity scope or precision')
    if not all(isinstance(a[k],int)for k in ['start_ps','end_ps','duration_ps']) or a['end_ps']-a['start_ps']!=a['duration_ps'] or a['duration_ps']<=0:raise ValueError('Malformed task timestamps')
    p=(vendor/a['saif_relpath']).resolve()
    if vendor.resolve()not in p.parents or sha(p)!=a['saif_sha256']:raise ValueError('Changed/outside SAIF')
    return p,a
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['synth','formal','power','post','all'],default='synth')
    parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--run-dir',type=Path)
    parser.add_argument('--work-root',type=Path,default=Path.home()/'Desktop',help='Writable result filesystem; source package and libraries remain read-only')
    parser.add_argument('--vendor-run',type=Path)
    parser.add_argument('--allow-tooling-update',action='store_true',help='Allow changed reporting tools only when mapping inputs are byte-identical')
    parser.add_argument('--recheck-reports',action='store_true',help='Re-audit existing formal/power reports without rerunning EDA')
    parser.add_argument('--layers',choices=['1','12'],default='12')
    parser.add_argument('--synth-seconds',type=int,default=10800)
    parser.add_argument('--formal-seconds',type=int,default=7200)
    parser.add_argument('--power-seconds',type=int,default=1200)
    parser.add_argument('--std-db',type=Path);parser.add_argument('--sram-root',type=Path)
    args=parser.parse_args();manifest=verify()
    print('Q12_FINAL_PACKAGE_VERIFIED '+manifest['baseline_result_sha256'],flush=True)
    if args.verify_only:return
    if os.name!='posix':raise RuntimeError('EDA requires the Linux contest server')
    if not 3600<=args.synth_seconds<=21600:raise ValueError('Synthesis deadline must be 1..6 hours')
    import fcntl
    lock=(Path(tempfile.gettempdir())/('.q12_final_'+manifest['baseline_result_sha256'][:16]+'.lock')).open('a+')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('Same exact candidate assessment is already running; no duplicate launched')
    dbs=libraries(args)
    args.work_root.mkdir(parents=True,exist_ok=True)
    out=args.run_dir.resolve()if args.run_dir else Path(tempfile.mkdtemp(prefix='qingyu_q12_final_assessment_',dir=str(args.work_root.resolve())))
    if not out.exists():out.mkdir()
    print('Q12_FINAL_ASSESSMENT_DIRECTORY='+str(out),flush=True)
    result=read(out/'result.json')if(out/'result.json').exists()else{'schema':'q12-final-assessment-result-v1','passed':False,'baseline_result_sha256':manifest['baseline_result_sha256'],'mapping_fingerprint':mapping_fingerprint(manifest),'package_identity_sha256':sha(HERE/'package_identity.json'),'libraries_sha256':{str(p):sha(p)for p in dbs},'stages':{},'limits':['TT prelayout EDA estimate, not silicon measurement','Formal and timing outcomes reported independently','Official dataset/loader-interface acceptance not implied','Power uses exact task activity, never analytic extrapolation']}
    if result['baseline_result_sha256']!=manifest['baseline_result_sha256']or result.get('mapping_fingerprint')!=mapping_fingerprint(manifest):raise ValueError('Run directory belongs to different frozen mapping inputs')
    if result['package_identity_sha256']!=sha(HERE/'package_identity.json'):
        if not args.allow_tooling_update:raise ValueError('Reporting package changed; review then use --allow-tooling-update with identical mapping inputs')
        result.setdefault('reporting_tool_updates',[]).append({'previous':result['package_identity_sha256'],'current':sha(HERE/'package_identity.json'),'mapping_unchanged':True})
        result['package_identity_sha256']=sha(HERE/'package_identity.json')
    if result['libraries_sha256']!={str(p):sha(p)for p in dbs}:raise ValueError('Physical libraries changed')
    env=os.environ.copy();env.update(Q12_PACKAGE=str(HERE),Q12_LIBRARIES=' '.join('{'+str(p)+'}'for p in dbs))
    (out/'tmp').mkdir(exist_ok=True);env['TMPDIR']=str(out/'tmp')
    env.update(dict(zip(['Q12_STD_DB','Q12_RAM128_DB','Q12_RAM1024_DB','Q12_RAM4096_DB'],map(str,dbs))))
    def stage(name,operation):
        old=result['stages'].get(name,{})
        if old.get('complete'):
            for n,h in old.get('outputs_sha256',{}).items():
                if sha(out/n)!=h:raise ValueError('Completed stage output changed '+n)
            if args.recheck_reports and name=='formal':
                old['audit']=formal_audit.audit(out/name,synth_dir,log_path=out/name/'formal.log')
                old['passed']=bool(old.get('tool_verified')and old['audit']['accepted'])
                old['outputs_sha256'][name+'/formal_audit.json']=sha(out/name/'formal_audit.json')
            if args.recheck_reports and name.startswith('power_layer'):
                try:old.update(audit_reports.power(out/name,old['end_ps']-old['start_ps']),accepted=True)
                except Exception as e:old.update(accepted=False,acceptance_error=str(e))
            put(out/'result.json',result)
            print('Q12_SKIP_COMPLETED='+name,flush=True);return
        cwd=out/name
        if cwd.exists():raise ValueError('Incomplete existing stage retained; use fresh run directory or reviewed recovery: '+name)
        cwd.mkdir();result['current_stage']=name;put(out/'result.json',result)
        (out/'STATUS.txt').write_text(name+' RUNNING '+datetime.datetime.utcnow().isoformat()+'Z\n')
        print('Q12_STAGE_BEGIN='+name,flush=True)
        try:
            record=operation(cwd);record['complete']=True
            record['outputs_sha256']={p.relative_to(out).as_posix():sha(p)for p in cwd.iterdir()if p.is_file()and p.suffix in ['.json','.tsv','.txt','.rpt','.v','.sdc','.svf']}
            result['stages'][name]=record
        except Exception as e:
            result['stages'][name]={'complete':False,'error':str(e)};put(out/'result.json',result)
            (out/'STATUS.txt').write_text(name+' FAILED '+str(e)+'\n');raise
        put(out/'result.json',result);print('Q12_STAGE_END='+name,flush=True)
    synth_dir=out/'synth'
    def synth(cwd):
        tool=shutil.which('dc_shell')
        if not tool:raise RuntimeError('dc_shell unavailable')
        record=command([tool,'-f',str(HERE/'map.tcl')],cwd,env,args.synth_seconds,cwd/'dc.log','Q12_FINAL_SYNTH_COMPLETE',optional_reports=True)
        record.update(audit_reports.synth(cwd));return record
    if args.phase in ['synth','all']:stage('synth',synth)
    if not result['stages'].get('synth',{}).get('complete'):raise ValueError('Successful same-run synthesis required')
    for n,h in result['stages']['synth']['outputs_sha256'].items():
        if sha(out/n)!=h:raise ValueError('Mapped evidence changed '+n)
    env.update(Q12_NETLIST=str(synth_dir/'mapped.v'),Q12_SDC=str(synth_dir/'mapped.sdc'),Q12_SVF=str(synth_dir/'mapped.svf'))
    if args.phase in ['formal','post','all']:
        def formal(cwd):
            tool=shutil.which('fm_shell')
            if not tool:return {'attempted':False,'passed':False,'reason':'fm_shell unavailable'}
            formal_audit.bind_inputs(HERE,synth_dir,cwd,dbs)
            rec={'attempted':True,'passed':False}
            try:
                rec.update(command([tool,'-f',str(HERE/'formal.tcl')],cwd,env,args.formal_seconds,cwd/'formal.log','Q12_FINAL_FORMAL_COMPLETE'))
                rec['tool_verified']=True
            except Exception as e:rec.update(tool_verified=False,error=str(e))
            rec['audit']=formal_audit.audit(cwd,synth_dir,log_path=cwd/'formal.log')
            rec['passed']=bool(rec.get('tool_verified')and rec['audit']['accepted'])
            return rec
        stage('formal',formal)
    if args.phase in ['power','post','all']:
        if not args.vendor_run:raise ValueError('--vendor-run required for exact activity')
        vendor=args.vendor_run.resolve();vr=read(vendor/'result.json')
        evidence=vr.get('baseline_evidence',{})
        if not vr.get('passed')or not vr.get('functional_passed')or evidence.get('sha256')!=manifest['baseline_result_sha256']or len(vr.get('tasks',[]))!=12:raise ValueError('Exact completed 12-layer vendor SAIF run required')
        result['vendor_result_sha256']=sha(vendor/'result.json');result['vendor_run']=str(vendor)
        macros=audit_reports.macro_rows(synth_dir/'macros_mapped.tsv')
        tasks=vr['tasks'][:int(args.layers)]
        for index,task in enumerate(tasks):
            def power(cwd,task=task):
                saif,activity=task_saif(task,vendor)
                preflight=check_saif(saif,activity['start_ps'],activity['end_ps'],macros)
                put(cwd/'activity_preflight.json',preflight)
                localenv=env.copy();localenv['Q12_SAIF']=str(saif)
                tool=shutil.which('pt_shell')
                if not tool:raise RuntimeError('pt_shell unavailable')
                rec=command([tool,'-f',str(HERE/'power.tcl')],cwd,localenv,args.power_seconds,cwd/'pt.log','Q12_FINAL_POWER_REPORTS_COMPLETE',optional_reports=True)
                rec.update(task=task['task'],saif_sha256=sha(saif),start_ps=activity['start_ps'],end_ps=activity['end_ps'])
                try:
                    watts=audit_reports.power_value((cwd/'power.rpt').read_text(errors='replace'),(cwd/'power_units.rpt').read_text(errors='replace'))
                    rec['provisional_unqualified']={'power_w':watts,'energy_uj':watts*activity['duration_ps']*1e-6,'reason':'Numerical units parsed; coverage/model qualification is evaluated separately'}
                except Exception as e:rec['units_error']=str(e)
                try:rec.update(audit_reports.power(cwd,activity['duration_ps']),accepted=True)
                except Exception as e:rec.update(accepted=False,acceptance_error=str(e))
                return rec
            stage('power_layer%02d'%index,power)
            if not result['stages']['power_layer%02d'%index].get('accepted'):
                result['power_acceptance_blocked']=True
                # Retain all twelve exact-window reports despite report-format
                # or coverage qualification problems; never extrapolate layer0.
    powers=[v for k,v in result['stages'].items()if k.startswith('power_layer')]
    if len(powers)==12 and all(x.get('accepted')for x in powers):
        result['mean_energy_uj']=sum(x['energy_uj']for x in powers)/12
        result['mean_power_w_weighted']=sum(x['energy_uj']for x in powers)*1e6/sum(x['duration_ps']for x in powers)
        result['power_complete']=True
    result['passed']=bool(result.get('power_complete')and result['stages'].get('formal',{}).get('passed'))
    result['current_stage']='finished_requested_phase';put(out/'result.json',result)
    (out/'STATUS.txt').write_text('REQUESTED_PHASE_COMPLETE '+args.phase+' passed='+str(result['passed'])+'\n')
    print('Q12_REQUESTED_PHASE_COMPLETE='+str(out/'result.json'),flush=True)
if __name__=='__main__':main()
