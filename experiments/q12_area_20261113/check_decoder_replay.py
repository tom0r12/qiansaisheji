"""Cycle-exact decoder comparison, canonical vectors and malformed streams."""
from pathlib import Path
import json,random,subprocess,hashlib
here=Path(__file__).resolve().parent
root=here.parents[1];out=here/'variants/decoder_window/checks'
base=root/'final/q12_20261113/vendor/src/q12/decoder2/q12_rice_decoder.sv'
candidate=out.parent/'q12_rice_decoder.sv'
ref=base.read_text().replace('module q12_rice_decoder #','module decoder_reference #')
(out/'reference.sv').write_text(ref)
test=candidate.read_text().replace('unused_shifted=bits << offset;', 'if(offset>320)$fatal(1,"peek domain violated");\n            unused_shifted=bits << offset;')
(out/'checked_candidate.sv').write_text(test)
rng=random.Random(20261113)
rows=[]
for k in (6,9):
 for delta in (0,1):
  for n in (1,2,3,31,32,33,63,64,65,127,128,129,256):
   for mode in range(4):
    vals=[rng.randrange(-2048,2048) if mode==0 else rng.randrange(-16,17) if mode==1 else 0 if mode==2 else (-2048 if i%2 else 2047) for i in range(n)]
    codes=[(v-(vals[i-64] if delta and i>=64 else 0))&4095 for i,v in enumerate(vals)]
    signed=[v-4096 if v&2048 else v for v in codes]
    zz=[(v<<1)^(v>>11) for v in signed]
    bits=''
    for start in range(0,n,32):
     group=zz[start:start+32];raw=sum((u>>k)+1+k for u in group)>=12*len(group)
     bits+=str(int(raw))
     for i,u in enumerate(group):
      bits+=format(codes[start+i],'012b') if raw else '1'*(u>>k)+'0'+format(u&((1<<k)-1),'0%db'%k)
    for corrupt in (0,1):
     payload=bits
     if corrupt:
      pos=rng.randrange(len(bits));payload=bits[:pos]+str(1-int(bits[pos]))+bits[pos+1:]
     encoded=[]
     for i in range(0,len(payload),32):
      word=payload[i:i+32].ljust(32,'0')
      encoded.append(sum(int(word[j:j+8],2)<<(j//8*8)for j in range(0,32,8)))
     index=len(rows);prefix='case%03d'%index
     (out/(prefix+'_input.hex')).write_text(''.join('%08x\n'%v for v in encoded))
     (out/(prefix+'_expected.hex')).write_text(''.join('%03x\n'%(v&4095)for v in vals))
     rows.append((prefix,n,k,delta,len(bits),int(not corrupt)))
(out/'cases.txt').write_text(''.join('%s %d %d %d %d %d\n'%r for r in rows))
ports='''.clk(clk),.rst_n(rst_n),.start_valid(sv),.start_ready(SR),.start_symbols(n),.start_encoded_bits(bits),.start_k(k),.start_delta(delta),.start_row_symbols(9'd64),.in_valid(iv),.in_ready(IR),.in_data(id),.in_valid_bits(ib),.in_last(il),.out_valid(OV),.out_ready(ready),.out_data(OD),.out_count(OC),.out_last(OL),.busy(B),.done(D),.error(E),.total_cycles(T),.consumed_bits(C)'''
def inst(name,module):
 p=ports
 for a,b in [('SR','sr'),('IR','ir'),('OV','ov'),('OD','od'),('OC','oc'),('OL','ol'),('B','b'),('D','d'),('E','e'),('T','t'),('C','c')]:p=p.replace('('+a+')','('+b+name+')')
 return module+' '+name+'('+p+');\n'
tb='''`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg rst_n=0,sv=0,iv=0,il=0,ready=0,delta=0;
reg [15:0] n=0;reg [31:0] bits=0,id=0;reg[3:0] k=0;reg[5:0] ib=0;
wire srr,sra,irr,ira,ovr,ova,olr,ola,br,ba,dr,da,er,ea;
wire[47:0] odr,oda;wire[2:0] ocr,oca;wire[31:0] tr,ta,cr,ca;
''' + inst('r','decoder_reference')+inst('a','q12_rice_decoder')+'''
reg[31:0] input_words[0:4095];reg[11:0] expected[0:1023];
integer fd,status,ni,ki,di,bi,valid_case,cases=0,sent,got,ticks,amount,lane,checks=0,normal=0,malformed=0;
reg[1023:0] prefix;reg take;reg[31:0] rng=32'h9182aa13;
task randomize_next;begin rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);end endtask
initial begin
 fd=$fopen("cases.txt","r");if(!fd)$fatal(1,"cases absent");
 while(!$feof(fd))begin
  status=$fscanf(fd,"%s %d %d %d %d %d\\n",prefix,ni,ki,di,bi,valid_case);
  if(status==6)begin
   $readmemh({$sformatf("%0s",prefix),"_input.hex"},input_words,0,(bi+31)/32-1);
   $readmemh({$sformatf("%0s",prefix),"_expected.hex"},expected,0,ni-1);
   @(negedge clk);rst_n=0;sv=0;iv=0;ready=0;
   repeat(3)@(negedge clk);rst_n=1;n=ni;bits=bi;k=ki;delta=di;sv=1;
   @(negedge clk);sv=0;sent=0;got=0;ticks=0;
   while(!da && ticks<12000)begin
    randomize_next();ready=rng[1:0]!=0;
    iv=sent<(bi+31)/32 && rng[4:2]!=0;
    id=input_words[sent];amount=bi-32*sent;if(amount>32)amount=32;ib=amount;il=(sent+1)*32>=bi;
    @(posedge clk);take=iv&&ira;
    if(ova&&ready)begin
     if(valid_case)for(lane=0;lane<oca;lane=lane+1)begin
      if(got>=ni || oda[lane*12+:12]!==expected[got])$fatal(1,"value case=%0d symbol=%0d",cases,got);
      got=got+1;
     end
    end
    #1;checks=checks+1;
    if({srr,irr,ovr,odr,ocr,olr,br,dr,er,tr,cr}!=={sra,ira,ova,oda,oca,ola,ba,da,ea,ta,ca})$fatal(1,"cycle mismatch case=%0d tick=%0d",cases,ticks);
    if(take)sent=sent+1;ticks=ticks+1;
    @(negedge clk);
   end
   if(ticks>=12000)$fatal(1,"timeout case=%0d",cases);
   if(valid_case&&(ea||got!=ni||ca!=bi))$fatal(1,"completion case=%0d got=%0d n=%0d",cases,got,ni);
   if(valid_case)normal=normal+1;else malformed=malformed+1;
   cases=cases+1;
  end
 end
 $display("PASS decoder lockstep cases=%0d normal=%0d mutated=%0d cycles=%0d",cases,normal,malformed,checks);$finish;
end
endmodule
'''
(out/'tb.sv').write_text(tb)
with (out/'replay_compile.log').open('w') as f:
 subprocess.run(['iverilog','-g2012','-s','tb','-o','decoder_sim','reference.sv','checked_candidate.sv','tb.sv'],cwd=out,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=60)
with (out/'replay.log').open('w') as f:
 subprocess.run(['vvp','decoder_sim'],cwd=out,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)
text=(out/'replay.log').read_text();assert 'PASS decoder lockstep' in text
result={'passed':True,'cases':len(rows),'candidate_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),'summary':text.strip()}
(out/'replay_result.json').write_text(json.dumps(result,indent=2)+'\n');print(text)
