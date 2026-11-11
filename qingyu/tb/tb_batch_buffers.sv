`timescale 1ns/1ps
module tb_batch_buffers #(parameter PIPE_MAC=0, READ_AHEAD=0);
 reg clk=0, rst_n=0, valid=0, rd=0;
 reg [15:0] addr=0;
 reg [31:0] data=0;
 reg rsp_ready=1;
 wire ready, rsp, err;
 wire [31:0] rdata;
 always #5 clk=~clk;
 // Two full batches and the same 3-row tail as the production design.
 qingyu_accel #(.ROWS(19),.K(2),.LANES(16),.STREAM_MAC(1),.DOUBLE_BUFFER(1),.PIPE_MAC(PIPE_MAC),.READ_AHEAD(READ_AHEAD)) dut
 (.clk(clk),.rst_n(rst_n),
`ifdef QINGYU_BLOCK_COPY
  .block_pop(1'b0),
`endif
  .icb_cmd_valid(valid),.icb_cmd_ready(ready),
  .icb_cmd_read(rd),.icb_cmd_addr(addr),.icb_cmd_wdata(data),.icb_cmd_wmask(4'hf),
  .icb_rsp_valid(rsp),.icb_rsp_ready(rsp_ready),.icb_rsp_err(err),.icb_rsp_rdata(rdata));
 reg [31:0] got;
 integer input_delta=0;
 task automatic access(input bit read_op,input integer a,input integer d,input bit expect_error=0);
  @(negedge clk);
  valid=1; rd=read_op; addr=a; data=d;
  if (READ_AHEAD && read_op && (a==40 || a==44)) rsp_ready=0;
  #1;
  while (!ready) @(negedge clk);
  @(negedge clk); valid=0;
  while (!rsp) @(negedge clk);
  if(err!==expect_error) $fatal(1,"unexpected response addr=%h error=%b",a,err);
  got=rdata;
  if (!rsp_ready) begin
   repeat(3) begin
    @(negedge clk);
    if (!rsp || err!==expect_error || rdata!==got) $fatal(1,"unstable stalled response");
   end
   rsp_ready=1;
  end
 endtask
 task automatic check_batch(input integer slot,input integer first,input integer rows);
  integer count, wordaddr;
  got=0;
  for(count=0; count<500 && got==0; count++) begin
   access(1,32+4*slot,0);
  end
  if(got!==rows*16) $fatal(1,"bad ready count");
  for(integer r=0;r<rows;r++) for(integer l=0;l<16;l++) begin
   wordaddr=16'h7000+512*slot+4*(16*r+l);
   if (READ_AHEAD && r==0 && l==0) begin
    access(1,wordaddr,0); // Indexed access must not consume the FIFO head.
    if(got!==(first+1+input_delta)*(l+1)+l) $fatal(1,"bad indexed read");
   end
   access(1,READ_AHEAD ? 40+4*slot : wordaddr,0);
   if(got!==(first+r+1+input_delta)*(l+1)+l) $fatal(1,"bad batch row=%d lane=%d",first+r,l);
  end
  if (READ_AHEAD && rows==3) access(1,40+4*slot,0,1);
  if(rows==3) access(1,16'h7000+512*slot+48*4,0,1);
  access(0,32+4*slot,1);
 endtask
 initial begin
  repeat(3) @(negedge clk); rst_n=1;
  for(integer r=0;r<19;r++) access(0,16'h1000+4*r,r+1);
  for(integer l=0;l<16;l+=2) begin
   access(0,16'h5000+2*l,((l+2)<<16)|(l+1));
   access(0,16'h5020+2*l,0);
  end
  for(integer l=0;l<16;l++) begin
   access(0,16'h6000+8*l,l); access(0,16'h6004+8*l,0);
  end
  access(0,4,1); wait(dut.producer_stall);
  repeat(12) @(negedge clk);
  if(dut.batch_ready!==3 || dut.row_index!=16) $fatal(1,"producer overran full slots");
  access(0,4,4); // Software abort while both buffers are owned by the host.
  access(1,32,0); if(got!==0) $fatal(1,"A still ready");
  access(1,36,0); if(got!==0) $fatal(1,"B still ready");
  access(1,16'h7000,0,1);
  for(integer task_id=0; task_id<2; task_id++) begin
   input_delta=task_id*20;
   for(integer r=0;r<19;r++) access(0,16'h1000+4*r,r+1+input_delta);
   access(0,4,3);
   wait(dut.producer_stall);
   check_batch(0,0,8); check_batch(1,8,8); check_batch(0,16,3);
   access(1,28,0); if(got!==304) $fatal(1,"wrong total");
  end
  access(0,4,3); wait(dut.engine_state==dut.E_MAC_CAP);
  @(negedge clk); rst_n=0; @(negedge clk); rst_n=1;
  access(1,8,0); if(got!==0 || dut.batch_ready!==0) $fatal(1,"hardware reset failed");
  if (PIPE_MAC) begin
   // The last product alone overflows a positive 48-bit accumulator.
   access(0,16'h1000,32'h00010001);
   access(0,16'h5000,0); access(0,16'h5020,1);
   access(0,16'h6000,32'hffffffff); access(0,16'h6004,32'h00007fff);
   access(0,4,3); wait(dut.error_flag);
   access(1,20,0);
   if(got!==6 || dut.busy!==0 || dut.batch_ready!==0)
    $fatal(1,"last product overflow was not handled before store");
  end
  $display("PASS batch handoff, full stall, tail bounds, consecutive tiles and reset");
  $finish;
 end
 initial begin #200000; $fatal(1,"timeout"); end
endmodule
