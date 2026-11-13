"""Full E203/System Bus regression using explicitly labelled behavioral SRAM.

Synthetic inputs test functionality and traffic, not official competition scores.
Run on Linux/WSL; private official fixtures stay on the contest server.
"""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,struct,re,time
import numpy as np
H=Path(__file__).resolve().parent;R=H.parents[1];B=R/'final/q12_20261113/vendor'
F=R/'final/q12_20261113/freeze_snapshot'
sys.path.insert(0,str(F/'output/eda/q12_candidate/packing'))
sys.path.insert(0,str(F/'output/eda/q12_candidate/reference'))
from rice_words import encode
from packet_io import build_output
from fixed_reference import direct,pair_identity

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd,log,cwd=None,timeout=900):
 with log.open('w')as f:
  subprocess.run(list(map(str,cmd)),cwd=cwd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=timeout)
def hexwords(p,b):p.write_text(''.join('%08x\n'%x for x in struct.unpack('<%dI'%(len(b)//4),b)))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--baseline',action='store_true');ap.add_argument('--cases',type=int,default=12);ap.add_argument('--reuse',action='store_true')
 ap.add_argument('--storage-bits',type=int,choices=(10,11,12,13,16),default=16);ap.add_argument('--weight-bits',type=int,choices=(10,11,12),default=12)
 ap.add_argument('--write-priority',action='store_true');ap.add_argument('--compact-weights',action='store_true');a=ap.parse_args()
 assert not a.compact_weights or (a.storage_bits==12 and a.weight_bits==10 and not a.baseline)
 assert not a.baseline or (a.storage_bits==16 and a.weight_bits==12)
 ybits=a.storage_bits if a.storage_bits!=16 else 13;cut=12-a.weight_bits;outcut=13-ybits
 tilebits=1584*a.storage_bits;tilewords=(tilebits+31)//32;output_words=17+16*tilewords
 magic=0x31443151 if a.storage_bits==16 else 0x32443151 if a.storage_bits==12 else 0x33003151+(a.storage_bits<<16)
 mode='baseline'if a.baseline else 'dense16'if (a.storage_bits==16 and not cut) else 'dense%d_w%d'%(a.storage_bits,a.weight_bits)
 if a.write_priority:mode+='_wp'
 if a.compact_weights:mode+='_m10'
 out=H/'build'/mode;out.mkdir(parents=True,exist_ok=True)
 m=json.loads((B/'manifest.json').read_text());sources=[]
 oldram=F/'qingyu/vendor/e203_hbirdv2/rtl/e203/general/sirv_gnrl_ram.v'
 assert oldram.is_file()
 # "mailbox" is a SystemVerilog keyword. Rename only that private net in
 # the local source snapshot, with no change to ports or logic.
 fio=B/'src/q12/loader_master/soc/qingyu_q12_loader_fio.sv'
 compatible=out/'qingyu_q12_loader_fio.sv'
 compatible.write_text(re.sub(r'\bmailbox\b','mailbox_select',fio.read_text()))
 replace={
 'src/q12/loader_master/soc/qingyu_q12_loader_fio.sv':compatible,
 'src/project/rtl/asic/sirv_gnrl_ram.v':oldram,
 'src/project/experiments/h1500v/opt33_readcache/rtl/asic/qingyu_shared_sram.sv':F/'output/github-qiansaisheji/qingyu/experiments/h1500v/opt33_readcache/rtl/qingyu_shared_sram.sv',
 'src/q12_vendor/tb_q12soc_vendor.sv': B/'evidence/tb_q12soc_behavioral.sv'if a.baseline else H/'tb/tb_dense_behavioral.sv',
 'src/q12/core_datareset/q12_task4.sv':R/'experiments/q12_area_20261113/variants/data_hold/q12_task4.sv',
 'src/q12_vendor/macro_presence.sv':None,
 'src/project/rtl/asic/qingyu_banked_sram.sv':None}
 if not a.baseline:
  replace['src/q12/integration/q12_stream_engine_overlap.sv']=H/'rtl/q12_stream_engine_overlap.sv'
  replace['src/q12/encoder_bounded/q13_rice_encoder.sv']=H/'rtl/q12_dense16_writer.sv'
  if a.storage_bits!=16:
   module='q12_dense12_writer' if a.storage_bits==12 else 'q12_native_writer #(.VALUE_BITS(%d))'%ybits
   engine=(H/'rtl/q12_stream_engine_overlap.sv').read_text().replace('q12_dense16_writer',module).replace('25344',str(tilebits)).replace('3168',str(tilewords*4)).replace('wr_desc_count=792','wr_desc_count=%d'%tilewords).replace('50756',str(output_words*4)).replace('31443151','%08x'%magic)
   engine=engine.replace("decode_weights?4'd9:4'd6","decode_weights?4'd%d:4'd6"%(9-cut))
   (out/'q12_stream_engine_overlap.sv').write_text(engine)
   replace['src/q12/integration/q12_stream_engine_overlap.sv']=out/'q12_stream_engine_overlap.sv'
   replace['src/q12/encoder_bounded/q13_rice_encoder.sv']=H/('rtl/q12_dense12_writer.sv'if a.storage_bits==12 else 'rtl/q12_native_writer.sv')
   limit=1<<(ybits-1)
   core=replace['src/q12/core_datareset/q12_task4.sv'].read_text().replace("32'sd4095","32'sd%d"%(limit-1)).replace("32'sd4096","32'sd%d"%limit).replace("13'hfff","13'h%x"%(limit-1)).replace("13'h1000","13'h%x"%((-limit)&8191))
   if a.compact_weights:
    from compact_weights import transform
    core=transform(core)
   (out/'q12_task4.sv').write_text(core);replace['src/q12/core_datareset/q12_task4.sv']=out/'q12_task4.sv'
   decoder=(R/'experiments/q12_area_20261113/variants/decoder_window/q12_rice_decoder.sv').read_text()
   if cut:
    k=9-cut
    for old,new in [('start_k!=9','start_k!=%d'%k),('k_q==6 ? 63 : 7','k_q==6 ? 63 : %d'%((4095>>k))),
                    ('k_q==6 ? 7 : 10','k_q==6 ? 7 : %d'%(k+1)),('remainder_window[71:63]','remainder_window[71:%d]'%(72-k)),
                    ('quotient<<9','quotient<<%d'%k),('u>>9','u>>%d'%k)]:
     assert old in decoder,old
     decoder=decoder.replace(old,new)
   (out/'q12_rice_decoder.sv').write_text(decoder)
   replace['src/q12/decoder2/q12_rice_decoder.sv']=out/'q12_rice_decoder.sv'
   tb=(H/'tb/tb_dense_behavioral.sv').read_text().replace('12688',str(output_words-1)).replace('12689',str(output_words)).replace('12690',str(output_words+1)).replace('50756',str(output_words*4)).replace('792',str(tilewords)).replace('31443151','%08x'%magic).replace('25344',str(tilebits))
   (out/'tb_dense.sv').write_text(tb);replace['src/q12_vendor/tb_q12soc_vendor.sv']=out/'tb_dense.sv'
 if a.write_priority:
  transport=B/'src/q12/integration/q12_icb_stream_prefix.sv'
  code=transport.read_text();old='read_eligible&&(!write_eligible||prefer_read)';assert code.count(old)==1
  code=code.replace(old,'read_eligible&&!write_eligible')
  (out/'q12_icb_stream_prefix.sv').write_text(code)
  replace['src/q12/integration/q12_icb_stream_prefix.sv']=out/'q12_icb_stream_prefix.sv'
 for s in m['source_order']:
  p=replace.get(s,B/s)
  if p is not None:sources.append(p)
 # Keep the decoder identical for the first uncompressed-output A/B.
 obj=Path('/tmp')/('qingyu_dense_obj_'+mode)
 flags=['--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_q12soc','+define+DISABLE_SV_ASSERTION=1',
        '--Mdir',str(obj),'-o','sim']
 for d in m['include_directories']:flags+=['-I'+str(B/d)]
 identity={'sources':{str(p):sha(p)for p in sources},'flags':flags}
 identity_path=out/'build_identity.json'
 if a.reuse:
  assert json.loads(identity_path.read_text())==identity,'stale executable'
 else:
  run(['verilator',*flags,*sources],out/'compile.log',timeout=900)
  identity_path.write_text(json.dumps(identity,indent=2)+'\n')
 fw=H/'firmware'
 if a.baseline:firmware=B/'firmware64.hex'
 else:
  code=(fw/'soc_main.c').read_text()
  if a.storage_bits!=16:code=code.replace('31443151','%08x'%magic).replace('25344',str(tilebits))
  (out/'soc_main.c').write_text(code)
  run(['riscv64-unknown-elf-gcc','-march=rv32imac','-mabi=ilp32','-misa-spec=2.2','-Os','-ffreestanding','-fno-builtin','-nostdlib','-msmall-data-limit=0','-Wl,--gc-sections','-T',fw/'linker.ld',fw/'startup.S',out/'soc_main.c','-o',out/'dense.elf'],out/'firmware.log')
  subprocess.run(['riscv64-unknown-elf-objcopy','-O','binary',str(out/'dense.elf'),str(out/'dense.bin')],check=True)
  b=(out/'dense.bin').read_bytes();assert len(b)<=65536;b=b.ljust(65536,b'\0')
  firmware=out/'firmware64.hex';firmware.write_text(''.join('%016x\n'%v for v in struct.unpack('<8192Q',b)))
 report={'passed':False,'mode':mode,'scope':'synthetic full SoC; behavioral SRAM; no official throughput or PPA',
         'firmware_sha256':sha(firmware),'tasks':[]}
 for case in range(a.cases):
  rng=np.random.default_rng(20261113+case)
  limit=[32,256,1024,2048][case%4]
  x=rng.integers(-limit,limit,size=(99,64));w=rng.integers(-limit,limit,size=(64,256))
  if case==4:x[:]=0
  if case==8:w[:]=0
  bias=rng.integers(-(1<<20),(1<<20),size=256)
  shifts=np.full(256,[12,14,17,19][case%4],dtype=np.int64)
  reference=direct(x,w,bias,shifts)
  if cut:
   w=np.clip(np.rint(w/(2**cut)),-(1<<(a.weight_bits-1)),(1<<(a.weight_bits-1))-1).astype(np.int64)
   bias=np.rint(bias/(2**cut)).astype(np.int64)
  shifts=shifts-cut+outcut
  y=np.clip(direct(x,w,bias,shifts),-(1<<(ybits-1)),(1<<(ybits-1))-1);pair_identity(x,w,bias)
  xp,xb=encode(x,12,6,True);weights=[encode(w[:,i*32:(i+1)*32],12,9-cut,False)for i in range(8)]
  header=[0x31513151,xb,*[n for _,n in weights],*[int(v)&0xffffffff for v in bias],*[sum(int(shifts[j+k])<<(8*k)for k in range(4))for j in range(0,256,4)]]
  ip=struct.pack('<330I',*header)+xp+b''.join(b for b,n in weights)
  if a.baseline:
   streams=[encode(y[:,i*16:(i+1)*16],13,7,True)for i in range(16)]
   expected=build_output([b for b,n in streams],[n for b,n in streams]);writes=18+sum(len(b)//4 for b,n in streams)
  elif a.storage_bits==16:
   expected=struct.pack('<17I',0x31443151,*([25344]*16))+b''.join(y[:,i*16:(i+1)*16].astype('<i2').tobytes()for i in range(16));writes=12690
  else:
   payload=[]
   for tile in range(16):
    vals=y[:,tile*16:(tile+1)*16].ravel()
    block=sum((int(v)&((1<<ybits)-1))<<(ybits*i)for i,v in enumerate(vals))
    payload.append(block.to_bytes(tilewords*4,'little'))
   expected=struct.pack('<17I',magic,*([tilebits]*16))+b''.join(payload);writes=output_words+1
  t=out/('case%02d'%case);t.mkdir(exist_ok=True);hexwords(t/'input.hex',ip);hexwords(t/'expected.hex',expected)
  cmd=[obj/'sim','+FIRMWARE='+str(firmware),'+INPUT='+str(t/'input.hex'),'+EXPECTED='+str(t/'expected.hex'),'+INPUT_WORDS='+str(len(ip)//4),'+OUTPUT_WORDS='+str(writes),'+LAYER='+str(case),'+OUTPUT_DUMP='+str(t/'actual.hex')]
  run(cmd,t/'simulation.log',timeout=120)
  log=(t/'simulation.log').read_text();assert 'PASS real E203 Q12 cold task' in log
  words=[int(v,16)for v in(t/'actual.hex').read_text().split()]
  actual=struct.pack('<%dI'%len(words),*words);assert actual==expected
  if not a.baseline and a.storage_bits==16:
   stored=np.frombuffer(actual[68:],dtype='<i2').reshape(16,99,16).transpose(1,0,2).reshape(99,256)
   assert np.array_equal(stored,y),'independent complete matrix readback'
  elif not a.baseline:
   stored=np.empty((99,256),dtype=np.int64)
   for row in range(99):
    for col in range(256):
     bit=(row*16+col%16)*ybits;offset=68+(col//16)*tilewords*4+bit//8
     v=(int.from_bytes(actual[offset:offset+3],'little')>>(bit%8))&((1<<ybits)-1)
     stored[row,col]=v-(1<<ybits) if v&(1<<(ybits-1)) else v
   assert np.array_equal(stored,y),'fixed-index native matrix readback'
  cycles=int(re.search(r'full_window_cycles=(\d+)',log)[1])
  report['tasks'].append({'case':case,'cycles':cycles,'input_words':len(ip)//4,'output_writes':writes,'values':25344,'passed':True})
  print(mode,report['tasks'][-1],flush=True)
  (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 report.update(passed=True,mean_cycles=sum(t['cycles']for t in report['tasks'])/len(report['tasks']))
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS',mode,'mean',report['mean_cycles'])
if __name__=='__main__':main()
