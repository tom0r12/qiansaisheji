"""Pre-registered, training-frozen global lossless INT8 transport formats.

No numerical policy changes. Actual bitstreams are encoded and independently
decoded for every validation X/Y frame and every unique layer W. C++ is used
only to make the software bitstream checks practical; its runtime is not RTL
throughput. All output files go into a new, never-overwritten analysis directory.
"""
from __future__ import annotations
import argparse
import ctypes
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
from statistics import mean
import numpy as np
from analyze_lossless_command_budget import canonical, lengths_for, numeric, quantized, sha, symbols, undo_symbols


CPP = r'''
#include <cstdint>
#include <vector>
#include <stdexcept>
#include <algorithm>
struct Bits {
  std::vector<uint8_t> data; uint64_t size=0, pos=0;
  void put(uint32_t v,int n) { for(int j=n-1;j>=0;--j){ if(!(size&7))data.push_back(0); data.back()|=((v>>j)&1)<<(7-(size&7)); ++size; } }
  uint32_t get(int n){uint32_t v=0;for(int j=0;j<n;++j){if(pos>=size)throw std::runtime_error("end");v=(v<<1)|((data[pos/8]>>(7-(pos&7)))&1);++pos;}return v;}
};
static unsigned zig(uint8_t byte){int s=byte<128?byte:int(byte)-256;return s<0?unsigned(-2*s-1):unsigned(2*s);}
static uint8_t unzig(unsigned u){if(u>255)throw std::runtime_error("symbol");int s=(u&1)?-int((u+1)/2):int(u/2);return uint8_t(s);}
extern "C" int64_t roundtrip(const uint8_t* src,uint64_t count,int mode,int k,
                              const uint8_t* lens,const uint32_t* codes,uint8_t* out){
 try{
  Bits bits;
  if(mode==0){for(uint64_t i=0;i<count;++i)bits.put(src[i],8);}
  else if(mode==1){for(uint64_t i=0;i<count;++i)bits.put(codes[src[i]],lens[src[i]]);}
  else for(uint64_t start=0;start<count;start+=32){
   uint64_t end=std::min(count,start+32);unsigned width=0,rice=0;
   for(uint64_t i=start;i<end;++i){unsigned u=zig(src[i]),w=0;while(u>>w)++w;width=std::max(width,w);rice+=(zig(src[i])>>k)+1+k;}
   if(mode==2){
    bool raw=rice>=8*(end-start);bits.put(raw,1);
    for(uint64_t i=start;i<end;++i){unsigned u=zig(src[i]);if(raw)bits.put(src[i],8);else{for(unsigned q=u>>k;q;--q)bits.put(1,1);bits.put(0,1);bits.put(u&((1u<<k)-1),k);}}
   }else{bits.put(width,4);for(uint64_t i=start;i<end;++i)bits.put(zig(src[i]),width);}
  }
  if(mode==0){for(uint64_t i=0;i<count;++i)out[i]=bits.get(8);}
  else if(mode==1){
   struct Node{int child[2]={-1,-1};int symbol=-1;};std::vector<Node> tree(1);
   for(int s=0;s<256;++s){int node=0;for(int j=lens[s]-1;j>=0;--j){int b=(codes[s]>>j)&1;if(tree[node].symbol>=0)throw std::runtime_error("prefix");if(tree[node].child[b]<0){int next=tree.size();tree[node].child[b]=next;tree.emplace_back();}node=tree[node].child[b];}if(tree[node].symbol>=0||tree[node].child[0]>=0||tree[node].child[1]>=0)throw std::runtime_error("code");tree[node].symbol=s;}
   for(uint64_t i=0;i<count;++i){int node=0;while(tree[node].symbol<0){node=tree[node].child[bits.get(1)];if(node<0)throw std::runtime_error("decode");}out[i]=tree[node].symbol;}
  }else for(uint64_t start=0;start<count;start+=32){
   uint64_t end=std::min(count,start+32);
   if(mode==2){bool raw=bits.get(1);for(uint64_t i=start;i<end;++i){if(raw)out[i]=bits.get(8);else{unsigned q=0;while(bits.get(1)){if(++q>255)throw std::runtime_error("unary");}out[i]=unzig((q<<k)|bits.get(k));}}}
   else{unsigned width=bits.get(4);if(width>8)throw std::runtime_error("width");for(uint64_t i=start;i<end;++i)out[i]=unzig(bits.get(width));}
  }
  if(bits.pos!=bits.size)throw std::runtime_error("trailing");
  return bits.size;
 }catch(...){return -1;}
}
'''


def zigzag(array):
    signed = array.astype(np.int16)
    signed[signed >= 128] -= 256
    return np.where(signed < 0, -2*signed-1, 2*signed).astype(np.uint16)


def block_cost(array):
    u = zigzag(array).reshape(-1, 32)
    rice = [int((1 + np.minimum(256, (u >> k).sum(axis=1) + 32*(k+1))).sum()) for k in range(8)]
    maximum = u.max(axis=1)
    width = np.zeros(256, dtype=np.uint16)
    for value in range(256):
        width[value] = value.bit_length()
    packed = int((4 + 32*width[maximum]).sum())
    return rice, packed


def measure(samples, fn):
    counts = [fn(i, o) for i, o in samples]
    average = mean(counts)
    return {"service_cycles_mean": average, "service_cycles_min": min(counts),
            "service_cycles_max": max(counts), "task_s_upper_bound_from_mean": 150e6/average,
            "samples_below_target_ignoring_all_other_work": sum(v < 150e6/10450 for v in counts),
            "samples": len(counts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-run', type=Path, required=True)
    parser.add_argument('--precision-run', type=Path, required=True)
    parser.add_argument('--per-layer-codec-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    study = json.loads((args.precision_run/'result.json').read_text())
    frozen = json.loads((args.precision_run/'frozen_config_sha256.json').read_text())
    identities = {(item['role'], item['layer']): item['sha256'] for item in study['inputs']}
    policy = 'x8_w8_y8_h0'
    declaration = {
        'schema': 'qingyu-global-lossless-preregistration-v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'script_sha256': sha(Path(__file__)), 'helper_sha256': sha(Path(__file__).with_name('analyze_lossless_command_budget.py')),
        'numeric_policy': policy, 'training_layers': list(range(12)), 'validation_used_to_fit': False,
        'candidates': ['raw8', 'global_huffman', 'global_rice32', 'global_bitpack32'],
        'transform_candidates': ['raw bytes', 'preceding-row modular delta, reset at every matrix/frame'],
        'huffman_fit': 'one histogram/table per X/W/Y, all 12 training layers merged; pseudocount 1 for every byte; minimize unpadded training symbol bits, raw on tie',
        'rice_fit': 'one k in 0..7 and one transform per X/W/Y; blocks of 32 zigzag signed8 symbols; 1-bit raw fallback selector; minimize exact training block bits, raw transform then lower k on tie',
        'bitpack_fit': 'one transform per X/W/Y; block32 zigzag with 4-bit width 0..8; minimize exact training block bits, raw transform on tie',
        'weights_in_fit': 'every training task loads its layer weights; W histogram and cost repeated by training frame count',
        'metadata': {'numeric_input_words': 192, 'bias_signed_bits': 16, 'shift_bits_per_channel': 8,
                     'input_header_words': 3, 'output_header_words': 2, 'cold_codebook_words': 0,
                     'input_header': ['format/version', 'X encoded bit count', 'W encoded bit count'],
                     'output_header': ['format/version', 'Y encoded bit count']},
        'padding': 'Each X/W/Y bitstream separately rounded up to a full 32-bit word; blocks are not separately word padded',
        'scope': 'Generic lossless format constants only; no layer IDs, model weights or matrix outputs embedded in ROM',
        'bitstream_check': 'All validation X/Y frames and each unique layer W actually encoded and decoded; delta reconstruction compared with original quantized bytes',
        'generic_alphabet_check': 'Every selected stream format roundtrips both all 256 raw byte values and a constructed input producing all 256 transformed symbols',
    }
    registration = args.output/'preregistration.json'
    registration.write_text(json.dumps(declaration, indent=2)+'\n')
    registration_hash = sha(registration)
    cpp_path = args.output/'codec_roundtrip.cpp'
    cpp_path.write_text(CPP)
    library_path = args.output/'codec_roundtrip.so'
    command = ['g++', '-O2', '-std=c++17', '-shared', '-fPIC', str(cpp_path), '-o', str(library_path)]
    with (args.output/'compile.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    library = ctypes.CDLL(str(library_path.resolve()))
    pointer = ctypes.POINTER(ctypes.c_uint8)
    library.roundtrip.argtypes = [pointer, ctypes.c_uint64, ctypes.c_int, ctypes.c_int, pointer,
                                  ctypes.POINTER(ctypes.c_uint32), pointer]
    library.roundtrip.restype = ctypes.c_int64
    histograms = {key: [np.zeros(256, dtype=np.int64) for _ in range(2)] for key in ('x','w','y')}
    rice_costs = {key: [np.zeros(8, dtype=np.int64) for _ in range(2)] for key in histograms}
    pack_costs = {key: [0, 0] for key in histograms}
    bias_min, bias_max = 0, 0
    config_hashes = {}
    for layer in range(12):
        cp = args.precision_run/policy/f'layer{layer:02d}.json'
        assert sha(cp) == frozen[f'{policy}/layer{layer:02d}.json']
        config_hashes[str(layer)] = sha(cp)
        config = json.loads(cp.read_text())
        path = args.reference_run/'float_training'/f'layer{layer:02d}.npz'
        assert sha(path) == identities['training', layer]
        data = numeric.load(path, 'training')
        values = quantized(data, config)
        bias = np.rint(data['b'].astype(np.float64)/np.exp2(np.asarray(config['w_exponents'])+config['x_exponent'])).astype(np.int64)
        bias_min, bias_max = min(bias_min, int(bias.min())), max(bias_max, int(bias.max()))
        assert np.all((bias >= -32768) & (bias < 32768))
        for key, value in zip(histograms, values):
            repeats = len(values[0]) if key == 'w' else 1
            for delta in (0, 1):
                encoded = symbols(value, bool(delta))
                histograms[key][delta] += repeats*np.bincount(encoded.ravel(), minlength=256)
                rice, packed = block_cost(encoded)
                rice_costs[key][delta] += repeats*np.asarray(rice)
                pack_costs[key][delta] += repeats*packed
        print('TRAIN', layer, flush=True)
    codecs = {name: {} for name in declaration['candidates']}
    trials = {}
    for key in histograms:
        options = []
        for delta in (0,1):
            lengths = lengths_for(histograms[key][delta])
            options.append((int(histograms[key][delta]@lengths), delta, lengths))
        cost, delta, lengths = min(options, key=lambda item: item[:2])
        assert max(lengths) <= 31
        codecs['raw8'][key] = {'mode': 0, 'row_delta': False}
        codecs['global_huffman'][key] = {'mode': 1, 'row_delta': bool(delta), 'lengths': lengths.tolist(), 'training_bits': cost}
        cost, delta, k = min((int(rice_costs[key][d][k]), d, k) for d in (0,1) for k in range(8))
        codecs['global_rice32'][key] = {'mode': 2, 'row_delta': bool(delta), 'k': k, 'training_bits': cost}
        cost, delta = min((pack_costs[key][d], d) for d in (0,1))
        codecs['global_bitpack32'][key] = {'mode': 3, 'row_delta': bool(delta), 'training_bits': cost}
        trials[key] = {'huffman_bits_by_transform': [o[0] for o in options],
                       'rice_bits_by_transform_and_k': [v.tolist() for v in rice_costs[key]],
                       'bitpack_bits_by_transform': pack_costs[key]}
    declaration_path = args.output/'frozen_global_codecs.json'
    declaration_path.write_text(json.dumps({'codecs': codecs, 'training_trials': trials, 'numeric_config_sha256': config_hashes,
                                           'bias_min': bias_min, 'bias_max': bias_max}, indent=2)+'\n')
    codec_hash = sha(declaration_path)
    print('ALL CODECS FROZEN', codec_hash, flush=True)
    # No validation data has been opened before the frozen file above.
    report = {'schema': 'qingyu-global-codec-budget-v1', 'passed': False, 'acceptance_passed': False,
              'created_utc': datetime.now(timezone.utc).isoformat(), 'preregistration_sha256': registration_hash,
              'frozen_codecs_sha256': codec_hash, 'script_sha256': sha(Path(__file__)),
              'cpp_sha256': sha(cpp_path), 'shared_library_sha256': sha(library_path), 'compile_command': command,
              'numeric_configuration_changed': False, 'numeric_policy': policy, 'candidates': {},
              'bias_range': [bias_min, bias_max], 'metadata': declaration['metadata'],
              'validation_tasks': 3072, 'validation_unique_weight_matrices': 12,
              'throughput_symbol_floors': {'input_symbols': 22720, 'output_symbols': 25344,
                                          'two_input_symbols_per_cycle': 11360, 'four_input_symbols_per_cycle': 5680,
                                          'two_output_symbols_per_cycle': 12672, 'four_output_symbols_per_cycle': 6336},
              'limits': ['No RTL codec, PPA, STA or complete SoC measurement',
                         'Service bounds exclude codec, CPU, dependency, startup, drain and cache-miss overhead',
                         'R1/W1 requires actual hit/slave/fabric evidence; it is not assumed for all accesses',
                         'Precise official loader starting event remains OPEN',
                         'Fixed ROM constants and per-cycle parallel lookup replication are not zero-area']}
    for name in codecs:
        report['candidates'][name] = {'streams': codecs[name], 'layers': []}
    def roundtrip(frame, codec):
        transformed = np.ascontiguousarray(symbols(frame, codec['row_delta']))
        restored = np.empty_like(transformed)
        lengths = np.asarray(codec.get('lengths', [8]*256), dtype=np.uint8)
        mapping = canonical(lengths) if codec['mode'] == 1 else {s: (s,8) for s in range(256)}
        codes = np.asarray([mapping[s][0] for s in range(256)], dtype=np.uint32)
        bits = library.roundtrip(transformed.ctypes.data_as(pointer), transformed.size,
                                 codec['mode'], codec.get('k',0), lengths.ctypes.data_as(pointer),
                                 codes.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)), restored.ctypes.data_as(pointer))
        assert bits >= 0
        assert np.array_equal(undo_symbols(restored, codec['row_delta']), (frame & 255).astype(np.uint8))
        if codec['mode'] == 0:
            assert bits == 8*frame.size
        elif codec['mode'] == 1:
            assert bits == int(lengths[transformed].sum())
        else:
            rice, pack = block_cost(transformed)
            assert bits == (rice[codec['k']] if codec['mode'] == 2 else pack)
        return int(bits)
    alphabet = np.arange(256, dtype=np.uint8).reshape(4,64)
    alphabet_checks = 0
    for streams in codecs.values():
        for codec in streams.values():
            roundtrip(alphabet, codec)
            roundtrip(undo_symbols(alphabet, codec['row_delta']), codec)
            alphabet_checks += 2
    report['generic_alphabet_roundtrips'] = alphabet_checks
    for layer in range(12):
        cp = args.precision_run/policy/f'layer{layer:02d}.json'
        assert sha(cp) == config_hashes[str(layer)]
        path = args.reference_run/'float_validation'/f'layer{layer:02d}.npz'
        assert sha(path) == identities['validation', layer]
        values = quantized(numeric.load(path, 'validation'), json.loads(cp.read_text()))
        for name, streams in codecs.items():
            lengths = {}
            for key, value in zip(('x','w','y'), values):
                frames = [value] if key == 'w' else value
                lengths[key] = [roundtrip(frame, streams[key]) for frame in frames]
            samples = []
            for sample in range(len(values[0])):
                x, w, y = lengths['x'][sample], lengths['w'][0], lengths['y'][sample]
                samples.append({'sample_index': sample, 'x_bits': x, 'w_bits': w, 'y_bits': y,
                                'input_words': (x+31)//32 + (w+31)//32 + 192 + 3,
                                'output_words': (y+31)//32 + 2})
            report['candidates'][name]['layers'].append({'layer': layer, 'samples': samples, 'data_sha256': sha(path)})
            print('VALIDATION', layer, name, flush=True)
        (args.output/'partial_result.json').write_text(json.dumps(report, indent=2)+'\n')
    original = json.loads((args.per_layer_codec_run/'result.json').read_text())
    assert original['passed']
    original_samples = [sample for layer in original['layers'] for sample in layer['samples_commands']]
    for name, entry in report['candidates'].items():
        samples = [(s['input_words'], s['output_words']) for layer in entry['layers'] for s in layer['samples']]
        entry['mean_input_words'] = mean(i for i,_ in samples)
        entry['mean_output_words'] = mean(o for _,o in samples)
        entry['service_bounds'] = {
            'preloaded_r1_w1': measure(samples, lambda i,o:i+o),
            'preloaded_r2_w1': measure(samples, lambda i,o:2*i+o),
            'strict_loader_write_read_output_r1_w1': measure(samples, lambda i,o:2*i+o),
            'strict_loader_write_read_output_r2_w1': measure(samples, lambda i,o:3*i+o),
        }
        entry['rom'] = {'cold_codebook_words': 0, 'note': 'Logical format constants only; physical area/ports/replication not measured'}
        if name == 'global_huffman':
            lengths = {k: np.asarray(v['lengths']) for k,v in entry['streams'].items()}
            maxima = {k: int(v.max()) for k,v in lengths.items()}
            entry['rom'].update({'canonical_code_length_definition_bytes': 3*256,
                                 'maximum_code_bits': maxima,
                                 'one_y_encoder_table_bits': 256*(maxima['y']+math.ceil(math.log2(maxima['y']+1))),
                                 'two_canonical_input_decoder_constant_bits': sum(256*8+maxima[k]*(maxima[k]+18) for k in ('x','w'))})
            entry['versus_original_per_layer_huffman'] = {
                'source_result_sha256': sha(args.per_layer_codec_run/'result.json'),
                'input_payload_word_delta_mean': entry['mean_input_words']-195-mean(s['input_words']-772 for s in original_samples),
                'output_payload_word_delta_mean': entry['mean_output_words']-2-mean(s['output_words'] for s in original_samples),
                'removed_cold_codebook_words': 192,
                'header_change_input_words': -1, 'header_change_output_words': 2,
                'note': 'Compression loss is remeasured with the new global tables; not inferred by subtracting cold tables'}
        else:
            entry['rom']['fixed_parameter_bits'] = 0 if name == 'raw8' else (12 if name == 'global_rice32' else 3)
    assert sha(registration) == registration_hash and sha(declaration_path) == codec_hash
    report['passed'] = True
    report['meaning_of_passed'] = 'Source/config identities, training freeze, actual software lossless bitstream roundtrips and independent bit counts passed; no performance acceptance'
    (args.output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({name: {'input_words': entry['mean_input_words'], 'output_words': entry['mean_output_words'],
                           'bounds': entry['service_bounds']} for name,entry in report['candidates'].items()}, indent=2), flush=True)
    print(args.output/'result.json', flush=True)


if __name__ == '__main__':
    main()
