"""Server-only VCS manufacturer SRAM functional regression; starts one task by default."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile,time
from convert_activity import convert
from decode_output import decode_output

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def metrics(text,tag):
 rows=re.findall(r'^'+re.escape(tag)+r' (.+)$',text,re.M)
 if len(rows)!=1:raise ValueError('Missing/duplicate '+tag)
 return {k:int(v)for k,v in re.findall(r'(\w+)=(-?\d+)',rows[0])}
def require_clean_task_log(text):
 # VCS may return zero even when a SystemVerilog $fatal ended the run.
 if len(re.findall(r'^PASS real E203 Q12 vendor task;',text,re.M))!=1 or re.search(r'(?im)^\s*(?:Fatal:|Error:|Error-\[)|\$fatal',text):
  raise ValueError('Missing clean vendor task PASS or Fatal/Error in simulation log')
def explicit_accounting(text):
 status=metrics(text,'Q12_MAILBOX_WAIT');master=metrics(text,'Q12_EXPLICIT_LOADER')
 if status!={'writes':10,'reads':9,'commands':19,'responses':19,'timeouts':0}:
  raise ValueError('Blocking WAIT read/write/ACK/timeout conservation differs')
 if master!={'masters':3,'requests':9,'mailbox_commands':status['commands'],'mailbox_responses':status['commands'],'independent_cpu':1}:
  raise ValueError('Explicit independent loader accounting differs')
 return status,master
def executable_files(exe):
 files=[exe]
 folder=Path(str(exe)+'.daidir')
 if folder.is_dir():files+=sorted(p for p in folder.rglob('*')if p.is_file())
 return {str(p.resolve()):sha(p)for p in files}
def reuse_executable(prior,identity):
 if not prior.get('passed')or prior.get('phase')!='complete' or not prior.get('tasks'):
  raise ValueError('Only a successful vendor task may seed build reuse')
 if prior.get('build_identity')!=identity:raise ValueError('Reuse source/model/compiler identity mismatch')
 exe=Path(prior['executable'])
 files=executable_files(exe)
 if not files or files!=prior['executable_files_sha256']:raise ValueError('Reused executable/runtime changed')
 return exe,files
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--tasks',type=int,default=1)
 ap.add_argument('--models',type=Path,default=Path('/storage1/admin_public_dir/SRAM_Lib_2025'))
 ap.add_argument('--model-identity',type=Path,default=Path.home()/'Desktop/sram_models.json')
 ap.add_argument('--work-root',type=Path,default=Path.home()/'Desktop')
 ap.add_argument('--compile-timeout',type=int,default=1800)
 ap.add_argument('--task-timeout',type=int,default=1800)
 ap.add_argument('--verify-only',action='store_true')
 ap.add_argument('--reuse-build',type=Path,help='Successful prior vendor-run directory; exact source/model/compiler hash match required')
 ap.add_argument('--activity',action='store_true',help='Explicit full-DUT VCD capture; no automatic SAIF or power run')
 ap.add_argument('--saif',action='store_true',help='Capture and convert all full-window activity to SAIF before PASS')
 ap.add_argument('--saif-timeout',type=int,default=1800)
 args=ap.parse_args();args.activity=args.activity or args.saif;bundle=Path(__file__).resolve().parent;m=read(bundle/'manifest.json')
 if m.get('frozen_result_sha256')!='07bc11f0d6301a7570979e70aca022f54845c8bab6468eae58f10ba94aa3a80e':raise ValueError('Wrong final frozen result identity')
 if m.get('firmware_hex_sha256')!='d3c7f0fdb0e5632afd3e927f199b1ece3f442b0c5d44a21021710cc929785ed1' or sha(bundle/'firmware64.hex')!=m['firmware_hex_sha256']:raise ValueError('Wrong final frozen firmware')
 if not 1<=args.tasks<=len(m['tasks']):raise ValueError('task count out of packaged range')
 if min(args.compile_timeout,args.task_timeout,args.saif_timeout)<1:raise ValueError('timeouts must be positive')
 if m.get('format_version')!='q12_x12_w12_y13_h1':raise ValueError('Wrong packet/numeric format')
 if m.get('hardware_external_master')!={'NP':3,'OUTSTANDING':4,'ONE_PER_PORT':'000','no_CPU_output_substitution':True}:raise ValueError('Exact explicit NP3 hardware identity required')
 for n,h in m['files_sha256'].items():
  if Path(n).is_absolute()or'..'in Path(n).parts:raise ValueError('unsafe manifest path')
  if sha(bundle/n)!=h:raise ValueError('Frozen bundle file changed: '+n)
 for p in (bundle/'src').rglob('*'):
  if p.is_file()and p.suffix in ['.v','.sv']and re.search(r'\bmodule\s+RAMSP(?:128|1024|4096)X16\b',p.read_text(encoding='utf-8',errors='replace')):
   raise ValueError('PDK/macro model must not be copied into package')
 identity=read(args.model_identity)
 if identity.get('source_library')!='SRAM_Lib_2025'or identity.get('model_kind')!='official_manufacturer':
  raise ValueError('Existing manufacturer model identity required')
 models=[args.models/n/'verilog'/(n+'.v')for n in m['required_macro_references']]
 for p in models:
  if sha(p)!=identity['files'][p.stem]:raise ValueError('Manufacturer model changed: '+str(p))
 print('Q12_VENDOR_PACKAGE_VERIFIED '+str(bundle),flush=True)
 if args.verify_only:return
 vcs=shutil.which('vcs')
 if not vcs:raise ValueError('vcs is not on PATH')
 out=Path(tempfile.mkdtemp(prefix='qingyu_q12_final_vendor_',dir=str(args.work_root)))
 print('Q12_VENDOR_RUN_DIRECTORY='+str(out),flush=True)
 report={'passed':False,'phase':'compile','scope':'Real E203, independent external NP3 loader master and original bus/shared SRAM; actual manufacturer-model functional simulation, not silicon or timing signoff',
  'manifest_sha256':sha(bundle/'manifest.json'),'model_identity_sha256':sha(args.model_identity),'model_sha256':{str(p):sha(p)for p in models},
  'baseline_evidence':m['baseline_evidence'],'expected_macro_instances':m['expected_macro_instances'],'commands':[],'tasks':[],
  'measurement':m['measurement'],'limits':['Cold independent tasks, historical frozen fixtures','No SDF, post-layout, STA, power or energy result','150 MHz conversion is conditional on same-version timing','Added external ICB boundary organizer acceptance remains pending'],
  'timeouts_seconds':{'compile':args.compile_timeout,'per_task':args.task_timeout,'per_saif':args.saif_timeout}}
 report['activity_requested']=args.activity
 report['saif_requested']=args.saif
 report['frozen_result_sha256']=m['frozen_result_sha256']
 report['firmware_hex_sha256']=m['firmware_hex_sha256']
 active_case=None;active_task=None
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 def run(cmd,log,limit,cwd):
  report['commands'].append([str(x)for x in cmd]);save();start=time.monotonic()
  with log.open('w')as f:
   p=subprocess.Popen([str(x)for x in cmd],cwd=cwd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
   try:rc=p.wait(timeout=limit)
   except BaseException:
    import signal
    try:os.killpg(p.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:
     try:os.killpg(p.pid,signal.SIGKILL)
     except ProcessLookupError:pass
     p.wait()
    raise
  if rc:raise RuntimeError('tool return=%d; see %s'%(rc,log))
  return time.monotonic()-start
 save()
 try:
  includes=['+incdir+'+str(bundle/p)for p in m['include_directories']]
  sources=[bundle/p for p in m['source_order']]+models
  (out/'sources.f').write_text(''.join('"'+str(p)+'"\n'for p in sources))
  flags=['-full64','-sverilog','-timescale=1ns/1ps','+define+DISABLE_SV_ASSERTION=1',
    '+define+ARM_UD_MODEL','+define+Q12_USE_VENDOR_MACROS','-debug_access+all','-top','tb_q12soc']
  build_identity={'manifest_sha256':report['manifest_sha256'],'model_sha256':report['model_sha256'],
   'model_identity_sha256':report['model_identity_sha256'],'vcs_path':str(Path(vcs).resolve()),
   'vcs_sha256':sha(Path(vcs).resolve()),'flags':flags,'source_order':m['source_order'],'include_order':m['include_directories']}
  report['build_identity']=build_identity
  cmd=[vcs,*flags,*includes,
    '-f',out/'sources.f','-Mdir='+str(out/'csrc'),'-o',out/'simv']
  if args.reuse_build:
   prior_dir=args.reuse_build.resolve();prior=read(prior_dir/'result.json')
   exe,exe_files=reuse_executable(prior,build_identity)
   report.update(reused_build=str(prior_dir),compile_seconds=0)
  else:
   report['compile_seconds']=run(cmd,out/'compile.log',args.compile_timeout,out)
   if re.search(r'Error-\[|\bError:|\bFatal:',(out/'compile.log').read_text(errors='replace')):
    raise ValueError('Compile log contains error')
   exe=out/'simv';exe_files=executable_files(exe)
  report.update(executable=str(exe),executable_files_sha256=exe_files)
  report['phase']='simulation';save()
  for row in m['tasks'][:args.tasks]:
   case=out/row['directory'];case.mkdir();active_case=case;active_task=row['task']
   (case/'result.json').write_text(json.dumps({'passed':False,'phase':'simulation','task':active_task})+'\n')
   for name in ['input.hex','expected.hex','dense.hex']:shutil.copy2(bundle/'tasks'/row['directory']/name,case/name)
   shutil.copy2(bundle/'firmware64.hex',case/'firmware64.hex')
   cmd=[exe,'+FIRMWARE=firmware64.hex','+INPUT=input.hex','+EXPECTED=expected.hex','+OUTPUT_DUMP=observed.hex',
    '+INPUT_WORDS='+str(row['input_words']),'+OUTPUT_WORDS='+str(row['output_actual_write_words']),'+LAYER='+row['task'][5:7]]
   if args.activity:cmd+=['+ACTIVITY=full_runtime.vcd']
   duration=run(cmd,case/'simulation.log',args.task_timeout,case);text=(case/'simulation.log').read_text(errors='replace')
   require_clean_task_log(text)
   v=metrics(text,'Q12SOC_METRICS');counts=metrics(text,'Q12_VENDOR_MACROS');pre=metrics(text,'Q12_POISON_PRELOAD_COMPLETE');rb=metrics(text,'Q12_MACRO_READBACK_COMPLETE')
   mailbox_status,explicit_loader=explicit_accounting(text)
   if counts!={'RAMSP128X16':30,'RAMSP1024X16':6,'RAMSP4096X16':80,'total':116}:raise ValueError('Wrong elaborated macro counts')
   if pre['commands']!=131072 or pre['responses']!=131072 or pre['tensor_words']!=0 or pre['CPU_reset']!=0:raise ValueError('Invalid poison initialization')
   if rb['words']!=131072 or rb['source_words']!=row['input_words']or rb['output_slots']!=10353:raise ValueError('Incomplete physical readback')
   if v['reads']!=row['input_words']or v['writes']!=row['output_actual_write_words']or v['loader_commands']!=row['input_words']+45:raise ValueError('Traffic conservation mismatch')
   if v['full_window_cycles']<=v['start_to_ack']:raise ValueError('Loading window missing')
   def words(p):return[int(x,16)for x in re.sub(r'//[^\n]*','',p.read_text()).split()]
   observed=words(case/'observed.hex')
   if len(observed)!=10353 or observed!=words(case/'expected.hex'):raise ValueError('Physical output differs from reference')
   dense=[w-65536 if w&32768 else w for w in words(case/'dense.hex')]
   decoded=decode_output(observed)
   if len(dense)!=25344 or decoded!=dense:raise ValueError('Independent decoded 25344-value result differs')
   task={'task':row['task'],'directory':row['directory'],'metrics':v,'phases':metrics(text,'Q12SOC_PHASES'),'macro_counts':counts,'mailbox_status':mailbox_status,'explicit_loader':explicit_loader,'wall_seconds':duration,'log_sha256':sha(case/'simulation.log'),'readback_sha256':sha(case/'observed.hex'),'decoded_values_checked':len(decoded)}
   for tag in ['Q12_PROFILE_BUS','Q12_PROFILE_CORE','Q12_PROFILE_EMPTY']:task[tag]=metrics(text,tag)
   baseline=read(bundle/'evidence/behavioral_soc_result.json')
   baseline_task=[t for t in baseline['tasks'] if t['task']==row['task']]
   if len(baseline_task)==1:
    prior=baseline_task[0]['metrics'];task['behavioral_full_window_cycles']=prior['full_window_cycles']
    task['cycles_delta_from_behavioral']=v['full_window_cycles']-prior['full_window_cycles']
    for key in ['reads','writes','cpu_commands','loader_commands','fabric_commands','responses']:
     if v[key]!=prior[key]:raise ValueError('Vendor/behavioral transaction conservation differs: '+key)
   if args.activity:
    first=metrics(text,'Q12_FULL_START');last=metrics(text,'Q12_FULL_END');vcd=case/'full_runtime.vcd'
    if not vcd.is_file()or vcd.stat().st_size<100:raise ValueError('Missing activity VCD')
    if last['cycle']-first['cycle']+1!=v['full_window_cycles']or last['time_ps']<=first['time_ps']:raise ValueError('Activity boundary mismatch')
    task['activity']={'vcd':str(vcd),'bytes':vcd.stat().st_size,'start_ps':first['time_ps'],'end_ps':last['time_ps'],
     'duration_ps':last['time_ps']-first['time_ps'],'scope':'tb_q12soc/dut','timescale_ps':1,'note':'VCD also includes firmware boot; explicit SAIF conversion slices exact FULL_START/FULL_END timestamps. Timestamp duration excludes inclusive-cycle reporting convention; do not substitute cycles without conversion.'}
   task.update(passed=True,phase='functional_complete')
   (case/'result.json').write_text(json.dumps(task,indent=2)+'\n')
   report['tasks'].append(task)
   save();print('Q12_VENDOR_TASK '+json.dumps(report['tasks'][-1]),flush=True)
  for n,h in m['files_sha256'].items():
   if sha(bundle/n)!=h:raise ValueError('Package changed during run: '+n)
  for p,h in report['model_sha256'].items():
   if sha(p)!=h:raise ValueError('Macro model changed during run')
  if executable_files(exe)!=exe_files:raise ValueError('Executable/runtime changed during run')
  mean=sum(t['metrics']['full_window_cycles']for t in report['tasks'])/len(report['tasks'])
  report.update(functional_passed=True,phase='functional_complete',mean_full_window_cycles=mean,mean_full_ms_at_assumed_150mhz=mean/150000,throughput_tasks_s_at_assumed_150mhz=150000000/mean)
  save()
  if args.saif:
   active_case=None;active_task=None;report['phase']='activity_conversion';save()
   activity=convert(out,args.saif_timeout)
   report['activity_conversion']=activity
   for task,record in zip(report['tasks'],activity['tasks']):
    if task['task']!=record['task']:raise ValueError('SAIF task ordering differs')
    task['activity'].update(record['activity'])
    task.update(passed=True,phase='complete')
    (out/task['directory']/'result.json').write_text(json.dumps(task,indent=2)+'\n')
  report.update(passed=True,phase='complete');save();print('Q12_VENDOR_COMPLETE='+str(out/'result.json'),flush=True)
 except BaseException as exc:
  report.update(passed=False,failed_phase=report['phase'],phase='failed',error=str(exc),failed_task=active_task);save()
  if active_case is not None:(active_case/'result.json').write_text(json.dumps({'passed':False,'phase':'failed','task':active_task,'error':str(exc)},indent=2)+'\n')
  print('Q12_VENDOR_STOPPED='+str(out),flush=True);raise
if __name__=='__main__':main()
