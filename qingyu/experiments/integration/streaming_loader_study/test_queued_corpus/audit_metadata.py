"""Audit a lossless metadata packing bound; no packet, RTL or calibration is changed."""
from pathlib import Path
import hashlib,json,statistics
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pack(values,width):
 bits=sum((v&((1<<width)-1))<<(width*i) for i,v in enumerate(values))
 return [(bits>>(32*i))&0xffffffff for i in range((len(values)*width+31)//32)]
def unpack(words,width,count,signed):
 bits=sum(v<<(32*i) for i,v in enumerate(words));out=[]
 for i in range(count):
  v=(bits>>(width*i))&((1<<width)-1)
  if signed and v&(1<<(width-1)):v-=1<<width
  out.append(v)
 return out
rows=[];identities={};inputs={}
for sample in [0,9,31,127,202,255]:
 for layer in range(12):
  folder=ROOT/f'build/int8_packet_corpus_20261112/sample{sample:03d}/layer{layer:02d}'
  m=json.loads((folder/'manifest.json').read_text());path=folder/'input.hex'
  if sha(path)!=m['files_sha256']['input.hex']:raise ValueError('Input hash differs')
  words=[int(x,16) for x in path.read_text().split()]
  if len(words)!=m['input_words']:raise ValueError('Input length differs')
  bias=[];shifts=[]
  for word in words[10:138]:
   for i in range(2):
    v=(word>>(16*i))&65535;bias.append(v-65536 if v&32768 else v)
  for word in words[138:202]:shifts.extend((word>>(8*i))&255 for i in range(4))
  ident=hashlib.sha256(json.dumps(dict(bias=bias,shifts=shifts),sort_keys=True).encode()).hexdigest()
  if layer in identities and identities[layer]!=ident:raise ValueError('Layer metadata varies between diagnostic samples')
  identities[layer]=ident;inputs[path.relative_to(ROOT).as_posix()]=sha(path)
  if sample:continue
  width=next(n for n in range(2,17) if min(bias)>=-(1<<(n-1)) and max(bias)<(1<<(n-1)))
  swidth=max(1,max(shifts).bit_length())
  b=pack(bias,width);s=pack(shifts,swidth)
  if unpack(b,width,256,True)!=bias or unpack(s,swidth,256,False)!=shifts:raise ValueError('Lossless roundtrip failed')
  saved=192-len(b)-len(s)
  rows.append(dict(layer=layer,bias_min=min(bias),bias_max=max(bias),bias_bits=width,shift_min=min(shifts),shift_max=max(shifts),shift_bits=swidth,
    original_metadata_words=192,packed_bias_words=len(b),packed_shift_words=len(s),saved_source_words_no_extra_header=saved,
    service_floor_reduction_no_extra_header=2*saved,service_floor_reduction_one_extra_header=2*(saved-1),
    metadata_sha256=ident,exact_roundtrip=True))
out=dict(schema='qingyu-lossless-metadata-packing-bound-v1',passed=True,scope='Six diagnostic samples x12 layers; each layer metadata identity equal across the six samples; no full3072 generalization',
 input_sha256=inputs,layers=rows,
 average_saved_source_words_no_extra_header=statistics.mean(x['saved_source_words_no_extra_header'] for x in rows),
 average_service_floor_reduction_no_extra_header=statistics.mean(x['service_floor_reduction_no_extra_header'] for x in rows),
 average_service_floor_reduction_one_extra_header=statistics.mean(x['service_floor_reduction_one_extra_header'] for x in rows),
 implementation_requirements=['New versioned packet ABI and independent packet/metadata oracle; unchanged numerical values','Signed bias extension and shift byte reconstruction must preserve every original private metadata word','Sustain original private metadata ready/valid throughput with a bounded bit reservoir, preserving held data','New header/payload length and loader watermark boundaries must be verified on both bus credit modes','Abort/error/reset must discard private parser state while transport drains accepted/offered requests'],
 limits=['No new packet or RTL is implemented','Floor reduction is a bandwidth-budget change, not a promised elapsed-cycle improvement','Any added header or alignment words reduce the budget gain; any parser stalls may erase it','No PPA, timing, E203 or official loader proof'])
(HERE/'METADATA_BOUND.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k.startswith('average_')},indent=2));print(sha(HERE/'METADATA_BOUND.json'))
