"""Training-frozen precision candidates and independent full-layer evaluation.

This experiment does not change production formats, RTL, or benchmark timing.
All candidate policies are declared before loading validation data. Width
selection is exploratory model selection, not an official test-set result.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from reference import weight_digest

POLICIES = [(16,16,16,1), (12,12,12,0), (10,10,12,0), (8,8,12,0),
            (8,8,8,0), (6,6,8,0), (8,4,8,0), (4,4,8,0)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tag(policy):
    x,w,y,h=policy
    return f'x{x}_w{w}_y{y}_h{h}'


def load(path, role):
    with np.load(path,allow_pickle=False) as archive:
        data={key:archive[key] for key in archive.files}
    if str(data['split'].item())!=role:
        raise ValueError('Incorrect dataset role')
    if data['X'].shape[1:]!=(99,64) or data['W'].shape!=(64,256):
        raise ValueError('Wrong complete-task dimensions')
    if set(data['labels'].tolist())!=set(range(12)):
        raise ValueError('All twelve labels required')
    for key in ['X','W','b','Y']:
        if not np.all(np.isfinite(data[key])):raise ValueError('Nonfinite '+key)
    return data


def exponent(maximum,bits):
    limit=(1<<(bits-1))-1
    if maximum==0:return 0
    value=int(math.ceil(math.log2(float(maximum)/limit)))
    while float(maximum)/math.ldexp(1.0,value)>limit:value+=1
    return value


def quantize(value,scale,bits):
    limit=(1<<(bits-1))-1
    rounded=np.rint(np.asarray(value,dtype=np.float64)/scale)
    clipped=int(np.count_nonzero(np.abs(rounded)>limit))
    return np.clip(rounded,-limit,limit).astype(np.int64),clipped


def exact_accumulation(x,w,b,xb):
    # All products and every possible partial sum are integers < 2**47.
    # IEEE binary64 therefore computes this integer matmul exactly, including
    # arbitrary BLAS reduction order. This is a model acceleration only.
    bound=np.abs(b)+((1<<(xb-1))-1)*np.sum(np.abs(w),axis=0)
    if np.any(bound>=(1<<47)):raise OverflowError('Signed48 bound exceeded')
    a=x.astype(np.float64)@w.astype(np.float64)+b.astype(np.float64)
    if np.any(a!=np.rint(a)):raise AssertionError('Nonintegral dot product')
    result=a.astype(np.int64)
    flat_x=x.reshape(-1,64);flat_a=result.reshape(-1,256)
    rng=np.random.default_rng(77201)
    for _ in range(32):
        i=int(rng.integers(len(flat_x)));j=int(rng.integers(256))
        scalar=int(b[j])+sum(int(flat_x[i,k])*int(w[k,j]) for k in range(64))
        if scalar!=int(flat_a[i,j]):raise AssertionError('Scalar integer cross-check')
    return result,int(np.max(bound))


def rounded(values,shift):
    if shift==0:return values.copy()
    magnitude=np.abs(values);quotient=magnitude>>shift
    remainder=magnitude&((1<<shift)-1);half=1<<(shift-1)
    increment=(remainder>half)|((remainder==half)&((quotient&1)!=0))
    out=quotient+increment.astype(np.int64)
    return np.where(values<0,-out,out)


def shifts_for(a,bits,headroom):
    lower=-(1<<(bits-1));upper=(1<<(bits-1))-1
    columns=a.reshape(-1,256)
    extremes=np.stack([np.min(columns,axis=0),np.max(columns,axis=0)])
    shifts=[]
    for j in range(256):
        for s in range(48):
            r=rounded(extremes[:,j],s)
            if np.all((r>=lower)&(r<=upper)):
                if s+headroom>47:raise OverflowError('Unsupported shift')
                shifts.append(s+headroom);break
        else:raise OverflowError('No output shift')
    return shifts


def evaluate(a,reference,config):
    bits=config['output_bits'];lower=-(1<<(bits-1));upper=(1<<(bits-1))-1
    error_sum=0.;reference_sum=0.;saturation=0
    for j,s in enumerate(config['shifts']):
        value=rounded(a[...,j],s)
        saturation+=int(np.count_nonzero((value<lower)|(value>upper)))
        value=np.clip(value,lower,upper)
        scale=math.ldexp(1.0,config['x_exponent']+config['w_exponents'][j]+s)
        ref=reference[...,j].astype(np.float64)
        error_sum+=float(np.sum((value.astype(np.float64)*scale-ref)**2))
        reference_sum+=float(np.sum(ref**2))
    nrmse=math.sqrt(error_sum/reference.size)/max(math.sqrt(reference_sum/reference.size),1e-8)
    return dict(elements=int(reference.size),nrmse_percent=nrmse*100,
                output_saturation=saturation,error_squared_sum=error_sum,
                reference_squared_sum=reference_sum)


def encode(data,config):
    x,clips=quantize(data['X'],math.ldexp(1.,config['x_exponent']),config['input_bits'])
    sw=np.exp2(np.asarray(config['w_exponents'],dtype=np.float64))
    w,_=quantize(data['W'],sw,config['weight_bits'])
    b_float=np.rint(np.asarray(data['b'],dtype=np.float64)/(math.ldexp(1.,config['x_exponent'])*sw))
    if np.any(np.abs(b_float)>=(1<<47)):raise OverflowError('Bias exceeds signed48')
    a,bound=exact_accumulation(x,w,b_float.astype(np.int64),config['input_bits'])
    return a,clips,bound


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output
    out.mkdir(parents=True,exist_ok=False)
    report={'schema':'qingyu-precision-bandwidth-study-v1',
            'created_utc':datetime.now(timezone.utc).isoformat(),
            'script_sha256':sha(Path(__file__)),'official_600_sample_evaluation':False,
            'validation_parameter_fit':False,'selection_scope':'exploratory architecture study',
            'limits':['No RTL implementation or PPA inferred','Packed-bit bandwidth is an ideal lower bound',
                      'Source initialization and complete-task timing require a separately specified loader'],
            'policies':{},'inputs':[]}
    for policy in POLICIES:
        x,w,y,h=policy
        input_words=math.ceil(99*64*x/32)+math.ceil(64*256*w/32)+576
        output_words=math.ceil(99*256*y/32)
        report['policies'][tag(policy)]={'input_bits':x,'weight_bits':w,'output_bits':y,'headroom_bits':h,
            'training':[],'validation':[],
            'ideal_packed_words':{'input_with_legacy_metadata':input_words,'output':output_words,
                'initial_write_plus_output':input_words+output_words,
                'initial_write_private_read_output':2*input_words+output_words}}
    (out/'declared_policies.json').write_text(json.dumps(report,indent=2)+'\n')
    train_ids=None;source_commit=None
    # Freeze every layer and every candidate before reading validation arrays.
    for layer in range(12):
        path=args.reference_run/'float_training'/f'layer{layer:02d}.npz'
        data=load(path,'training');ids=set(map(str,data['sample_ids'].tolist()))
        commit=str(data['source_commit'].item())
        if train_ids is not None and (ids!=train_ids or commit!=source_commit):raise ValueError('Training provenance differs')
        train_ids=ids;source_commit=commit
        report['inputs'].append({'role':'training','layer':layer,'sha256':sha(path)})
        cache={}
        for policy in POLICIES:
            x,w,y,h=policy
            config={'layer':layer,'input_bits':x,'weight_bits':w,'output_bits':y,'headroom_bits':h,
                    'x_exponent':exponent(np.max(np.abs(data['X'])),x),
                    'w_exponents':[exponent(v,w) for v in np.max(np.abs(data['W']),axis=0)],
                    'weights_sha256':weight_digest(data['W'],data['b']),'fit_role':'training'}
            if (x,w) not in cache:cache[x,w]=encode(data,config)
            a,clips,bound=cache[x,w];config['shifts']=shifts_for(a,y,h)
            directory=out/tag(policy);directory.mkdir(exist_ok=True)
            (directory/f'layer{layer:02d}.json').write_text(json.dumps(config,indent=2)+'\n')
            metric=evaluate(a,data['Y'],config);metric.update(layer=layer,input_clipping=clips,accumulator_bound=bound)
            report['policies'][tag(policy)]['training'].append(metric)
        print('Frozen training layer',layer,flush=True)
    frozen={p.relative_to(out).as_posix():sha(p) for p in out.glob('*/layer*.json')}
    (out/'frozen_config_sha256.json').write_text(json.dumps(frozen,indent=2)+'\n')
    val_ids=None
    for layer in range(12):
        path=args.reference_run/'float_validation'/f'layer{layer:02d}.npz'
        data=load(path,'validation');ids=set(map(str,data['sample_ids'].tolist()))
        if ids&train_ids or (val_ids is not None and ids!=val_ids):raise ValueError('Validation identity overlap/change')
        if str(data['source_commit'].item())!=source_commit:raise ValueError('Model commit differs')
        val_ids=ids;report['inputs'].append({'role':'validation','layer':layer,'sha256':sha(path)})
        cache={}
        for policy in POLICIES:
            x,w,y,h=policy;config=json.loads((out/tag(policy)/f'layer{layer:02d}.json').read_text())
            if weight_digest(data['W'],data['b'])!=config['weights_sha256']:raise ValueError('Weights changed')
            if (x,w) not in cache:cache[x,w]=encode(data,config)
            a,clips,bound=cache[x,w]
            metric=evaluate(a,data['Y'],config);metric.update(layer=layer,input_clipping=clips,accumulator_bound=bound)
            report['policies'][tag(policy)]['validation'].append(metric)
        (out/'partial_result.json').write_text(json.dumps(report,indent=2)+'\n')
        print('Evaluated independent validation layer',layer,flush=True)
    if frozen!={p.relative_to(out).as_posix():sha(p) for p in out.glob('*/layer*.json')}:raise ValueError('Frozen configuration changed')
    report.update(training_samples=len(train_ids),validation_samples=len(val_ids),source_commit=source_commit,
                  training_sample_ids=sorted(train_ids),validation_sample_ids=sorted(val_ids),sample_sets_disjoint=True)
    for name,policy in report['policies'].items():
        policy['max_validation_nrmse_percent']=max(r['nrmse_percent'] for r in policy['validation'])
        policy['meets_local_3_percent_threshold']=policy['max_validation_nrmse_percent']<=3
        print(name,'max NRMSE %',policy['max_validation_nrmse_percent'],flush=True)
    report['completed']=True
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
