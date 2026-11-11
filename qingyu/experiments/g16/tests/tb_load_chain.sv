`timescale 1ns/1ps
module tb_load_chain #(parameter integer MODE=2);
 reg clk=0, rst_n=0;
 always #5 clk=~clk;
 reg cmd=0, consume=0;
 wire ready,reply,error,mv,mr,rr;
 wire [31:0] addr,data;
 wire [3:0] mask;
 reg random_stalls=0, force_stall=0;
 reg [31:0] rng=32'h97e7c23b;
 reg pending=0, response=0, bad=0;
 reg [31:0] rdata=0;
 wire accept=!force_stall && (!pending || (response && rr)) && (!random_stalls || rng[2]);
 localparam BASE=32'ha0010040, SOURCE=BASE+32'h40000;
 integer issued,completed,fail_at=-1,chained=0;
 reg frozen=0; reg [68:0] last_cmd;
 reg [31:0] tag=32'hcafe0000;
 qingyu_fio dut (
  .clk(clk),.rst_n(rst_n),.icb_cmd_valid(cmd),.icb_cmd_ready(ready),.icb_cmd_read(1'b0),
  .icb_cmd_addr(32'hf0000038),.icb_cmd_wdata(BASE),.icb_cmd_wmask(4'hf),
  .icb_rsp_valid(reply),.icb_rsp_ready(consume),.icb_rsp_err(error),
  .cpu_cmd_valid(1'b0),.cpu_cmd_read(1'b0),.cpu_cmd_addr(32'b0),.cpu_cmd_wdata(32'b0),
  .cpu_cmd_wmask(4'b0),.cpu_rsp_ready(1'b1),
  .mem_cmd_valid(mv),.mem_cmd_ready(accept),.mem_cmd_read(mr),.mem_cmd_addr(addr),
  .mem_cmd_wdata(data),.mem_cmd_wmask(mask),.mem_rsp_valid(response),.mem_rsp_ready(rr),
  .mem_rsp_err(bad),.mem_rsp_rdata(rdata));

 always @(posedge clk) begin
  rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  if(!rst_n) begin
   pending<=0;response<=0;bad<=0;issued<=0;completed<=0;frozen<=0;
  end else begin
   if (frozen && (!mv || {mr,addr,data,mask}!==last_cmd))
    $fatal(1,"stalled command changed mode=%0d beat=%0d",MODE,issued);
   frozen<=mv && !accept;
   last_cmd<={mr,addr,data,mask};
   if (response && rr) begin
    completed<=completed+1;pending<=0;response<=0;
    if (bad && mv) $fatal(1,"successor issued following bad response");
   end else if (pending && !response && (!random_stalls || rng[5])) response<=1;
   if (mv && accept) begin
    if (issued>=32 || (issued>fail_at && fail_at>=0) || mask!=4'hf)
     $fatal(1,"extra/malformed command beat %0d",issued);
    if (mr !== !issued[0] || addr !== ((issued[0]?BASE:SOURCE)+4*(issued/2)))
     $fatal(1,"wrong read flag/address at beat %0d",issued);
    if (issued[0] && data!==(tag+issued/2)) $fatal(1,"wrong write value beat %0d",issued);
    if (response && rr) chained<=chained+1;
    pending<=1;response<=!random_stalls || rng[5];bad<=issued==fail_at;
    rdata<=tag+issued/2;issued<=issued+1;
   end
  end
 end
 task automatic reset;
  @(negedge clk);rst_n=0;cmd=0;consume=0;force_stall=0;
  repeat(2) @(negedge clk);rst_n=1;
  #1;if (reply || mv || pending) $fatal(1,"reset did not flush");
 endtask
 task automatic start;
  @(negedge clk);cmd=1;#1;if (!ready) $fatal(1,"command lost");
  @(negedge clk);cmd=0;
 endtask
 task automatic run(input integer fault,input bit stalls);
  integer expected;
  reset();fail_at=fault;random_stalls=stalls;tag=tag+32'h34a3;start();
  wait(reply);#1;expected=fault<0?32:fault+1;
  if (issued!=expected || completed!=expected || pending || error!==(fault>=0))
   $fatal(1,"wrong completion mode=%0d fault=%0d issued=%0d completed=%0d",MODE,fault,issued,completed);
  repeat(4) begin @(negedge clk);if(!reply || mv) $fatal(1,"reply stall");end
  consume=1;@(negedge clk);consume=0;
 endtask
 initial begin
  run(-1,0);
  if (chained!=(MODE==2?31:MODE==1?15:0)) $fatal(1,"peak chain count %0d",chained);
  for(integer n=0;n<32;n=n+1) run(n,1);
  for(integer n=0;n<16;n=n+1) run(-1,1);
  // Reset on each side of a read/write handoff; next transfer must start from word zero.
  for(integer n=1;n<=4;n=n+1) begin
   reset();fail_at=-1;random_stalls=1;start();wait(dut.phase==n);
   reset();run(-1,1);
  end
  $display("PASS load-chain mode=%0d peak/32 fault placements/16 random blocks/4 reset phases; chained=%0d",MODE,chained);
  $finish;
 end
 initial begin #1000000;$fatal(1,"timeout mode=%0d",MODE);end
endmodule

