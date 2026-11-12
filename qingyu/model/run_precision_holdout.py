"""Audit frozen INT8 on an additional, prespecified validation partition slice.

This is local robustness evidence, not the organizer's frozen 600 evaluation.
No numerical or codec parameter is fitted or modified.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys

os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('TF_NUM_INTRAOP_THREADS','2')
os.environ.setdefault('TF_NUM_INTEROP_THREADS','2')
import numpy as np
from check_precision_tasks import sha, summarize, task_metrics
import study_precision_bandwidth as study
from reference import weight_digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True,exist_ok=False)
    out=args.output.resolve()
    original=root/'build/precision_bandwidth_20261111'
    configs=json.loads((original/'frozen_config_sha256.json').read_text())
    previous=json.loads((original/'result.json').read_text())
    policy='x8_w8_y8_h0'
    declaration={'schema':'qingyu-additional-precision-holdout-v1',
      'created_utc':datetime.now(timezone.utc).isoformat(),'script_sha256':sha(Path(__file__)),
      'policy':policy,'partition':'validation','offset':256,'count':512,'layers':list(range(12)),
      'parameters_refit':False,'official_600_sample_evaluation':False,
      'previous_study_sha256':sha(original/'result.json'),'config_manifest_sha256':sha(original/'frozen_config_sha256.json'),
      'frozen_config_sha256':{k:v for k,v in configs.items() if k.startswith(policy+'/')},
      'limits':['Additional local validation utterances, not organizer-selected holdout',
                'Generated silence entries are explicitly recorded by the original loader',
                'No RTL, PPA, classification accuracy or official score inferred']}
    for name,digest in declaration['frozen_config_sha256'].items():
        assert sha(original/name)==digest
    plan=out/'preregistration.json';plan.write_text(json.dumps(declaration,indent=2)+'\n')
    plan_hash=sha(plan)
    status={'state':'running','stages':[],'preregistration_sha256':plan_hash}
    def save_status():
        status['checked_utc']=datetime.now(timezone.utc).isoformat()
        (out/'pipeline_status.json').write_text(json.dumps(status,indent=2)+'\n')
    scripts=root/'model'
    repo=root/'vendor/keyword-transformer'
    stages=[('prepare',['prepare_official_audio.py','--repo',str(repo),'--data-dir','D:/QingyuModelData',
                        '--split','validation','--offset','256','--count','512','--output',str(out/'audio.npz')]),
            ('extract',['extract_kwt1.py','--repo',str(repo),'--audio-npz',str(out/'audio.npz'),
                        '--split','validation','--output',str(out/'float_validation')])]
    for name,command in stages:
        status['current_stage']=name;save_status()
        print(name,'RUNNING',flush=True)
        with (out/(name+'.log')).open('w',encoding='utf-8') as log:
            proc=subprocess.run([sys.executable,'-X','utf8',str(scripts/command[0]),*command[1:]],stdout=log,stderr=subprocess.STDOUT)
        status['stages'].append({'name':name,'returncode':proc.returncode,'log':name+'.log'})
        if proc.returncode:
            status['state']='failed';save_status();raise SystemExit(f'{name} failed; see {out}')
        save_status()
    audio_manifest=json.loads((out/'audio.manifest.json').read_text())
    assert audio_manifest['count']==512 and audio_manifest['offset']==256
    new_ids={x['sample_id'] for x in audio_manifest['samples']}
    assert len(new_ids)==512
    old_ids=set(previous['training_sample_ids'])|set(previous['validation_sample_ids'])
    assert not new_ids & old_ids
    status['current_stage']='frozen_precision_audit';save_status()
    report={'passed':False,'acceptance_passed':False,'preregistration_sha256':plan_hash,
      'official_600_sample_evaluation':False,'parameters_refit':False,'policy':policy,
      'input_sha256':{},'config_sha256':declaration['frozen_config_sha256'],'tasks':[],
      'additional_utterances':512,'disjoint_from_prior_training_and_validation_ids':True,
      'audio_manifest_sha256':sha(out/'audio.manifest.json'),'limits':declaration['limits']}
    for layer in range(12):
        source=out/'float_validation'/f'layer{layer:02d}.npz'
        report['input_sha256'][source.name]=sha(source)
        data=study.load(source,'validation')
        assert set(map(str,data['sample_ids']))==new_ids
        cp=original/policy/f'layer{layer:02d}.json'
        assert sha(cp)==declaration['frozen_config_sha256'][policy+'/'+cp.name]
        config=json.loads(cp.read_text())
        assert weight_digest(data['W'],data['b'])==config['weights_sha256']
        assert str(data['source_commit'].item())==previous['source_commit']
        accum,clips,bound=study.encode(data,config)
        limit=(1<<(config['input_bits']-1))-1
        rounded=np.rint(data['X'].astype(np.float64)/math.ldexp(1.,config['x_exponent']))
        per_clips=np.count_nonzero(np.abs(rounded)>limit,axis=(1,2))
        assert int(per_clips.sum())==clips
        report['tasks'].extend(task_metrics(accum,data,config,per_clips))
        print('AUDIT',layer,'PASS',flush=True)
        (out/'partial_result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert sha(plan)==plan_hash
    report['summary']=summarize(report['tasks'])
    report['passed']=True
    report['meaning_of_passed']='Frozen-source/config and per-task audit completed; see numerical threshold in summary'
    result=out/'result.json';result.write_text(json.dumps(report,indent=2)+'\n')
    status.update(state='complete',result_sha256=sha(result),summary=report['summary']);save_status()
    print(json.dumps(report['summary'],indent=2),flush=True)
    print(result,flush=True)


if __name__=='__main__':main()
