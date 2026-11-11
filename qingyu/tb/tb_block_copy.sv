`timescale 1ns/1ps
module tb_block_copy;
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
  command('hf0000038,'ha0000044);reply(1);
  command('hf0000030,'ha0010000);reply(1);
  command('hf0000038,'ha0000040);
  for(integer n=0;n<16;n++) begin
   beat(1,'ha0040040+4*n,n+101);beat(0,'ha0000040+4*n,n+101);
   if(n<15 && rv) $fatal(1,"early command completion");
  end
  reply(0);
  command('hf0000038,'ha0000040);beat(1,'ha0040040,0,1);reply(1);
  command('hf0000038,'ha0000040);beat(1,'ha0040040,321);beat(0,'ha0000040,321,1);reply(1);
  // Hold a CPU SRAM response. The FIO request must not steal it.
  @(negedge clk);cv=1;ca='ha0000100;mready=1;cra=0;
  @(negedge clk);cv=0;mready=0;fv=1;fa='hf0000038;fd='ha0000040;
  mvalid=1;result=456;#1;if(fq || !cp || cdata!=456 || ma) $fatal(1,"owner lost");
  cra=1;@(negedge clk);mvalid=0;#1;if(!fq) $fatal(1,"command did not resume");
  @(negedge clk);fv=0;
  beat(1,'ha0040040,22);
  rst_n=0;@(negedge clk);rst_n=1;#1;if(rv || mv) $fatal(1,"stale transfer after reset");
  $display("PASS CPU block transfer: backpressure, bounds, response ownership, errors and abort");
  $finish;
 end
 initial begin #30000; $fatal(1,"timeout");end
endmodule
