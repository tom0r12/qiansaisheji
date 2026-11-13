"""Exercise all source-guard substitutions before sending a server job."""
from pathlib import Path
import ast,hashlib,struct,sys
H=Path(__file__).resolve().parent;R=H.parents[2]
source=(H/'run_dense.py').read_text();ast.parse(source)
start=source.index(' runner=(P/');end=source.index(' (P/\'run_vendor.py\').write_text',start)
part=source[start:end]
part='\n'.join(s[1:]for s in part.splitlines())
ns={'P':R/'final/q12_20261113/vendor','fw':'a'*64}
exec(part,ns);ast.parse(ns['runner'])
assert '10353'not in ns['runner']
assert "task['baseline_format_differs']=True"in ns['runner']
assert "if v['reads']!=row['input_words']"in ns['runner']
assert "explicit_accounting(text)"in ns['runner']
sys.path.insert(0,str(H));from decode_native import decode_output
for p in (H.parent/'build/dense12_w10_wp').glob('case*/expected.hex'):
 words=[int(s,16)for s in p.read_text().split()];values=decode_output(words)
 assert len(values)==25344 and all(-2048<=v<=2047 for v in values)
 for r in range(99):
  for c in range(256):
   t=c//16;ix=r*16+c%16;pos=17+t*594+(ix*12)//32;sh=(ix*12)%32
   v=((words[pos]|((words[pos+1]if pos+1<len(words)else 0)<<32))>>sh)&4095
   assert values[r*256+c]==(v-4096 if v&2048 else v)
print('PASS guarded vendor-runner substitutions, Python syntax, native fixed-index readback')
import numpy as np
sys.path.insert(0,str(R/'final/q12_20261113/freeze_snapshot/output/eda/q12_candidate/packing'))
import rice_words,packet_reference
rng=np.random.default_rng(339173)
for k,delta in [(6,True),(7,False),(9,False)]:
 for limit in [1,32,512,2048]:
  a=rng.integers(-limit,limit,size=(99,64)if delta else(64,32))
  expected=rice_words.encode(a,12,k,delta)
  actual=packet_reference.encode(a.tolist(),12,k,delta)
  assert actual==expected
  assert packet_reference.decode(*actual,a.shape,12,k,delta)==a.tolist()
print('PASS standard-library input codec: 12 independent packet/roundtrip comparisons')
