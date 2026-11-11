`timescale 1ns/1ps
module tb_h1500_transfer;
 reg clk=0,rst_n=0;
 always #5 clk=~clk;
 reg fv=0, fr=0, accept=0;
 reg [31:0] fa=0,fd=0;
 wire fq,rv,err;
 reg cv=0, cr=1, cra=1;
 reg [31:0] ca=0;
 wire cq,cp,ce; wire [31:0] cdata;
 wire mv,mr,ma; wire [31:0] addr,data; wire [3:0] mask;
 reg mready=0, mvalid=0, merr=0; reg [31:0] result=0;
 qingyu_fio dut(.clk(clk),.rst_n(rst_n),.icb_cmd_valid(fv),.icb_cmd_ready(fq),
  .icb_cmd_read(fr),.icb_cmd_addr(fa),.icb_cmd_wdata(fd),.icb_cmd_wmask(4'hf),
  .icb_rsp_valid(rv),.icb_rsp_ready(accept),.icb_rsp_err(err),
  .cpu_cmd_valid(cv),.cpu_cmd_read(cr),.cpu_cmd_addr(ca),.cpu_cmd_wdata(32'b0),.cpu_cmd_wmask(4'hf),
  .cpu_cmd_ready(cq),.cpu_rsp_ready(cra),.cpu_rsp_valid(cp),.cpu_rsp_err(ce),.cpu_rsp_rdata(cdata),
  .mem_cmd_valid(mv),.mem_cmd_ready(mready),.mem_cmd_read(mr),.mem_cmd_addr(addr),
  .mem_cmd_wdata(data),.mem_cmd_wmask(mask),.mem_rsp_valid(mvalid),.mem_rsp_ready(ma),
  .mem_rsp_rdata(result),.mem_rsp_err(merr));
 task automatic command(input integer portno,input integer dest);
  @(negedge clk);fv=1;fa=portno;fd=dest; #1;
  while(!fq) @(negedge clk);
  @(negedge clk);fv=0;
 endtask
 task automatic reply(input bit bad);
  wait(rv); repeat(3) begin @(negedge clk); if(!rv || err!==bad) $fatal(1,"unstable FIO reply"); end
  accept=1; @(negedge clk);accept=0;
 endtask
 task automatic beat(input bit rd,input integer a,input integer w,input bit bad=0);
  wait(mv);
  repeat(3) begin @(negedge clk);
   if(!mv || mr!==rd || addr!==a || (!rd && (data!==w || mask!=15))) $fatal(1,"bad stalled beat");
  end
  mready=1; @(negedge clk);mready=0;
  repeat(3) @(negedge clk); mvalid=1;merr=bad;result=w;#1;
  if(!ma) $fatal(1,"response not accepted");
  @(negedge clk);mvalid=0;merr=0;
 endtask
 initial begin
  repeat(3) @(negedge clk);rst_n=1;
  command('hf0000084,'ha003fc40);reply(1);
  command('hf0000090,'ha003cea0);reply(1);
  command('hf0000080,'ha0038200);reply(1);
  // CPU explicitly requests one bounded complete input copy; stalls on every beat.
  command('hf0000090,'ha0000000);
  for(integer n=0;n<3168;n++) beat(1,'ha0000000+4*n,(n<<16)|n);
  reply(0);
  // Tile weights are genuinely read from 64 shared rows, not preloaded privately.
  command('hf0000080,'ha0004000);
  for(integer n=0;n<512;n++) beat(1,'ha0004000+512*(n/8)+4*(n%8),0);
  reply(0);
  for(integer n=0;n<16;n++) begin
   command('hf0006000+8*n,n+17);reply(0);
   command('hf0006004+8*n,0);reply(0);
  end
  command('hf0000004,1);reply(0);
  for(integer batch=0;batch<13;batch++) begin
   wait(dut.u_accel.batch_ready[batch%2]);
   // Reject a strided destination whose final row would exceed shared SRAM.
   command(batch%2 ? 'hf0000040 : 'hf000003c,'ha007ffc0);reply(1);
   command(batch%2 ? 'hf0000040 : 'hf000003c,'ha0010000+batch*8192);
   for(integer n=0;n<(batch==12?48:128);n++)
    beat(0,'ha0010000+batch*8192+1024*(n/16)+4*(n%16),17+n%16);
   reply(0);
   command('hf0000020+4*(batch%2),1);reply(0);
  end
  if(dut.u_accel.output_count!=1584) $fatal(1,"wrong output total");
  command('hf0000004,4);reply(0);
  command('hf0000090,'ha0000000);beat(1,'ha0000000,0,1);reply(1);
  command('hf0000080,'ha0004000);beat(1,'ha0004000,0,1);reply(1);
  command('hf0000090,'ha0000000);beat(1,'ha0000000,32'h12345678);
  rst_n=0;@(negedge clk);rst_n=1;#1;
  if(rv || mv || dut.u_accel.busy) $fatal(1,"stale transaction after reset");
  $display("PASS H1500 input copy, full weight tile, strided batch writeback, bounds, stalls, errors, reset, 3-row tail");
  $finish;
 end
 initial begin #10000000; $fatal(1,"timeout");end
endmodule
