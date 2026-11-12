"""Audit a prespecified identity-filtered slice with frozen numerical settings."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
os.environ.setdefault('OMP_NUM_THREADS','2')
import numpy as np
from check_precision_tasks import sha, summarize, task_metrics
import study_precision_bandwidth as study
from reference import weight_digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1]
    base=root/'build/precision_bandwidth_20261111'
    old=json.loads((base/'result.json').read_text())
    frozen=json.loads((base/'frozen_config_sha256.json').read_text())
    audio=json.loads((args.source/'audio.manifest.json').read_text())
    old_ids=set(old['training_sample_ids'])|set(old['validation_sample_ids'])
    # Selection uses identities only. No new tensor/error has been opened.
    keep=[i for i,x in enumerate(audio['samples']) if x['sample_id'] not in old_ids]
    ids={audio['samples'][i]['sample_id'] for i in keep}
    assert len(ids)==len(keep)>0 and not ids&old_ids
    policy='x8_w8_y8_h0'
    hashes={k:v for k,v in frozen.items() if k.startswith(policy+'/')}
    for key,value in hashes.items():assert sha(base/key)==value
    registration={'schema':'qingyu-identity-filtered-holdout-v1','created_utc':datetime.now(timezone.utc).isoformat(),
      'script_sha256':sha(Path(__file__)),'source_audio_manifest_sha256':sha(args.source/'audio.manifest.json'),
      'original_study_sha256':sha(base/'result.json'),'selection_rule':'Exclude every original training or validation sample ID, before opening new tensors or errors; preserve source order',
      'source_samples':len(audio['samples']),'excluded_previously_used':len(audio['samples'])-len(keep),
      'kept_source_indices':keep,'sample_ids':sorted(ids),'policy':policy,'frozen_config_sha256':hashes,
      'parameters_refit':False,'official_600_sample_evaluation':False}
    plan=args.output/'preregistration.json';plan.write_text(json.dumps(registration,indent=2)+'\n')
    plan_hash=sha(plan)
    report={'passed':False,'acceptance_passed':False,'official_600_sample_evaluation':False,
      'preregistration_sha256':plan_hash,'parameters_refit':False,'input_sha256':{},'tasks':[],
      'additional_utterances':len(keep),'excluded_prior_samples':len(audio['samples'])-len(keep),
      'limits':['Local robustness sample, not organizer-selected evaluation',
                'Generated silence entries are loader records and not independent acoustic content',
                'No PPA, RTL, classification accuracy or official score inferred']}
    for layer in range(12):
        path=args.source/'float_validation'/f'layer{layer:02d}.npz'
        report['input_sha256'][path.name]=sha(path)
        data=study.load(path,'validation')
        assert list(map(str,data['sample_ids']))==[x['sample_id'] for x in audio['samples']]
        for name in ['X','Y','labels','sample_ids']:data[name]=data[name][keep]
        assert set(map(str,data['sample_ids']))==ids
        config_path=base/policy/f'layer{layer:02d}.json'
        assert sha(config_path)==hashes[policy+'/'+config_path.name]
        config=json.loads(config_path.read_text())
        assert weight_digest(data['W'],data['b'])==config['weights_sha256']
        assert str(data['source_commit'].item())==old['source_commit']
        acc,clips,bound=study.encode(data,config)
        limit=(1<<(config['input_bits']-1))-1
        quant=np.rint(data['X'].astype(np.float64)/math.ldexp(1.,config['x_exponent']))
        per_clips=np.count_nonzero(np.abs(quant)>limit,axis=(1,2))
        assert int(per_clips.sum())==clips
        report['tasks'].extend(task_metrics(acc,data,config,per_clips))
        print('AUDIT',layer,'COMPLETE',flush=True)
        (args.output/'partial_result.json').write_text(json.dumps(report,indent=2)+'\n')
    assert sha(plan)==plan_hash
    report.update(passed=True,summary=summarize(report['tasks']),
                  meaning_of_passed='Identity and frozen configuration audit completed; numerical acceptance is stated separately in summary')
    (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['summary'],indent=2),flush=True)
    print(args.output/'result.json',flush=True)


if __name__=='__main__':main()
