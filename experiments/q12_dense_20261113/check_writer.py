"""Independent fixed-slot, backpressure, restart, reset and framing tests."""
from pathlib import Path
import subprocess,json,hashlib,sys
H=Path(__file__).resolve().parent
O=H/'checks';O.mkdir(exist_ok=True)
tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,sv=0,iv=0,il=0,ready=0;reg[51:0] data=0;
wire sr,ir,ov,ol,busy,done,error;wire[31:0] od,cycles;wire[9:0] words;
q12_dense16_writer dut(clk,rst,sv,sr,iv,ir,data,il,ov,ready,od,ol,busy,done,error,cycles,words);
integer sent,got,ticks,frames=0,checks=0,seed,lane,j;reg take,was_stalled=0;
reg[32:0] held;reg[31:0] rng=32'habc01973;reg[15:0] a,b;
function automatic[12:0] value(input integer n,input integer s);
 value=13'((n*2053+s*997)%8192);
endfunction
function automatic[15:0] expanded(input[12:0] x); expanded={{3{x[12]}},x};endfunction
task random_next;begin rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);end endtask
task start_frame;begin
 @(negedge clk);sv=1;iv=0;ready=0;
 if(!sr)$fatal(1,"start not ready");
 @(negedge clk);sv=0;
end endtask
initial begin
 repeat(3)@(negedge clk);rst=1;
 for(seed=0;seed<12;seed=seed+1)begin
  start_frame();sent=0;got=0;ticks=0;was_stalled=0;
  while(!done && ticks<20000)begin
   random_next();ready=(seed==0)||rng[1:0]!=0;
   // Once offered, retain all input payload under backpressure.
   if(!iv || take)begin
    iv=sent<396 && ((seed==0)||rng[4:2]!=0);
    for(lane=0;lane<4;lane++)data[lane*13+:13]=value(sent*4+lane,seed);
    il=sent==395;
   end
   @(posedge clk);take=iv&&ir;
   if(was_stalled && {ol,od}!==held)$fatal(1,"unstable output");
   was_stalled=ov&&!ready;held={ol,od};
   if(ov&&ready)begin
    a=expanded(value(2*got,seed));b=expanded(value(2*got+1,seed));
    if(od!=={b,a} || ol!==(got==791))$fatal(1,"value/order/last frame=%0d word=%0d",seed,got);
    got++;checks+=2;
   end
   if(take)sent++;
   ticks++;@(negedge clk);
  end
  iv=0;
  if(error||got!=792||words!=792||busy)$fatal(1,"completion");
  if(seed==0 && ticks!=793)$fatal(1,"unexpected full-rate cycles %0d",ticks);
  frames++;
 end
 // A partial frame must be discarded by reset and cannot leak into restart.
 start_frame();iv=1;il=0;data=52'hfffffffffffff;
 @(negedge clk);iv=0;rst=0;
 @(negedge clk);rst=1;if(ov||busy||error)$fatal(1,"reset did not flush");
 // Premature last is an error, never a successful partial matrix.
 start_frame();iv=1;il=1;
 @(negedge clk);iv=0;
 if(!error||!done||ov||busy)$fatal(1,"early last accepted");
 $display("PASS dense writer frames=%0d values=%0d reset+invalid_last=PASS full_rate=1_word_per_cycle",frames,checks);$finish;
end
endmodule
'''
native12='--native12' in sys.argv
width=int(sys.argv[sys.argv.index('--bits')+1])if '--bits'in sys.argv else 12 if native12 else 16
assert width in(10,11,12,13,16)
tag='writer%d'%width
if width!=16:
 module='q12_dense12_writer'if native12 else 'q12_native_writer #(.VALUE_BITS(%d))'%width
 tb=tb.replace('q12_dense16_writer',module).replace('reg[15:0] a,b;','reg[15:0] a,b;reg[31:0] expected_word;integer bitno,symbol;')
 tb=tb.replace("value=13'((n*2053+s*997)%8192);","value=13'(((n*2053+s*997)%%%d)-%d);"%(1<<width,1<<(width-1)))
 tb=tb.replace('a=expanded(value(2*got,seed));b=expanded(value(2*got+1,seed));',
 '''expected_word=0;
    for(bitno=0;bitno<32;bitno++)begin
     symbol=(got*32+bitno)/WIDTH;a=expanded(value(symbol,seed));
     expected_word[bitno]=(symbol<1584)?a[(got*32+bitno)%WIDTH]:1'b0;
    end'''.replace('WIDTH',str(width))).replace('od!=={b,a}','od!==expected_word')
 count=(1584*width+31)//32
 tb=tb.replace('791',str(count-1)).replace('792',str(count)).replace('793',str(count+1)).replace('values=%0d','checked_bus_bits=%0d').replace('checks+=2','checks+=32')
(O/(tag+'_tb.sv')).write_text(tb)
src=H/('rtl/q12_dense12_writer.sv'if native12 else 'rtl/q12_native_writer.sv'if width!=16 else 'rtl/q12_dense16_writer.sv')
for log,cmd in [(tag+'_lint.log',['verilator','--lint-only','-Wall',str(src)]),
                (tag+'_compile.log',['iverilog','-g2012','-s','tb','-o',str(O/(tag+'_sim')),str(src),str(O/(tag+'_tb.sv'))]),
                (tag+'_replay.log',['vvp',str(O/(tag+'_sim'))])]:
 with (O/log).open('w')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
text=(O/(tag+'_replay.log')).read_text();assert 'PASS dense writer' in text
(O/(tag+'_result.json')).write_text(json.dumps({'passed':True,'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'summary':text.strip()},indent=2)+'\n')
print(text)
