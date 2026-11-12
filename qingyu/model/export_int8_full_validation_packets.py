"""Export every frozen validation record, with resumable verified packet artifacts.

This is the existing 256-record validation population, not the official600 set.
Neither numeric settings nor compression codebooks are fitted here.
"""
from pathlib import Path
import hashlib, json, os, subprocess, sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,data):
    temporary=path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(data,indent=2)+'\n');temporary.replace(path)
def verify(path,index):
    data=json.loads(path.read_text())
    assert data['passed'] and data['sample_index']==index and len(data['layers'])==12
    for row in data['layers']:
        layer=path.parent/f'layer{row["layer"]:02d}'
        manifest=json.loads((layer/'manifest.json').read_text())
        assert row==manifest
        for name,digest in manifest['files_sha256'].items():
            assert sha(layer/name)==digest
    return data

def main():
    out=ROOT/'build/int8_full_validation_packets_20261112';out.mkdir(exist_ok=True)
    metadata_path=ROOT/'build/model_reference_20261111_201956_613/float_validation/extraction_manifest.json'
    metadata=json.loads(metadata_path.read_text());assert len(metadata['sample_ids'])==256
    exporter=ROOT/'model/export_int8_packets.py'
    diagnostic_path=ROOT/'build/int8_packet_corpus_20261112/result.json'
    diagnostic=json.loads(diagnostic_path.read_text());assert diagnostic['passed']
    existing={row['sample_index']:row for row in diagnostic['results']}
    identity={'schema':'qingyu-full-frozen-validation-packets-v1',
              'script_sha256':sha(Path(__file__)),'exporter_sha256':sha(exporter),
              'metadata_sha256':sha(metadata_path),'diagnostic_manifest_sha256':sha(diagnostic_path),
              'selection_rule':'All indices0..255 in original frozen validation order; no exclusions or timing-based selection.',
              'records':[{'sample_index':i,'sample_id':v} for i,v in enumerate(metadata['sample_ids'])],
              'scope':'Frozen 256 validation records x12 task layers; no new fitting, no official600 claim, no unbiased larger-population claim.'}
    prereg=out/'preregistration.json'
    if prereg.exists(): assert json.loads(prereg.read_text())==identity,'Resume identity changed'
    else: save(prereg,identity)
    result_path=out/'result.json'
    report=json.loads(result_path.read_text()) if result_path.exists() else {'passed':False,'tasks':0,'results':[],'attempts':[]}
    assert len({r['sample_index'] for r in report['results']})==len(report['results'])
    completed={r['sample_index']:r for r in report['results']}
    report.update(preregistration_sha256=sha(prereg),scope=identity['scope'])
    env=dict(os.environ,OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
    print(out,flush=True)
    for i in range(256):
        if i in completed:
            item=completed[i];path=(ROOT/item['path'].replace('\\','/')).resolve()
            assert path.is_relative_to(ROOT) and sha(path)==item['sha256'];verify(path,i);continue
        if i in existing:
            item=existing[i];path=(ROOT/item['path'].replace('\\','/')).resolve()
            assert path.is_relative_to(ROOT) and sha(path)==item['sha256']
            reused=True
        else:
            timestamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            target=out/f'sample{i:03d}_{timestamp}'
            log=out/f'sample{i:03d}_{timestamp}.log'
            command=[sys.executable,str(exporter),'--output',str(target),'--sample',str(i)]
            with log.open('w') as stream:
                run=subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=600)
            report['attempts'].append({'sample_index':i,'returncode':run.returncode,'log':log.name,'log_sha256':sha(log)})
            save(result_path,report)
            if run.returncode: raise RuntimeError('Export failed; saved '+str(log))
            path=target/'result.json';reused=False
        data=verify(path,i)
        assert sha(exporter)==identity['exporter_sha256']
        item={'sample_index':i,'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),
              'tasks':12,'reused_diagnostic':reused,'input_words':[r['input_words'] for r in data['layers']],
              'output_write_transactions':[r['output_written_words']+1 for r in data['layers']]}
        report['results'].append(item);completed[i]=item;report['tasks']+=12;save(result_path,report)
        print('PASS packet sample',i,'tasks',report['tasks'],flush=True)
    assert report['tasks']==3072 and set(completed)==set(range(256))
    assert sha(exporter)==identity['exporter_sha256'] and sha(Path(__file__))==identity['script_sha256']
    report['passed']=True;save(result_path,report);print('PASS '+str(result_path),flush=True)

if __name__=='__main__':main()
