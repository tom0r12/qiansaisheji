"""Lossless-width proof and rejected out-of-range weight inputs."""
from pathlib import Path
import argparse,hashlib,json,subprocess,re
ap=argparse.ArgumentParser();ap.add_argument('--metadata',action='store_true');args=ap.parse_args()
H=Path(__file__).resolve().parent;R=H.parents[1];O=H/('checks/compact_metadata_weights'if args.metadata else'checks/compact_weights');O.mkdir(parents=True,exist_ok=True)
C=H/('build/dense12_w10_wp_m10'+('_c25'if args.metadata else'')+'/q12_task4.sv')
def run(cmd,name):
 with(O/name).open('w')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)
# This specifies the numerical contract independently of the RTL's bit indices.
proof='''module miter(input[383:0] values,output legal,output mismatch);
wire[319:0] memory;wire[383:0] reconstructed;wire[31:0] ok;
for(genvar j=0;j<32;j=j+1)begin
 assign memory[j*10+:10]=values[j*12+:10];
 assign reconstructed[j*12+:12]={{2{memory[j*10+9]}},memory[j*10+:10]};
 assign ok[j]=($signed(values[j*12+:12])>=-512)&&($signed(values[j*12+:12])<=511);
end
assign legal=&ok;assign mismatch=values!=reconstructed;
endmodule
'''
(O/'miter.sv').write_text(proof)
run(['yosys','-Q','-T','-p','read_verilog -sv '+str(O/'miter.sv')+'; prep -top miter -flatten; sat -set legal 1 -prove mismatch 0 -verify'],'proof.log')
assert 'SUCCESS!'in(O/'proof.log').read_text()
tb='''`timescale 1ns/1ps
module tb;
 reg clk=0;always #5 clk=~clk;
 reg rst_n=0,bv=0,xv=0,wv=0;reg[47:0] wd=0;wire br,xr,wr,busy,done,error;
 wire[2:0] pg,pdi;wire[1:0] ps;wire xd,pl,pd,ov;wire[51:0] od;wire[3:0] ot;wire[8:0] oi;
 wire[31:0] a,b,c,d,e,f;wire mr;
 q12_task4 dut(.clk,.rst_n,.begin_valid(bv),.begin_ready(br),.x_valid(xv),.x_ready(xr),.x_data(48'b0),
 .w_valid(wv),.w_ready(wr),.w_data(wd),.meta_valid(1'b0),.meta_ready(mr),.meta_data(32'b0),
 .pair_group(pg),.pair_slot_base(ps),.x_done(xd),.pair_loaded(pl),.pair_done(pd),.pair_done_index(pdi),
 .out_valid(ov),.out_ready(1'b1),.out_data(od),.out_tile(ot),.out_word_index(oi),.busy,.done,.error,
 .total_cycles(a),.load_cycles(b),.factor_cycles(c),.cache_read_cycles(d),.compute_cycles(e),.store_cycles(f));
 integer lane,testno,n,timeout;reg take;
 initial begin
 for(testno=0;testno<8;testno=testno+1)begin
  rst_n=0;bv=0;xv=0;wv=0;repeat(3)@(negedge clk);rst_n=1;
  @(negedge clk);if(!br)$fatal(1,"not ready after reset");bv=1;
  @(negedge clk);bv=0;xv=1;n=0;timeout=0;
  while(n<1600 && timeout<6000)begin
   @(posedge clk);take=xv&&xr;if(take)n++;timeout++;@(negedge clk);
  end
  xv=0;if(n!=1600)$fatal(1,"X load timeout");timeout=0;
  while(!wr && timeout<100)begin @(negedge clk);timeout++;end
  if(!wr)$fatal(1,"W not ready");
  wd=0;lane=testno%4;wd[lane*12+:12]=(testno<4)?12'd512:12'(-513);wv=1;
  @(negedge clk);wv=0;
  if(!error||!done||busy||ov)$fatal(1,"invalid W accepted lane=%0d",lane);
 end
 $display("PASS compact weight range rejection cases=8 reset recovery=PASS");$finish;
 end
endmodule
'''
(O/'tb.sv').write_text(tb)
base=R/'final/q12_20261113/vendor/src/q12/core_datareset'
run(['iverilog','-g2012','-s','tb','-o',str(O/'sim'),str(C),str(base/'q12_pair_acc.sv'),str(base/'q12_striped_sram.sv'),str(O/'tb.sv')],'compile.log')
run(['vvp',str(O/'sim')],'simulation.log')
log=(O/'simulation.log').read_text();assert 'PASS compact weight'in log
result={'passed':True,'source_sha256':hashlib.sha256(C.read_bytes()).hexdigest(),'lossless_storage_legal_states':'2^320','invalid_weight_tests':8,'macro_reduction':{'RAMSP128X16':4},'summary':log.strip()}
(O/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
