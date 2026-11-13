"""Standard-library input codec; independent of RTL and scientific runtimes."""
import struct
def bus_words(payload):return list(struct.unpack('<%dI'%(len(payload)//4),payload))
def encode(values,width,k,delta):
 mask=(1<<width)-1;columns=len(values[0]);flat=[]
 for r,row in enumerate(values):
  for c,v in enumerate(row):
   assert -(1<<(width-1))<=v<(1<<(width-1))
   flat.append((v-(values[r-1][c]if delta and r else 0))&mask)
 pieces=[]
 for p in range(0,len(flat),32):
  a=flat[p:p+32];signed=[v-(1<<width)if v&(1<<(width-1))else v for v in a]
  zz=[-2*v-1 if v<0 else 2*v for v in signed]
  coded=['1'*(v>>k)+'0'+format(v&((1<<k)-1),'0%db'%k)for v in zz]
  pieces.append('1'+''.join(format(v,'0%db'%width)for v in a)if sum(map(len,coded))>=len(a)*width else '0'+''.join(coded))
 bits=''.join(pieces);n=len(bits);bits+='0'*((-n)%32)
 return bytes(int(bits[i:i+8],2)for i in range(0,len(bits),8)),n
def decode(payload,nbits,shape,width,k,delta):
 bits=''.join(format(v,'08b')for v in payload);assert '1'not in bits[nbits:]
 bits=bits[:nbits];pos=0;values=[];mask=(1<<width)-1
 def get(n):
  nonlocal pos
  assert pos+n<=nbits
  v=int(bits[pos:pos+n],2)if n else 0;pos+=n;return v
 while len(values)<shape[0]*shape[1]:
  raw=get(1);count=min(32,shape[0]*shape[1]-len(values));cost=0
  for _ in range(count):
   if raw:
    v=get(width);v=v-(1<<width)if v&(1<<(width-1))else v
    z=-2*v-1 if v<0 else 2*v
   else:
    end=bits.index('0',pos);q=end-pos;pos=end+1;assert q<=mask>>k
    z=(q<<k)|get(k);v=-(z+1)//2 if z&1 else z//2
   cost+=(z>>k)+1+k
   if delta:
    v=(v+(values[-shape[1]]if len(values)>=shape[1]else 0))&mask
    v=v-(1<<width)if v&(1<<(width-1))else v
   values.append(v)
  assert bool(raw)==(cost>=count*width)
 assert pos==nbits
 return [values[i:i+shape[1]]for i in range(0,len(values),shape[1])]
