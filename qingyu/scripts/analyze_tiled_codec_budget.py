"""Measure fixed global codecs with an explicitly tiled transport layout.

The existing training-frozen codec parameters and numerical configuration are
not refit. This is a new preregistered layout study, not an RTL speed claim.
"""
from datetime import datetime, timezone
import argparse
import ctypes
import json
from pathlib import Path
from statistics import mean
import numpy as np
from analyze_global_codec_budget import zigzag, measure
from analyze_lossless_command_budget import canonical, numeric, quantized, sha, symbols, undo_symbols


def rice_bits(values, k):
    u = zigzag(values).ravel()
    full = len(u)//32*32
    cost = int((1+np.minimum(256,(u[:full].reshape(-1,32)>>k).sum(axis=1)+32*(k+1))).sum())
    if full < len(u):
        tail = u[full:]
        cost += 1+min(8*len(tail),int((tail>>k).sum())+len(tail)*(k+1))
    return cost


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    origin=root/'build/global_codec_budget_20261112'
    precision=root/'build/precision_bandwidth_20261111'
    reference=root/'build/model_reference_20261111_201956_613'
    args.output.mkdir(parents=True,exist_ok=False)
    frozen_path=origin/'frozen_global_codecs.json'
    frozen=json.loads(frozen_path.read_text())
    original=json.loads((origin/'result.json').read_text())
    assert original['passed'] and sha(frozen_path)==original['frozen_codecs_sha256']
    families=['global_huffman','global_rice32']
    declaration={'schema':'qingyu-tiled-codec-layout-v1','created_utc':datetime.now(timezone.utc).isoformat(),
      'script_sha256':sha(Path(__file__)),'origin_codec_sha256':sha(frozen_path),
      'origin_result_sha256':sha(origin/'result.json'),'numerical_policy':'x8_w8_y8_h0',
      'parameters_refit':False,'validation_used_to_fit':False,'families':families,
      'x':'One 99x64 row-major stream; preceding-row delta retains width64; dummy row100 zeros locally generated, never transmitted',
      'w':'Eight independently padded 64x32 column-group streams; within each stream K-row-major; each 32-symbol Rice block is one full row',
      'y':'Sixteen independently padded 99x16 column-tile streams; preceding-row delta resets at each tile; width16; final Rice block has16 symbols',
      'headers':{'input_words':10,'input_fields':['format/version','X encoded bits','W group0..7 encoded bits'],
                 'output_words':17,'output_fields':['format/version','Y tile0..15 encoded bits']},
      'numeric_metadata_words':192,'cold_codebook_words':0,
      'independent_validation':'Every stream encoded/decoded using frozen native bit codec; undo delta and reconstruct original whole X/W/Y matrix byte-for-byte',
      'limits':['Same integer numerics; no new precision acceptance','All cold inputs still loaded each task',
                'No hardware reordering, multi-tile retention or overlapping pipeline measured',
                'Array current load ordering still needs explicit bounded reordering adapters',
                'Headers charged but not physically bus-serialized by this study']}
    registration=args.output/'preregistration.json'
    registration.write_text(json.dumps(declaration,indent=2)+'\n')
    prereg_hash=sha(registration)
    library_path=origin/'codec_roundtrip.so'
    assert sha(library_path)==original['shared_library_sha256']
    library=ctypes.CDLL(str(library_path.resolve()))
    pointer=ctypes.POINTER(ctypes.c_uint8)
    library.roundtrip.argtypes=[pointer,ctypes.c_uint64,ctypes.c_int,ctypes.c_int,pointer,ctypes.POINTER(ctypes.c_uint32),pointer]
    library.roundtrip.restype=ctypes.c_int64
    prepared={}
    for family in families:
        prepared[family]={}
        for key,codec in frozen['codecs'][family].items():
            lens=np.asarray(codec.get('lengths',[8]*256),dtype=np.uint8)
            mapping=canonical(lens) if codec['mode']==1 else {s:(s,8) for s in range(256)}
            codes=np.asarray([mapping[s][0] for s in range(256)],dtype=np.uint32)
            prepared[family][key]=(codec,lens,codes)
    count=0
    def roundtrip(frame, family, key):
        nonlocal count
        codec,lens,codes=prepared[family][key]
        transformed=np.ascontiguousarray(symbols(frame,codec['row_delta']))
        decoded=np.empty_like(transformed)
        bits=library.roundtrip(transformed.ctypes.data_as(pointer),transformed.size,codec['mode'],codec.get('k',0),
                               lens.ctypes.data_as(pointer),codes.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)),decoded.ctypes.data_as(pointer))
        assert bits>=0
        expected=int(lens[transformed].sum()) if codec['mode']==1 else rice_bits(transformed,codec['k'])
        assert bits==expected
        restored=undo_symbols(decoded,codec['row_delta'])
        assert np.array_equal(restored,(frame&255).astype(np.uint8))
        count+=1
        return int(bits),restored
    identities={(x['role'],x['layer']):x['sha256'] for x in json.loads((precision/'result.json').read_text())['inputs']}
    report={'passed':False,'acceptance_passed':False,'preregistration_sha256':prereg_hash,
            'frozen_global_codecs_sha256':sha(frozen_path),'script_sha256':sha(Path(__file__)),
            'headers':declaration['headers'],'candidates':{family:{'layers':[]} for family in families},'limits':declaration['limits']}
    for layer in range(12):
        config_path=precision/'x8_w8_y8_h0'/f'layer{layer:02d}.json'
        assert sha(config_path)==frozen['numeric_config_sha256'][str(layer)]
        data_path=reference/'float_validation'/f'layer{layer:02d}.npz'
        assert sha(data_path)==identities['validation',layer]
        values=quantized(numeric.load(data_path,'validation'),json.loads(config_path.read_text()))
        x,w,y=values
        for family in families:
            w_bits=[];restored_w=np.empty_like(w,dtype=np.uint8)
            for group in range(8):
                sl=slice(group*32,(group+1)*32)
                bits,restored=roundtrip(w[:,sl],family,'w');w_bits.append(bits);restored_w[:,sl]=restored
            assert np.array_equal(restored_w,(w&255).astype(np.uint8))
            samples=[]
            for sample in range(len(x)):
                xb,_=roundtrip(x[sample],family,'x')
                yb=[];restored_y=np.empty_like(y[sample],dtype=np.uint8)
                for tile in range(16):
                    sl=slice(tile*16,(tile+1)*16)
                    bits,restored=roundtrip(y[sample,:,sl],family,'y');yb.append(bits);restored_y[:,sl]=restored
                assert np.array_equal(restored_y,(y[sample]&255).astype(np.uint8))
                samples.append({'sample_index':sample,'x_bits':xb,'w_group_bits':w_bits,'y_tile_bits':yb,
                    'input_words':(xb+31)//32+sum((b+31)//32 for b in w_bits)+192+10,
                    'output_words':sum((b+31)//32 for b in yb)+17})
            report['candidates'][family]['layers'].append({'layer':layer,'samples':samples,'input_sha256':sha(data_path)})
            print('VALIDATION',layer,family,flush=True)
        (args.output/'partial_result.json').write_text(json.dumps(report,indent=2)+'\n')
    for family,entry in report['candidates'].items():
        samples=[(x['input_words'],x['output_words']) for layer in entry['layers'] for x in layer['samples']]
        entry['mean_input_words']=mean(i for i,o in samples)
        entry['mean_output_words']=mean(o for i,o in samples)
        entry['service_bounds']={'preloaded_r1_w1':measure(samples,lambda i,o:i+o),
          'preloaded_r2_w1':measure(samples,lambda i,o:2*i+o),
          'strict_loader_write_read_output_r1_w1':measure(samples,lambda i,o:2*i+o),
          'strict_loader_write_read_output_r2_w1':measure(samples,lambda i,o:3*i+o)}
        entry['layout_overhead_vs_original_words']={
          'input_mean':entry['mean_input_words']-original['candidates'][family]['mean_input_words'],
          'output_mean':entry['mean_output_words']-original['candidates'][family]['mean_output_words']}
    assert sha(registration)==prereg_hash and sha(frozen_path)==original['frozen_codecs_sha256']
    report.update(passed=True,actual_stream_roundtrips=count,validation_tasks=3072,
                  meaning_of_passed='Frozen identity, actual lossless payload encoding/decoding and complete tiled-matrix reconstruction only')
    (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:{n:v for n,v in e.items() if n!='layers'} for k,e in report['candidates'].items()},indent=2))
    print(args.output/'result.json',flush=True)


if __name__=='__main__':main()
