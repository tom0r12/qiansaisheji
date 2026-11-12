"""Consume verified exports and measure the frozen real E203 across all256 records.

The task deliberately preserves the existing preload timing limitation.
It does not call this population the official600 evaluation.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shutil,subprocess,sys,tempfile,time

ROOT=Path(__file__).resolve().parents[1]
EXPORT=ROOT/'build/int8_full_validation_packets_20261112'
SEED=ROOT/'build/int8soc/20261111T174218864779Z'
RUNNER=ROOT/'experiments/integration/int8soc/run_soc.py'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,data):
    temporary=path.with_suffix('.json.tmp');temporary.write_text(json.dumps(data,indent=2)+'\n');temporary.replace(path)
def relative_path(name):
    p=(ROOT/name.replace('\\','/')).resolve();assert p.is_relative_to(ROOT);return p

def main():
    prereg_path=EXPORT/'preregistration.json';prereg=json.loads(prereg_path.read_text())
    assert len(prereg['records'])==256
    seed=json.loads((SEED/'result.json').read_text());assert seed['passed'] and seed['reuse_contract_version']==2
    assert seed['core_directory']=='experiments/arithmetic/winograd_task8_prefetch'
    assert seed['engine_directory']=='experiments/integration/int8stream_dual'
    assert seed['codec_directory']=='experiments/codec/rice32_bounded'
    assert sha(RUNNER)==seed['runner_sha256']
    out=ROOT/'build/int8_full_validation_soc_20261112_r2';out.mkdir(exist_ok=True)
    identity={'schema':'qingyu-int8-full-validation-real-e203-v1','script_sha256':sha(Path(__file__)),
      'runner_sha256':sha(RUNNER),'seed_report':SEED.relative_to(ROOT).as_posix(),'seed_report_sha256':sha(SEED/'result.json'),
      'packet_preregistration_sha256':sha(prereg_path),'records':prereg['records'],
      'scope':'All frozen256 validation records x12 task layers, real E203, unchanged official fabric. CPU first configuration to final output-marker ACK; initial source preload excluded. No official600/loader/STA/area/whole-SoC energy claim.'}
    identity_path=out/'preregistration.json'
    if identity_path.exists():assert json.loads(identity_path.read_text())==identity
    else:save(identity_path,identity)
    report_path=out/'result.json'
    report=json.loads(report_path.read_text()) if report_path.exists() else {'passed':False,'phase':'running','tasks':0,'runs':[],'attempts':[]}
    report['preregistration_sha256']=sha(identity_path);report['scope']=identity['scope']
    existing={r['sample_index']:r for r in report['runs']};assert len(existing)==len(report['runs'])
    # The original testbench stores filenames in128 bytes. Keep unchanged
    # compiled RTL and stage byte-identical packets in a short ASCII location.
    staging=Path(tempfile.mkdtemp(prefix='qingyu_fullval_'))
    report.setdefault('staging_directories',[]).append(str(staging))
    if not existing:
        old_path=ROOT/'build/int8_full_validation_soc_20261112/result.json'
        old_prereg=old_path.parent/'preregistration.json'
        if old_path.exists():
            old=json.loads(old_path.read_text());old_identity=json.loads(old_prereg.read_text())
            for key in ['seed_report_sha256','packet_preregistration_sha256','runner_sha256','records']:
                assert old_identity[key]==identity[key]
            for entry in old['runs']:
                child_path=relative_path(entry['result']);child=json.loads(child_path.read_text())
                assert sha(child_path)==entry['result_sha256'] and child['passed']
                assert child['sample_index']==entry['sample_index'] and child['simulator_sha256']==seed['simulator_sha256']
                assert len(entry['metrics'])==12
                report['runs'].append(entry);existing[entry['sample_index']]=entry;report['tasks']+=12
            report['inherited_passed_results']={'path':old_path.relative_to(ROOT).as_posix(),'sha256':sha(old_path),'count':len(old['runs'])}
    save(report_path,report)
    print(out,flush=True)
    try:
        for index in range(256):
            if index in existing:
                entry=existing[index];path=relative_path(entry['result'])
                assert sha(path)==entry['result_sha256'] and json.loads(path.read_text())['passed'];continue
            deadline=time.monotonic()+1800
            while True:
                exports=json.loads((EXPORT/'result.json').read_text())
                matches=[x for x in exports['results'] if x['sample_index']==index]
                if matches:break
                assert time.monotonic()<deadline,'Timed out waiting for completed export sample'+str(index)
                time.sleep(5)
            assert len(matches)==1
            packet=relative_path(matches[0]['path']);assert sha(packet)==matches[0]['sha256']
            short_images=staging/f's{index:03d}'
            shutil.copytree(packet.parent,short_images)
            files={str(p.relative_to(packet.parent)):sha(p) for p in packet.parent.rglob('*') if p.is_file()}
            assert files=={str(p.relative_to(short_images)):sha(p) for p in short_images.rglob('*') if p.is_file()}
            assert len(str(short_images/'layer11/expected_output.hex').encode())<128
            timestamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            log=out/f'sample{index:03d}_{timestamp}.log'
            command=[sys.executable,str(RUNNER),'--layers','12','--reuse-build',str(SEED),
                '--images',str(short_images),'--core-dir',seed['core_directory'],
                '--engine-dir',seed['engine_directory'],'--codec-dir',seed['codec_directory'],'--jobs','2']
            with log.open('w') as output:
                child=subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,timeout=1200)
            report['attempts'].append({'sample_index':index,'returncode':child.returncode,'log':log.name,'log_sha256':sha(log)})
            save(report_path,report)
            assert child.returncode==0,'Subrun failed: '+str(log)
            found=re.findall(r'^PASS (.+/result.json)$',log.read_text(),re.M);assert len(found)==1
            path=Path(found[0]).resolve();assert path.is_relative_to(ROOT)
            data=json.loads(path.read_text())
            assert data['passed'] and data['sample_index']==index and len(data['layers'])==12
            assert sha(RUNNER)==identity['runner_sha256'] and sha(prereg_path)==identity['packet_preregistration_sha256']
            assert files=={str(p.relative_to(short_images)):sha(p) for p in short_images.rglob('*') if p.is_file()}
            report['runs'].append({'sample_index':index,'sample_id':prereg['records'][index]['sample_id'],
                'result':path.relative_to(ROOT).as_posix(),'result_sha256':sha(path),
                'packet_result_sha256':sha(packet),'staged_images':str(short_images),'staged_files_sha256':files,
                'metrics':[r['metrics'] for r in data['layers']]})
            report['tasks']+=12;save(report_path,report)
            print('PASS SoC sample',index,'tasks',report['tasks'],'mean_cycles',data['mean_cpu_setup_to_ack_cycles'],flush=True)
        assert report['tasks']==3072 and sha(Path(__file__))==identity['script_sha256']
        export_result=json.loads((EXPORT/'result.json').read_text());assert export_result['passed'] and export_result['tasks']==3072
        metrics=[m for row in report['runs'] for m in row['metrics']]
        cycles=[m['cpu_setup_to_ack'] for m in metrics]
        report.update(passed=True,phase='complete',packet_result_sha256=sha(EXPORT/'result.json'),
            output_elements=3072*25344,min_cpu_setup_cycles=min(cycles),max_cpu_setup_cycles=max(cycles),
            mean_cpu_setup_cycles=sum(cycles)/3072,
            mean_serialized_ideal_loader_plus_cpu_cycles=sum(m['reads']+m['cpu_setup_to_ack'] for m in metrics)/3072)
        save(report_path,report);print('PASS '+str(report_path),flush=True)
    except Exception as error:
        report.update(passed=False,phase='failed',error=str(error));save(report_path,report);raise

if __name__=='__main__':main()
