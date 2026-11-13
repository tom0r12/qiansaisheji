"""Derived fixed-width-output candidate; original private fixtures stay immutable."""
from pathlib import Path
import hashlib,json,os,re,shutil,signal,struct,subprocess,tempfile,time,sys
import math
from packet_reference import encode,decode,bus_words

H=Path(__file__).resolve().parent
I=json.loads((H/'identity.json').read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def words(p):return [int(s,16)for s in p.read_text().split()]
def hexwords(p,v):p.write_text(''.join('%08x\n'%(int(x)&0xffffffff)for x in v))
def round_even(v,k):
 if k<=0:return v<<(-k)
 q,r=divmod(abs(v),1<<k);q+=r>(1<<(k-1))or(r==(1<<(k-1))and q&1)
 return -q if v<0 else q
for n,h in I['files'].items():assert sha(H/n)==h,n
matches=[p.parent for p in Path('/tmp/q12_final_s4_36usr_20261113').glob('*/manifest.json')if sha(p)==I['baseline_manifest_sha256']]
assert len(matches)==1,matches
B=matches[0];m=read(B/'manifest.json')
for n,h in m['files_sha256'].items():assert sha(B/n)==h,n
O=Path(tempfile.mkdtemp(prefix='q12_c2512_',dir='/tmp'));P=O/'vendor_inputs'
print('Q12_NATIVE_RUN_DIRECTORY='+str(O),flush=True)
shutil.copytree(str(B),str(P))
report={'passed':False,'phase':'prepare','identity':I,'baseline':str(B),'tasks':[]}
def save():write(O/'result.json',report)
save()
try:
 for dest,source in I['overrides'].items():shutil.copy2(str(H/source),str(P/dest))
 fw=sha(P/'firmware64.hex');assert fw==I['firmware_sha256']
 for row in m['tasks']:
  d=P/'tasks'/row['directory'];old=words(B/'tasks'/row['directory']/'input.hex')
  bias=[v-(1<<32)if v&(1<<31)else v for v in old[10:266]]
  shifts=[(v>>s)&255 for v in old[266:330]for s in(0,8,16,24)]
  xw=(old[1]+31)//32;p=330+xw
  xb=struct.pack('<%dI'%xw,*old[330:p]);x=decode(xb,old[1],(99,64),12,6,True)
  weights=[]
  for g in range(8):
   n=old[2+g];nw=(n+31)//32
   weights.append(decode(struct.pack('<%dI'%nw,*old[p:p+nw]),n,(64,32),12,9,False));p+=nw
  assert p==len(old)
  w=[[v for g in weights for v in g[r]]for r in range(64)]
  cols=list(zip(*w))
  refacc=[sum(a*b for a,b in zip(row,col))+bias[c]for row in x for c,col in enumerate(cols)]
  original=[max(-4096,min(4095,round_even(v,shifts[i%256])))for i,v in enumerate(refacc)]
  prior=[v-65536 if v&32768 else v for v in words(B/'tasks'/row['directory']/'dense.hex')]
  assert original==prior,'original direct-reference disagreement'
  # Fixed RNE post-training quantization, no optimization against these samples.
  wq=[[max(-512,min(511,round_even(v,2)))for v in row]for row in w]
  bq=[round_even(v,2)for v in bias];sq=[v-1 for v in shifts];assert min(sq)>=0
  cols=list(zip(*wq));acc=[sum(a*b for a,b in zip(row,col))+bq[c]for row in x for c,col in enumerate(cols)]
  y=[max(-2048,min(2047,round_even(v,sq[i%256])))for i,v in enumerate(acc)]
  packed=[encode([row[g*32:(g+1)*32]for row in wq],12,7,False)for g in range(8)]
  header=[0x31513151,old[1],*[n for b,n in packed],*[v&0xffffffff for v in bq],*[sum(sq[j+k]<<(8*k)for k in range(4))for j in range(0,256,4)]]
  packet=struct.pack('<330I',*header)+xb+b''.join(b for b,n in packed)
  payload=[]
  for tile in range(16):
   vals=[y[r*256+tile*16+c]for r in range(99)for c in range(16)]
   bitstream=sum((v&4095)<<(12*i)for i,v in enumerate(vals))
   payload.append(bitstream.to_bytes(594*4,'little'))
  expected=struct.pack('<17I',0x32443151,*([19008]*16))+b''.join(payload)
  hexwords(d/'input.hex',bus_words(packet));hexwords(d/'expected.hex',bus_words(expected));hexwords(d/'dense.hex',[v&65535 for v in y])
  # Preserve both independent old and new references for reproducibility.
  original_metadata=dict(row)
  row.update(input_words=len(packet)//4,output_actual_write_words=9522,output_allocation_words=9521,
             input_sha256=hashlib.sha256(packet).hexdigest(),output_sha256=hashlib.sha256(expected).hexdigest(),
             dense_sha256=hashlib.sha256(struct.pack('<25344h',*y)).hexdigest(),
             weight_bits=[n for b,n in packed],output_bits=[19008]*16,baseline_task=original_metadata)
  err=[2*a-b for a,b in zip(y,original)]
  dynamic=max(original)-min(original)
  report['tasks'].append({'task':row['task'],'input_words':row['input_words'],'output_writes':9522,'values':len(y),'delta_rmse_over_frozen_range_percent':math.sqrt(sum(v*v for v in err)/len(err))*100/dynamic if dynamic else 0})
 runner=(P/'run_vendor.py').read_text()
 def subst(old,new):
  global runner
  assert old in runner,old;runner=runner.replace(old,new)
 subst("'d3c7f0fdb0e5632afd3e927f199b1ece3f442b0c5d44a21021710cc929785ed1'",repr(fw))
 subst("'q12_x12_w12_y13_h1'","'q12_x12_w10_y12_native'")
 subst('10353','9521')
 # Changed numerical format necessarily changes traffic; retain per-task
 # conservation against the freshly derived packet, and report old deltas.
 subst("   for key in ['reads','writes','cpu_commands','loader_commands','fabric_commands','responses']:\n     if v[key]!=prior[key]:raise ValueError('Vendor/behavioral transaction conservation differs: '+key)",
       "   task['baseline_format_differs']=True\n    task['traffic_delta_from_old_format']={key:v[key]-prior[key]for key in ['reads','writes','cpu_commands','loader_commands','fabric_commands','responses']}")
 subst("{'RAMSP128X16':30,'RAMSP1024X16':6,'RAMSP4096X16':80,'total':116}",
       "{'RAMSP128X16':24,'RAMSP1024X16':6,'RAMSP4096X16':80,'total':110}")
 m['baseline_expected_macro_instances']=m['expected_macro_instances']
 m['expected_macro_instances']={'RAMSP128X16':24,'RAMSP1024X16':6,'RAMSP4096X16':80,'total':110}
 (P/'run_vendor.py').write_text(runner)
 m.update(candidate='x12_w10_y12_native_write_priority',format_version='q12_x12_w10_y12_native',firmware_hex_sha256=fw,
          derived_candidate={'baseline_manifest_sha256':I['baseline_manifest_sha256'],'output_compression':False,'values':25344,'numeric_bits':12,'rounding':'RNE','weight_bits':10,'overrides':I['overrides']})
 m['files_sha256']={n:sha(P/n)for n in m['files_sha256']}
 write(P/'manifest.json',m);report['manifest_sha256']=sha(P/'manifest.json');report['phase']='vendor_simulation';save()
 cmd=[sys.executable,str(P/'run_vendor.py'),'--tasks','12','--saif','--work-root',str(O)]
 with (O/'vendor.log').open('w')as log:
  proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=str(O),start_new_session=True)
  write(O/'process.json',{'pid':proc.pid,'command':cmd})
  try:rc=proc.wait(timeout=18000)
  except BaseException:
   os.killpg(proc.pid,signal.SIGTERM);raise
 assert rc==0,'vendor regression failed; see '+str(O/'vendor.log')
 results=list(O.glob('qingyu_q12_final_vendor_*/result.json'));assert len(results)==1
 v=read(results[0]);assert v['passed']and v['functional_passed']and len(v['tasks'])==12
 expected_cycles=[24560,24708,24725,24689,24686,24533,24710,24646,24802,24652,24778,24759]
 actual_cycles=[t['metrics']['full_window_cycles']for t in v['tasks']]
 assert actual_cycles==expected_cycles,'Storage-only change altered full-window cycles'
 report['cycles_identical_to_native12']=True
 report.update(phase='activity_complete',functional_passed=True,vendor_result=str(results[0]),vendor_result_sha256=sha(results[0]),mean_full_window_cycles=v['mean_full_window_cycles'],conditional_throughput_150mhz=v['throughput_tasks_s_at_assumed_150mhz'])
 report['limits']=['Official random600 float accuracy pending','Same-version full-SoC area, timing, and energy pending','Historical12 functional activity is not final competition score']
 save();print('Q12_NATIVE_ACTIVITY_COMPLETE='+str(O/'result.json'),flush=True)
except BaseException as e:
 report.update(phase='failed',error=str(e));save();raise
