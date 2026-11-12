"""Preregistered adaptive Rice32 lossless study, including actual bitstreams.

No RTL, numeric refit, validation-fitted predictor, or full-task speed claim.
Every task's tiled X/W/Y bytes are encoded, decoded and reconstructed, with
all input/output headers, initial marker invalidation and stream padding.
"""
from __future__ import annotations
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from analyze_lossless_command_budget import numeric, quantized, sha


CPP = r'''
#include <cstdint>
#include <vector>
#include <algorithm>
#include <stdexcept>
#include <cstring>
struct Writer {
 std::vector<uint8_t> data; uint64_t size=0;
 void put(uint32_t value,unsigned width){for(int b=int(width)-1;b>=0;--b){
  if(!(size&7))data.push_back(0);data.back()|=((value>>b)&1)<<(7-(size&7));++size;}}
};
struct Reader {
 const uint8_t* data;uint64_t size,pos=0;
 uint32_t get(unsigned width){uint32_t value=0;for(unsigned b=0;b<width;++b){
  if(pos>=size)throw std::runtime_error("truncated");
  value=(value<<1)|((data[pos/8]>>(7-(pos&7)))&1);++pos;}return value;}
};
static unsigned zig(uint8_t b){int s=b<128?int(b):int(b)-256;return s<0?unsigned(-2*s-1):unsigned(2*s);}
static uint8_t unzig(unsigned u){if(u>255)throw std::runtime_error("range");return uint8_t((u&1)?-int((u+1)/2):int(u/2));}
static unsigned cost(const uint8_t* p,unsigned n,unsigned k){unsigned v=n*(1+k);for(unsigned i=0;i<n;++i)v+=zig(p[i])>>k;return v;}
static unsigned best_k(const uint8_t* p,unsigned n){unsigned kbest=0,vbest=cost(p,n,0);for(unsigned k=1;k<8;++k){unsigned v=cost(p,n,k);if(v<vbest){kbest=k;vbest=v;}}return kbest;}
extern "C" int64_t decode(const uint8_t* wire,uint64_t bits,uint64_t count,int adaptive,unsigned fixed_k,uint8_t* out){
 try{
  if(!count||fixed_k>7)throw std::runtime_error("config");
  Reader reader{wire,bits};
  for(uint64_t base=0;base<count;base+=32){unsigned n=unsigned(std::min(uint64_t(32),count-base));
   bool raw=reader.get(1);unsigned k=(!raw&&adaptive)?reader.get(3):fixed_k;
   for(unsigned i=0;i<n;++i){
    if(raw)out[base+i]=reader.get(8);
    else {unsigned q=0;while(reader.get(1)){if(++q>(255u>>k))throw std::runtime_error("unary");}
      out[base+i]=unzig((q<<k)|reader.get(k));}
   }
   unsigned chosen=adaptive?best_k(out+base,n):fixed_k;
   bool expected_raw=cost(out+base,n,chosen)+(adaptive?3:0)>=8*n;
   if(raw!=expected_raw||(!raw&&k!=chosen))throw std::runtime_error("noncanonical");
  }
  if(reader.pos!=bits)throw std::runtime_error("trailing");
  if(bits%8 && (wire[bits/8]&((1u<<(8-bits%8))-1)))throw std::runtime_error("padding");
  return bits;
 }catch(...){return -1;}
}
extern "C" int64_t roundtrip(const uint8_t* src,uint64_t count,int adaptive,unsigned fixed_k,uint8_t* out,uint8_t* wire,uint64_t* stats){
 try{
  if(!count||fixed_k>7)throw std::runtime_error("config");
  Writer writer;std::fill(stats,stats+12,0);
  for(uint64_t base=0;base<count;base+=32){unsigned n=unsigned(std::min(uint64_t(32),count-base));
   unsigned k=adaptive?best_k(src+base,n):fixed_k;
   bool raw=cost(src+base,n,k)+(adaptive?3:0)>=8*n;
   writer.put(raw,1);++stats[0];++stats[raw?2:3];
   if(!raw&&adaptive){writer.put(k,3);stats[1]+=3;}
   if(!raw)++stats[4+k];
   for(unsigned i=0;i<n;++i){unsigned u=zig(src[base+i]);
    if(raw)writer.put(src[base+i],8);
    else {for(unsigned q=u>>k;q;--q)writer.put(1,1);writer.put(0,1);writer.put(u&((1u<<k)-1),k);}
   }
  }
  std::memcpy(wire,writer.data.data(),writer.data.size());
  if(decode(writer.data.data(),writer.size,count,adaptive,fixed_k,out)!=int64_t(writer.size))throw std::runtime_error("decode");
  if(std::memcmp(src,out,count))throw std::runtime_error("roundtrip");
  return writer.size;
 }catch(...){return -1;}
}
'''

FAMILIES = {
    'global_rice32': dict(adaptive=False, predictor='row'),
    'adaptive_rice32': dict(adaptive=True, predictor='row'),
    'adaptive_rice32_gradient': dict(adaptive=True, predictor='gradient'),
}
K = {'x': 2, 'w': 5, 'y': 3}


def transform(frame, predictor):
    value=np.asarray(frame,dtype=np.int16)
    residual=value.copy()
    if predictor!='none':
        residual[1:]=value[1:]-value[:-1]
        if predictor=='gradient':
            residual[1:,1:]-=value[1:,:-1]-value[:-1,:-1]
    return np.ascontiguousarray((residual&255).astype(np.uint8))


def inverse(residual, predictor):
    if predictor=='none':return residual.copy()
    delta=residual.astype(np.int64)
    if predictor=='gradient':delta[1:]=np.cumsum(delta[1:],axis=1)
    return (np.cumsum(delta,axis=0)&255).astype(np.uint8)


def independent_cost(data, adaptive, k):
    s=data.ravel().astype(np.int16);s[s>=128]-=256
    u=np.where(s<0,-2*s-1,2*s).astype(np.uint16)
    length=len(u);padding=(-length)%32
    blocks=np.pad(u,(0,padding)).reshape(-1,32)
    counts=np.full(len(blocks),32,dtype=np.int64);counts[-1]-=padding
    if adaptive:
        candidates=np.stack([(blocks>>j).sum(axis=1)+counts*(1+j) for j in range(8)])
        selection=np.argmin(candidates,axis=0)
        costs=np.min(candidates,axis=0)+3
    else:
        selection=np.full(len(blocks),k,dtype=np.int64)
        costs=(blocks>>k).sum(axis=1)+counts*(1+k)
    raw=costs>=8*counts
    bits=int((1+np.minimum(costs,8*counts)).sum())
    stats=np.zeros(12,dtype=np.uint64)
    stats[0]=len(blocks);stats[1]=int(np.count_nonzero(~raw))*3 if adaptive else 0
    stats[2]=int(np.count_nonzero(raw));stats[3]=len(raw)-stats[2]
    for j in range(8):stats[4+j]=int(np.count_nonzero((selection==j)&~raw))
    return bits,stats


def python_bits(data,adaptive,k):
    values=[int(v) for v in data.ravel()];wire=[]
    for base in range(0,len(values),32):
        block=values[base:base+32]
        signed=[v if v<128 else v-256 for v in block]
        unsigned=[-2*v-1 if v<0 else 2*v for v in signed]
        costs=[sum((v>>j)+j+1 for v in unsigned) for j in range(8)]
        chosen=min(range(8),key=lambda j:(costs[j],j)) if adaptive else k
        raw=costs[chosen]+(3 if adaptive else 0)>=8*len(block)
        wire.append('1' if raw else '0')
        if not raw and adaptive:wire.append(f'{chosen:03b}')
        for v,u in zip(block,unsigned):
            if raw:wire.append(f'{v:08b}')
            else:wire.append('1'*(u>>chosen)+'0'+(f'{u&((1<<chosen)-1):0{chosen}b}' if chosen else ''))
    return ''.join(wire)


def metrics(values):
    a=np.asarray(values,dtype=np.int64)
    return dict(count=len(a),mean=float(a.mean()),minimum=int(a.min()),
                p50=float(np.quantile(a,.5)),p90=float(np.quantile(a,.9)),
                p95=float(np.quantile(a,.95)),p99=float(np.quantile(a,.99)),maximum=int(a.max()))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--layers',type=int,nargs='+',default=list(range(12)))
    p.add_argument('--samples',type=int,default=256)
    args=p.parse_args();root=Path(__file__).resolve().parents[1]
    assert 1<=args.samples<=256 and len(set(args.layers))==len(args.layers) and all(0<=j<12 for j in args.layers)
    args.output.mkdir(parents=True,exist_ok=False)
    reference=root/'build/model_reference_20261111_201956_613'
    precision=root/'build/precision_bandwidth_20261111'
    frozen_path=root/'build/global_codec_budget_20261112/frozen_global_codecs.json'
    tiled_path=root/'build/tiled_codec_budget_20261112/result.json'
    declaration={
        'schema':'qingyu-adaptive-rice-preregistration-v1','created_utc':datetime.now(timezone.utc).isoformat(),
        'script_sha256':sha(Path(__file__)),'helper_sha256':sha(Path(__file__).with_name('analyze_lossless_command_budget.py')),
        'numeric_policy':'x8_w8_y8_h0','numeric_configuration_changed':False,'fit_uses_training':False,'validation_used_to_fit':False,
        'families':FAMILIES,'fixed_global_k':K,'layers':args.layers,'samples_per_layer_per_split':args.samples,
        'selection_rule':'Per block select least Rice payload bits across k0..7, lower k on tie; include all3 k bits then choose raw if coded is not strictly shorter. Deterministic self-description, no fitted table.',
        'wire':'Block up to32symbols. Raw:1 then n original transformed bytes (8n bits). Rice:0 then adaptive k[2:0] if enabled, then signed8-zigzag unary ones/zero/MSB remainder. Fixed k is known from global stream format. Byte MSB-first bit order and little-endian bus word byte lanes; only stream tail padded to32bits.',
        'row_predictor':'X width64/Y width16: first row predictor0, subsequent rows predict above byte. W no predictor.',
        'gradient_predictor':'X64/Y16 first row predictor0; later first column predicts above; all later columns predict (left+above-upperleft) mod256. Residual=(current-predictor) mod256. Decoder uses only already reconstructed bytes. W unchanged/no predictor.',
        'layout':'X99x64 single stream; W8 independent64x32 groups; Y16 independent99x16 tiles. Predictor epoch and padding reset per stream. No row100 dummy transmitted.',
        'input_header_words':10,'numeric_metadata_words':192,'input_format_fields':['format/version','X encoded bits','8W encoded bits'],
        'output_stored_header_words':17,'output_wire_header_operations':18,'output_header_note':'1 initial invalidate write+16length writes+1finalmagic write; header allocation remains17words.',
        'cold_codebook_words':0,'output_slot_words':398,'output_allocation_words':6385,
        'verification':'Both training and validation; every task25streams actually serialized/independently decoded, predictor inverted, X/W/Y matrices reconstructed exactly; every block count agrees independent NumPy cost. Unique layer W is reencoded/decoded for each task and charged each task.',
        'limits':['No hardware implementation/STA/PPA','Statistics over complete3072 tasks per split only if all12layers and256samples selected',
                  'Service bounds omit dependencies, codec, CPU, cache misses, startup/drain and real loader',
                  'Strict sequential loader then engine is Cload+Cengine; 2I+O assumes ideal aggregate service and cannot assert perfect overlap',
                  'Any future adaptive hardware must count cost-selection state and latency; original measured engine timing does not transfer unchanged'],
    }
    prereg=args.output/'preregistration.json';prereg.write_text(json.dumps(declaration,indent=2)+'\n');prehash=sha(prereg)
    cpp=args.output/'codec.cpp';cpp.write_text(CPP)
    library_path=args.output/'codec.so';command=['g++','-O2','-std=c++17','-shared','-fPIC',str(cpp),'-o',str(library_path)]
    with (args.output/'compile.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    lib=ctypes.CDLL(str(library_path.resolve()));ptr=ctypes.POINTER(ctypes.c_uint8);stats_ptr=ctypes.POINTER(ctypes.c_uint64)
    lib.roundtrip.argtypes=[ptr,ctypes.c_uint64,ctypes.c_int,ctypes.c_uint,ptr,ptr,stats_ptr];lib.roundtrip.restype=ctypes.c_int64
    lib.decode.argtypes=[ptr,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_int,ctypes.c_uint,ptr];lib.decode.restype=ctypes.c_int64
    frozen=json.loads(frozen_path.read_text());assert sha(frozen_path)=='e5e2618ef86c7cf237fde66785b5981c0245c55ecd6cb262031405f620ba0d28'
    tiled=json.loads(tiled_path.read_text());assert tiled['passed']
    study_path=precision/'result.json';study=json.loads(study_path.read_text())
    identities={(v['role'],v['layer']):v['sha256'] for v in study['inputs']}
    provenance={str(frozen_path.relative_to(root)):sha(frozen_path),str(tiled_path.relative_to(root)):sha(tiled_path),str(study_path.relative_to(root)):sha(study_path),
                'scripts/analyze_lossless_command_budget.py':declaration['helper_sha256'],'model/study_precision_bandwidth.py':sha(root/'model/study_precision_bandwidth.py')}
    for key,k in K.items():assert frozen['codecs']['global_rice32'][key]['k']==k
    result={'schema':'qingyu-adaptive-rice-budget-v1','passed':False,'acceptance_passed':False,
            'preregistration_sha256':prehash,'script_sha256':sha(Path(__file__)),'cpp_sha256':sha(cpp),'shared_library_sha256':sha(library_path),
            'compile_command':command,'provenance_sha256':provenance,'numeric_configuration_changed':False,
            'training_used_to_fit':False,'validation_used_to_fit':False,'candidates':{},'limits':declaration['limits'],
            'selftests':{},'actual_task_stream_roundtrips':0,'actual_matrix_elements_roundtripped':0}
    outpath=args.output/'result.json'
    def save():outpath.write_text(json.dumps(result,indent=2)+'\n')
    # This scratch space only transports actual software wire bytes to/from C++.
    wire=np.empty(8192,dtype=np.uint8);stats=np.empty(12,dtype=np.uint64)
    def check(frame,predictor,adaptive,k,expected=None,scalar=False):
        residual=transform(frame,predictor);decoded=np.empty_like(residual)
        bits=int(lib.roundtrip(residual.ctypes.data_as(ptr),residual.size,int(adaptive),k,decoded.ctypes.data_as(ptr),wire.ctypes.data_as(ptr),stats.ctypes.data_as(stats_ptr)))
        assert bits>=0
        want,counts=independent_cost(residual,adaptive,k) if expected is None else expected
        assert bits==want and np.array_equal(stats,counts) and np.array_equal(decoded,residual)
        restored=inverse(decoded,predictor);assert np.array_equal(restored,np.asarray(frame,dtype=np.uint8))
        if scalar:
            actual=''.join(f'{int(v):08b}' for v in wire[:(bits+7)//8])[:bits]
            assert actual==python_bits(residual,adaptive,k)
        return bits,restored,stats.copy(),bytes(wire[:(bits+7)//8])
    save()
    try:
        tests=0;malformed=0;rng=np.random.default_rng(20261112)
        for predictor,row in [('none',32),('row',16),('row',64),('gradient',16),('gradient',64)]:
            frames=[np.arange(256,dtype=np.uint8).reshape(-1,row),rng.integers(0,256,(3,row),dtype=np.uint8),np.zeros((3,row),dtype=np.uint8),np.full((3,row),255,dtype=np.uint8)]
            for adaptive in [False,True]:
                for k in range(8):
                    for frame in frames:
                        bits,_,_,_=check(frame,predictor,adaptive,k,scalar=True);tests+=1
                        assert lib.decode(wire.ctypes.data_as(ptr),bits-1,frame.size,int(adaptive),k,np.empty_like(frame).ctypes.data_as(ptr))<0
                        malformed+=1
        for n in [1,3,4,15,16,31,32,33,63,65]:
            for adaptive in [False,True]:
                for k in range(8):check(rng.integers(0,256,(1,n),dtype=np.uint8),'none',adaptive,k,scalar=True);tests+=1
        result['selftests']=dict(scalar_wire_and_inverse=tests,truncated_rejections=malformed)
        # All formats and deterministic selection rules above were frozen before
        # opening either data split. Training is a report, not a fitting stage.
        for family,policy in FAMILIES.items():
            result['candidates'][family]={'policy':policy,'training':{'layers':[]},'validation':{'layers':[]}}
        for role in ['training','validation']:
            for layer in args.layers:
                cp=precision/'x8_w8_y8_h0'/f'layer{layer:02d}.json'
                assert sha(cp)==frozen['numeric_config_sha256'][str(layer)]
                data_path=reference/f'float_{role}'/f'layer{layer:02d}.npz';assert sha(data_path)==identities[role,layer]
                provenance[str(cp.relative_to(root))]=sha(cp);provenance[str(data_path.relative_to(root))]=sha(data_path)
                config=json.loads(cp.read_text());data=numeric.load(data_path,role)
                x,w,y=quantized(data,config);x=x[:args.samples].astype(np.uint8);w=w.astype(np.uint8);y=y[:args.samples].astype(np.uint8)
                assert len(x)==args.samples and x.shape[1:]==(99,64) and w.shape==(64,256) and y.shape[1:]==(99,256)
                del data
                for family,policy in FAMILIES.items():
                    adaptive=policy['adaptive'];predictor=policy['predictor'];samples=[]
                    digest=hashlib.sha256();sumstats={key:np.zeros(12,dtype=np.uint64) for key in K}
                    # Cache independent expected costs, not the actual W encode/decode.
                    w_costs=[independent_cost(transform(w[:,g*32:(g+1)*32],'none'),adaptive,K['w']) for g in range(8)]
                    for index in range(args.samples):
                        stream_bits={'x':[],'w':[],'y':[]};restored_w=np.empty_like(w);restored_y=np.empty_like(y[index])
                        frames=[('x',0,x[index],predictor,None)]
                        frames += [('w',g,w[:,g*32:(g+1)*32],'none',w_costs[g]) for g in range(8)]
                        frames += [('y',t,y[index,:,t*16:(t+1)*16],predictor,None) for t in range(16)]
                        for key,part,frame,pred,expected in frames:
                            bits,restored,counts,actual_wire=check(frame,pred,adaptive,K[key],expected)
                            assert bits<=8*frame.size+(frame.size+31)//32
                            stream_bits[key].append(bits);sumstats[key]+=counts
                            digest.update(bits.to_bytes(4,'little'));digest.update(actual_wire)
                            if key=='w':restored_w[:,part*32:(part+1)*32]=restored
                            if key=='y':restored_y[:,part*16:(part+1)*16]=restored
                            result['actual_task_stream_roundtrips']+=1;result['actual_matrix_elements_roundtripped']+=frame.size
                        assert np.array_equal(restored_w,w) and np.array_equal(restored_y,y[index])
                        xb=stream_bits['x'][0];wb=stream_bits['w'];yb=stream_bits['y']
                        iw=202+(xb+31)//32+sum((b+31)//32 for b in wb)
                        ow=18+sum((b+31)//32 for b in yb)
                        if role=='validation' and family=='global_rice32':
                            old=tiled['candidates']['global_rice32']['layers'][layer]['samples'][index]
                            assert iw==old['input_words'] and ow==old['output_words']+1
                            assert xb==old['x_bits'] and wb==old['w_group_bits'] and yb==old['y_tile_bits']
                        samples.append(dict(sample_index=index,input_words=iw,output_words=ow,x_bits=xb,w_group_bits=wb,y_tile_bits=yb,
                            input_tail_pad_bits=32*(iw-202)-xb-sum(wb),output_tail_pad_bits=32*(ow-18)-sum(yb)))
                    totals={key:dict(selector_bits=int(v[0]),adaptive_k_bits=int(v[1]),raw_blocks=int(v[2]),rice_blocks=int(v[3]),rice_k_histogram=[int(n) for n in v[4:]]) for key,v in sumstats.items()}
                    result['candidates'][family][role]['layers'].append(dict(layer=layer,samples=samples,actual_wire_stream_sha256=digest.hexdigest(),block_totals=totals))
                    save();print(role.upper(),layer,family,'PASS',flush=True)
                del x,w,y
        target=150000000/10450
        for family,entry in result['candidates'].items():
            for role in ['training','validation']:
                tasks=[s for layer in entry[role]['layers'] for s in layer['samples']]
                i=np.array([s['input_words'] for s in tasks]);o=np.array([s['output_words'] for s in tasks])
                summary={'input_words':metrics(i),'output_words':metrics(o),'input_tail_pad_bits':metrics([s['input_tail_pad_bits'] for s in tasks]),'output_tail_pad_bits':metrics([s['output_tail_pad_bits'] for s in tasks])}
                for name,values in [('preloaded_r1_w1',i+o),('preloaded_r2_w1',2*i+o),('strict_aggregate_r1_w1',2*i+o),('strict_aggregate_r2_w1',3*i+o)]:
                    summary[name]=metrics(values);summary[name]['tasks_below_target_ignoring_all_other_work']=int(np.count_nonzero(values<target))
                summary['target_cycles_at_assumed150mhz']=target
                entry[role]['summary']=summary
        assert sha(prereg)==prehash and sha(Path(__file__))==declaration['script_sha256']
        assert all(sha(root/name)==h for name,h in provenance.items())
        result.update(passed=True,tasks_per_split=len(args.layers)*args.samples,meaning_of_passed='Actual lossless bitstreams, canonical parser, whole-matrix reconstruction, exact source identities and budget bookkeeping only')
        save();print(json.dumps({name:{role:v[role]['summary'] for role in ['training','validation']} for name,v in result['candidates'].items()},indent=2),flush=True)
    except Exception as exc:
        result['failure']=str(exc);save();raise
    print(outpath,flush=True)


if __name__=='__main__':main()
