"""Frozen-training Q12 parameters and real 32-bit packets; local private data only."""
from pathlib import Path
from datetime import datetime, timezone
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
import sys,json,hashlib,struct,zipfile,shutil
import numpy as np
from rice_words import encode,decode,exact_lengths
from packet_io import parse_input,parse_output,build_output,FORMAT_VERSION
HERE=Path(__file__).resolve().parent;CAND=HERE.parent;WORK=CAND.parents[2]
sys.path.insert(0,str(CAND/'reference'))
from fixed_reference import direct,pair_identity
sys.path.insert(0,str(WORK/'output/github-qiansaisheji/qingyu/model'))
import study_precision_bandwidth as numeric
PROBE=WORK/'output/eda/int8_precision_probe/score95_20261112_215852'
CONFIG=PROBE/'x12_w12_y13_h1'
DATA=WORK/'qingyu/model/full_v2_run'
SAMPLES=[0,9,31,127,198,255]
OUT=CAND/'fixtures'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def stream(v,width,k,delta):
    b,n=encode(v,width,k,delta)
    assert n==int(exact_lengths(v,width,k,delta)[0])
    assert np.array_equal(decode(b,n,v.shape,width,k,delta),v)
    return b,n
def main():
    OUT.mkdir(exist_ok=True);freeze=OUT/'frozen';freeze.mkdir(exist_ok=True)
    expected=json.loads((PROBE/'frozen_config_sha256.json').read_text())
    configs={}
    for layer in range(12):
        p=CONFIG/f'layer{layer:02d}.json'
        assert sha(p)==expected[f'x12_w12_y13_h1/{p.name}']
        cfg=json.loads(p.read_text())
        assert (cfg['input_bits'],cfg['weight_bits'],cfg['output_bits'],cfg['headroom_bits'],cfg['fit_role'])==(12,12,13,1,'training')
        if (freeze/p.name).exists():assert sha(freeze/p.name)==sha(p)
        else:shutil.copyfile(p,freeze/p.name)
        configs[p.name]=sha(p)
    dump(freeze/'frozen_config_sha256.json',configs)
    plan={'format_version':FORMAT_VERSION,'scope':'historical local private data; not official600, not RTL/PPA',
          'configuration_fit':'original training256 only; no parameter refit here',
          'architecture_selection':'exploratory width selection using prior historical validation; not a fresh held-out official score',
          'frozen_prior_to_this_validation_read':datetime.now(timezone.utc).isoformat(),
          'config_hashes':configs,'precision_study_sha256':sha(PROBE/'result.json'),
          'selected_samples':SAMPLES,'codec':{'X':{'width':12,'k':6,'delta_stride':64},'W':{'width':12,'k':9,'delta':False},'Y':{'width':13,'k':7,'delta_stride':16}},
          'metadata':{'header_words':330,'bias_signed_bits':22,'bias_encoding':'256 signextended32 words','shifts':'256 bytes in64words'},
          'wire_bounds':{'input_words':8873,'x_max_bits':76230,'weight_group_max_bits':24640,'output_slot_words':646,'output_allocation_words':10353,'output_write_words_max':10354},
          'magic_unchanged':{'input':0x31513151,'output':0x31593151},
          'scripts':{str(p.relative_to(CAND)):sha(p)for p in[Path(__file__),HERE/'rice_words.py',HERE/'packet_io.py',CAND/'reference/fixed_reference.py']}}
    dump(OUT/'plan.json',plan)
    rows=[];data_hashes={};checks=0;bias_min=0;bias_max=0
    archive=OUT/'q12_fixtures72.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED)as z:
        for layer in range(12):
            source=DATA/'float_validation'/f'layer{layer:02d}.npz';data_hashes[str(source)]=sha(source)
            d=numeric.load(source,'validation');cfg=json.loads((freeze/f'layer{layer:02d}.json').read_text())
            w,wclip=numeric.quantize(d['W'],np.exp2(cfg['w_exponents']),12);assert wclip==0
            assert numeric.weight_digest(d['W'],d['b'])==cfg['weights_sha256']
            bias=np.rint(d['b'].astype(np.float64)/np.exp2(np.asarray(cfg['w_exponents'])+cfg['x_exponent'])).astype(np.int64)
            assert np.all((bias>=-(1<<21))&(bias<(1<<21)))
            bias_min=min(bias_min,int(bias.min()));bias_max=max(bias_max,int(bias.max()))
            shifts=np.asarray(cfg['shifts'],dtype=np.int64)
            weights=[stream(w[:,g*32:g*32+32],12,9,False)for g in range(8)]
            for sample in SAMPLES:
                x,xclip=numeric.quantize(d['X'][sample],2.**cfg['x_exponent'],12);assert xclip==0
                y=direct(x,w,bias,shifts)
                scalar=int(bias[17])+sum(int(x[98,k])*int(w[k,17])for k in range(64))
                assert scalar==int((x@w+bias)[98,17])
                pair_identity(x,w,bias)
                xp,xbits=stream(x,12,6,True)
                outputs=[stream(y[:,t*16:t*16+16],13,7,True)for t in range(16)]
                header=[0x31513151,xbits,*[n for b,n in weights],*[int(v)&0xffffffff for v in bias],
                        *[sum(int(shifts[j+k])<<(8*k)for k in range(4))for j in range(0,256,4)]]
                assert len(header)==330
                ip=struct.pack('<330I',*header)+xp+b''.join(b for b,n in weights)
                op=build_output([b for b,n in outputs],[n for b,n in outputs])
                px,pw,pb,ps=parse_input(ip)
                assert all(np.array_equal(a,b)for a,b in[(px,x),(pw,w),(pb,bias),(ps,shifts),(parse_output(op),y)])
                assert np.array_equal(direct(px,pw,pb,ps),parse_output(op))
                task=f'layer{layer:02d}/sample{sample:03d}'
                blobs={'input.bin':ip,'expected_output.bin':op,'expected_dense16.bin':y.astype('<i2').tobytes()}
                for name,blob in blobs.items():z.writestr(task+'/'+name,blob)
                rows.append({'task':task,'input_words':len(ip)//4,'output_allocation_words':len(op)//4,
                             'output_actual_write_words':18+sum(len(b)//4 for b,n in outputs),
                             'input_sha256':hashlib.sha256(ip).hexdigest(),'output_sha256':hashlib.sha256(op).hexdigest(),
                             'dense_sha256':hashlib.sha256(blobs['expected_dense16.bin']).hexdigest(),
                             'x_bits':xbits,'weight_bits':[n for b,n in weights],'output_bits':[n for b,n in outputs]})
                checks+=25
            print('Q12_FIXTURE_LAYER',layer,flush=True)
        z.writestr('manifest.json',json.dumps({'format_version':FORMAT_VERSION,'status':'software packet roundtrip + independent direct MAC/RNE, not RTL','plan_sha256':sha(OUT/'plan.json'),'tasks':rows},indent=2))
    result={'completed':True,'tasks':len(rows),'roundtrip_stream_checks':checks,'independent_dense_values':len(rows)*25344,
            'fixtures_zip_sha256':sha(archive),'plan_sha256':sha(OUT/'plan.json'),'config_hashes':configs,
            'data_sha256':data_hashes,'bias_min':bias_min,'bias_max':bias_max,'reference_pair_identity_checked':True,
            'layer00_input_words':rows[0]['input_words'],'layer00_output_write_words':rows[0]['output_actual_write_words'],
            'bounds':plan['wire_bounds'],'scope':plan['scope']}
    for n,h in configs.items():assert sha(freeze/n)==h
    dump(OUT/'result.json',result);print('Q12_FIXTURES_READY',archive,sha(archive),flush=True)
if __name__=='__main__':main()
