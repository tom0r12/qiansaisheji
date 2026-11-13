#!/usr/bin/env python3
"""Run a derived candidate against frozen Q12 tasks without changing the baseline."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time

HERE=Path(__file__).resolve().parent
SOURCE='src/q12/core_datareset/q12_task4.sv'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())

def main():
    record=read(HERE/'replay_identity.json')
    # Only inspect the known task root; leave all existing runs and manifests intact.
    known=Path('/tmp/q12_final_s4_36usr_20261113')
    packages=[p.parent for p in known.glob('*/manifest.json') if sha(p)==record['manifest_sha256']]
    if len(packages)!=1: raise ValueError('Expected one exact frozen vendor package; found '+str(packages))
    package=packages[0];m=read(package/'manifest.json')
    for name,h in m['files_sha256'].items():
        if sha(package/name)!=h: raise ValueError('Baseline package changed: '+name)
    candidate=HERE/'q12_task4.sv'
    if sha(candidate)!=record['candidate_sha256']: raise ValueError('Candidate identity mismatch')
    old=(package/SOURCE).read_text();new=candidate.read_text()
    if record.get('data_hold'):
        for line in ['            for(integer b=0;b<3;b=b+1) begin burst_data_q[b]<=0;burst_addr_q[b]<=0;end\n',
                     '            for(integer c=0;c<32;c=c+1) begin bias_load_q[c]<=0;shift_load_q[c]<=0;end\n']:
            if old.count(line)!=1:raise ValueError('Reset-removal baseline pattern changed')
            old=old.replace(line,'')
    func=re.compile(r'function automatic logic \[12:0\] requantize\(.*?endfunction',re.S)
    def normalized(s):return re.sub(r'\s+','',re.sub(r'//[^\n]*|/\*.*?\*/','',s,flags=re.S))
    if normalized(func.sub('FUNCTION',old))!=normalized(func.sub('FUNCTION',new)):raise ValueError('Unexpected control/datapath change')
    model_identity=Path.home()/'Desktop/sram_models.json'
    identity=read(model_identity)
    if identity.get('model_kind')!='official_manufacturer':raise ValueError('Wrong macro identity')
    models=[Path('/storage1/admin_public_dir/SRAM_Lib_2025')/n/'verilog'/(n+'.v') for n in m['required_macro_references']]
    for p in models:
        if sha(p)!=identity['files'][p.stem]:raise ValueError('Model changed: '+str(p))
    spec=importlib.util.spec_from_file_location('baseline_checks',str(package/'run_vendor.py'))
    import sys
    sys.path.insert(0,str(package))
    helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
    baseline=read(package/'evidence/behavioral_soc_result.json')
    expected={t['task']:t for t in baseline['tasks']}
    out=Path(tempfile.mkdtemp(prefix='q12_area_replay_',dir='/tmp'))
    report={'candidate':record.get('candidate','q12_area_requant_v1'),'passed':False,'phase':'compile','package':str(package),
            'baseline_manifest_sha256':sha(package/'manifest.json'),'candidate_sha256':sha(candidate),
            'source_override':SOURCE,'models':{str(p):sha(p) for p in models},'tasks':[],
            'limits':['Functional vendor-model simulation, not timing signoff','150 MHz throughput remains conditional on mapped timing',
                      'NP3 loader organizer acceptance inherited as OPEN from baseline']}
    def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(cmd,cwd,log,timeout):
        start=time.monotonic()
        with log.open('w') as f:
            p=subprocess.Popen([str(x) for x in cmd],cwd=str(cwd),stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                rc=p.wait(timeout=timeout)
            except BaseException:
                try:os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid,signal.SIGKILL);p.wait()
                raise
        if rc:raise RuntimeError('Tool failed; see '+str(log))
        return time.monotonic()-start
    print('Q12_AREA_REPLAY_DIRECTORY='+str(out),flush=True);save()
    try:
        vcs=shutil.which('vcs')
        if not vcs:raise ValueError('vcs unavailable')
        sources=[candidate if n==SOURCE else package/n for n in m['source_order']]+models
        if sources.count(candidate)!=1:raise ValueError('Override not used exactly once')
        if record.get('data_hold'):
            monitor=HERE/'q12_data_init_check.sv'
            if sha(monitor)!=record['monitor_sha256']:raise ValueError('Monitor changed')
            sources.append(monitor)
            report['init_monitor_sha256']=sha(monitor)
        (out/'sources.f').write_text(''.join('"'+str(p)+'"\n' for p in sources))
        flags=['-full64','-sverilog','-timescale=1ns/1ps','+define+DISABLE_SV_ASSERTION=1','+define+ARM_UD_MODEL',
               '+define+Q12_USE_VENDOR_MACROS','-debug_access+all','-top','tb_q12soc']
        cmd=[vcs]+flags+['+incdir+'+str(package/n) for n in m['include_directories']]+['-f',out/'sources.f','-Mdir='+str(out/'csrc'),'-o',out/'simv']
        report['compile_command']=[str(x) for x in cmd]
        report['compile_seconds']=run(cmd,out,out/'compile.log',900)
        if re.search(r'Error-\[|\bError:|\bFatal:',(out/'compile.log').read_text(errors='replace')):raise ValueError('Compile error')
        report['phase']='simulation';save()
        def words(p):return [int(x,16) for x in re.sub(r'//[^\n]*','',p.read_text()).split()]
        for task in m['tasks']:
            case=out/task['directory'];case.mkdir()
            for n in ['input.hex','expected.hex','dense.hex']:shutil.copy2(package/'tasks'/task['directory']/n,case/n)
            shutil.copy2(package/'firmware64.hex',case/'firmware64.hex')
            cmd=[out/'simv','+FIRMWARE=firmware64.hex','+INPUT=input.hex','+EXPECTED=expected.hex','+OUTPUT_DUMP=observed.hex',
                 '+INPUT_WORDS='+str(task['input_words']),'+OUTPUT_WORDS='+str(task['output_actual_write_words']),'+LAYER='+task['task'][5:7]]
            elapsed=run(cmd,case,case/'simulation.log',600)
            text=(case/'simulation.log').read_text(errors='replace')
            helpers.require_clean_task_log(text)
            if record.get('data_hold'):
                init=helpers.metrics(text,'Q12_DATA_INIT_CHECK')
                if init!={'bursts':512,'metadata':256}:raise ValueError('Incomplete initialized-before-use coverage: '+str(init))
            status,loader=helpers.explicit_accounting(text)
            metrics=helpers.metrics(text,'Q12SOC_METRICS')
            counts=helpers.metrics(text,'Q12_VENDOR_MACROS')
            assert counts=={'RAMSP128X16':30,'RAMSP1024X16':6,'RAMSP4096X16':80,'total':116}
            pre=helpers.metrics(text,'Q12_POISON_PRELOAD_COMPLETE');rb=helpers.metrics(text,'Q12_MACRO_READBACK_COMPLETE')
            assert pre['commands']==pre['responses']==131072 and pre['tensor_words']==0 and pre['CPU_reset']==0
            assert rb['words']==131072 and rb['source_words']==task['input_words'] and rb['output_slots']==10353
            observed=words(case/'observed.hex');assert len(observed)==10353 and observed==words(case/'expected.hex')
            dense=[w-65536 if w&32768 else w for w in words(case/'dense.hex')]
            assert len(dense)==25344 and helpers.decode_output(observed)==dense
            prior=expected[task['task']]['metrics']
            for key in ['full_window_cycles','reads','writes','cpu_commands','loader_commands','fabric_commands','responses']:
                if metrics[key]!=prior[key]:raise ValueError('Cycle/traffic differs: '+key)
            result={'task':task['task'],'passed':True,'metrics':metrics,'baseline_cycles':prior['full_window_cycles'],
                    'cycle_delta':metrics['full_window_cycles']-prior['full_window_cycles'],'seconds':elapsed,
                    'values_checked':len(dense),'macro_counts':counts,'mailbox':status,'loader':loader,
                    'log_sha256':sha(case/'simulation.log'),'readback_sha256':sha(case/'observed.hex')}
            if record.get('data_hold'):result['initialized_before_use_checks']=init
            (case/'result.json').write_text(json.dumps(result,indent=2)+'\n');report['tasks'].append(result);save()
            print('Q12_AREA_REPLAY_TASK '+json.dumps(result),flush=True)
        for n,h in m['files_sha256'].items():
            if sha(package/n)!=h:raise ValueError('Baseline modified during run')
        assert sha(candidate)==record['candidate_sha256']
        report.update(passed=True,phase='complete',mean_full_window_cycles=sum(t['metrics']['full_window_cycles'] for t in report['tasks'])/len(report['tasks']))
        report['throughput_at_assumed_150mhz']=150000000/report['mean_full_window_cycles'];save()
        print('Q12_AREA_REPLAY_COMPLETE='+str(out/'result.json'),flush=True)
    except BaseException as exc:
        report.update(phase='failed',error=str(exc));save();raise

if __name__=='__main__':main()
