"""Read-only packet/numeric exploration on the user's private contest server.
No training, no fixture alteration, no data export. Output aggregate metrics only.
"""
from pathlib import Path
import hashlib,json,math,collections,time
BASE_HASH='BASE_HASH'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def words(p):return [int(v,16)for v in p.read_text().split()]
def dec(words,nbits,n,k,cols=0):
 bits=''.join(format(b,'08b')for w in words for b in w.to_bytes(4,'little'))[:nbits]
 pos=0;out=[]
 def get(n):
  nonlocal pos
  v=int(bits[pos:pos+n],2)if n else 0;pos+=n;return v
 while len(out)<n:
  raw=get(1)
  for _ in range(min(32,n-len(out))):
   if raw:v=get(12);v=v-4096 if v&2048 else v
   else:
    end=bits.index('0',pos);q=end-pos;pos=end+1;z=(q<<k)|get(k);v=-(z+1)//2 if z&1 else z//2
   if cols:
    v=((v+(out[-cols]if len(out)>=cols else 0))+2048)%4096-2048
   out.append(v)
 assert pos==nbits
 return out
def rounded(v,k):
 if k<=0:return v<<(-k)
 q,r=divmod(abs(v),1<<k);q+=r>(1<<(k-1))or(r==(1<<(k-1))and q&1)
 return -q if v<0 else q
def encoded_length(v,k,width=12):
 z=[-2*x-1 if x<0 else 2*x for x in v]
 return sum(1+min(width*len(z[i:i+32]),sum((x>>k)+1+k for x in z[i:i+32]))for i in range(0,len(z),32))
matches=[p.parent for p in Path('/tmp/q12_final_s4_36usr_20261113').glob('*/manifest.json')if sha(p)==BASE_HASH]
assert len(matches)==1,matches
b=matches[0];m=json.loads((b/'manifest.json').read_text())
summary={'scope':'historical12 packet study; error is relative to frozen Q12, not official float600', 'tasks':[]}
try:
 import numpy as np
except ImportError:np=None
print('PACKET_STUDY numpy='+str(np is not None),flush=True)
for row in m['tasks']:
 d=b/'tasks'/row['directory'];packet=words(d/'input.hex');bias=[v-(1<<32)if v&(1<<31)else v for v in packet[10:266]]
 shifts=[(v>>s)&255 for v in packet[266:330]for s in(0,8,16,24)]
 xwords=(packet[1]+31)//32;x=dec(packet[330:330+xwords],packet[1],6336,6,64)
 p=330+xwords;weights=[];weight_flat=[]
 for group in range(8):
  nbits=packet[2+group];nw=(nbits+31)//32;v=dec(packet[p:p+nw],nbits,2048,9);p+=nw;weights.append(v);weight_flat+=v
 assert p==len(packet)
 original=[v-65536 if v&32768 else v for v in words(d/'dense.hex')]
 if np is not None:
  xx=np.array(x,dtype=np.int64).reshape(99,64)
  ww=np.concatenate([np.array(v,dtype=np.int64).reshape(64,32)for v in weights],axis=1)
 counts=collections.Counter(weight_flat);entropy=-sum(n/16384*math.log(n/16384,2)for n in counts.values())
 record={'task':row['task'],'input_words':len(packet),'weight_entropy_bits_per_value':entropy,'candidates':[]}
 for wb,yb in ((12,13),(11,13),(10,13),(11,12),(10,12),(11,11)):
  cut=12-wb;outcut=13-yb
  quant=[[max(-(1<<(wb-1)),min((1<<(wb-1))-1,rounded(v,cut)))for v in g]for g in weights]
  bits=[encoded_length(v,9-cut)for v in quant]
  nw=330+xwords+sum((n+31)//32 for n in bits)
  qb=[rounded(v,cut)for v in bias];qs=[s-cut+outcut for s in shifts];assert min(qs)>=0
  if np is not None:
   wq=np.concatenate([np.array(v,dtype=np.int64).reshape(64,32)for v in quant],axis=1)
   acc=(xx@wq+np.array(qb,dtype=np.int64)).ravel().tolist()
  else:
   cols=[[quant[c//32][i*32+c%32]for i in range(64)]for c in range(256)]
   acc=[sum(a*b for a,b in zip(x[r*64:(r+1)*64],cols[c]))+qb[c]for r in range(99)for c in range(256)]
  new=[max(-(1<<(yb-1)),min((1<<(yb-1))-1,rounded(v,qs[i%256])))<<outcut for i,v in enumerate(acc)]
  sse=sum((a-b)**2 for a,b in zip(original,new));rms=math.sqrt(sum(v*v for v in original)/len(original));dynamic=max(original)-min(original)
  rmse=math.sqrt(sse/len(original))
  result={'w_bits':wb,'y_bits':yb,'input_words':nw,'delta_rmse_over_range_percent':100*rmse/dynamic if dynamic else 0,'delta_rmse_over_rms_percent':100*rmse/rms if rms else 0,'bus_lower_bound':2*nw+18+16*((1584*yb+31)//32)}
  record['candidates'].append(result)
 summary['tasks'].append(record)
 print(json.dumps(record),flush=True)
out=Path('/tmp/q12_bandwidth_study_20261113.json');out.write_text(json.dumps(summary,indent=2)+'\n')
print('STUDY_COMPLETE '+str(out),flush=True)
