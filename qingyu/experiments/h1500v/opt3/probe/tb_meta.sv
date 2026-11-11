`timescale 1ns/1ps
// Standalone FIO + accel metadata gather test: no E203, no output copies.
module tb_meta;
 reg clk=0, rst_n=0;
 always #5 clk=~clk;

 reg  valid=0, read_cmd=0, ready_rsp=0;
 reg  [31:0] address=0, data=0;
 reg  [3:0]  mask=4'hf;
 wire ready_cmd, valid_rsp, error_rsp, host_valid;
 wire [31:0] result, host_code;

 wire mem_cmd_valid, mem_cmd_read, mem_rsp_ready;
 wire [31:0] mem_cmd_addr, mem_cmd_wdata;
 wire [3:0] mem_cmd_wmask;
 wire mem_cmd_ready, mem_rsp_valid, mem_rsp_err;
 wire [31:0] mem_rsp_rdata;

 qingyu_fio dut(
  .clk(clk), .rst_n(rst_n),
  .cpu_cmd_valid(1'b0), .cpu_cmd_read(1'b0), .cpu_rsp_ready(1'b0),
  .cpu_cmd_addr(32'b0), .cpu_cmd_wdata(32'b0), .cpu_cmd_wmask(4'b0),
  .cpu_cmd_ready(), .cpu_rsp_valid(), .cpu_rsp_err(),
  .cpu_rsp_rdata(),
  .mem_cmd_valid(mem_cmd_valid), .mem_cmd_read(mem_cmd_read), .mem_rsp_ready(mem_rsp_ready),
  .mem_cmd_addr(mem_cmd_addr), .mem_cmd_wdata(mem_cmd_wdata), .mem_cmd_wmask(mem_cmd_wmask),
  .mem_cmd_ready(mem_cmd_ready), .mem_rsp_valid(mem_rsp_valid), .mem_rsp_err(mem_rsp_err),
  .mem_rsp_rdata(mem_rsp_rdata),
  .icb_cmd_valid(valid), .icb_cmd_ready(ready_cmd), .icb_cmd_read(read_cmd), .icb_cmd_addr(address),
  .icb_cmd_wdata(data), .icb_cmd_wmask(mask), .icb_rsp_valid(valid_rsp), .icb_rsp_ready(ready_rsp),
  .icb_rsp_rdata(result), .icb_rsp_err(error_rsp),
  .host_valid(host_valid), .host_code(host_code));

 qingyu_shared_sram u_shared(
  .clk(clk), .rst_n(rst_n),
  .icb_cmd_valid(mem_cmd_valid), .icb_cmd_ready(mem_cmd_ready),
  .icb_cmd_read(mem_cmd_read), .icb_cmd_addr(mem_cmd_addr),
  .icb_cmd_wdata(mem_cmd_wdata), .icb_cmd_wmask(mem_cmd_wmask),
  .icb_rsp_valid(mem_rsp_valid), .icb_rsp_ready(mem_rsp_ready),
  .icb_rsp_rdata(mem_rsp_rdata), .icb_rsp_err(mem_rsp_err));

 localparam integer BIAS_BASE = 32'h0000c000 >> 2;   // word offsets inside the SRAM
 localparam integer SHIFT_BASE = 32'h0000c800 >> 2;
 reg [63:0] bias [0:255];
 reg [7:0]  shift [0:255];
 integer i, b, t, lane, errors=0, checked=0;

 task automatic transfer(input bit rd, input [31:0] addr, input [31:0] wd,
                         input [3:0] wm, input bit exp_err);
  integer count;
  begin
   @(negedge clk); address=addr; data=wd; mask=wm; read_cmd=rd; valid=1; ready_rsp=0;
   count=0;
   while(!ready_cmd) begin @(negedge clk); count=count+1; if(count>200)$fatal(1,"cmd timeout %h",addr); end
   @(negedge clk); valid=0;
   while(!valid_rsp) begin @(negedge clk); count=count+1; if(count>2000)$fatal(1,"rsp timeout %h",addr); end
   if(error_rsp!==exp_err) $fatal(1,"unexpected error addr=%h err=%b",addr,error_rsp);
   ready_rsp=1; @(negedge clk); ready_rsp=0;
  end
 endtask

 initial begin
  // Program bias/shift into the shared SRAM model.
  for(i=0;i<256;i=i+1) begin
   bias[i] = -64'sd1000000 + i*64'sd12345;
   shift[i] = (i%7==0) ? (i[7:0] % 40) : 8'd0;
  end
  // make some shifts nonzero in every byte position
  shift[46]=1; shift[69]=1; shift[174]=1; shift[192]=1; shift[237]=1; shift[249]=1;
  shift[3]=7; shift[7]=9; shift[63]=11; shift[255]=13;
  for(i=0;i<256;i=i+1) begin
   u_shared.mem[BIAS_BASE+2*i]   = bias[i][31:0];
   u_shared.mem[BIAS_BASE+2*i+1] = bias[i][63:32];
  end
  for(i=0;i<64;i=i+1) begin
   u_shared.mem[SHIFT_BASE+i] = {shift[4*i+3], shift[4*i+2], shift[4*i+1], shift[4*i]};
  end

  repeat(3) @(negedge clk); rst_n=1; repeat(2) @(negedge clk);
  transfer(0, 32'hf00000a4, 32'ha000c800, 4'hf, 0);
  transfer(0, 32'hf00000a8, 32'ha000c000, 4'hf, 0);
  for(t=0;t<16;t=t+1) begin
   transfer(0, 32'hf00000a0, t*16, 4'hf, 0);
   // wait for the gather to finish
   i=0; while(dut.meta_busy && i<4000) begin @(negedge clk); i=i+1; end
   if(dut.meta_busy) $fatal(1,"gather timeout tile %0d",t);
   repeat(2) @(negedge clk);
   for(lane=0;lane<16;lane=lane+1) begin
    b = lane*4;
    checked=checked+1;
    if(dut.u_accel.metadata_ram.mem[b+0] !== bias[t*16+lane][15:0]) begin
     errors=errors+1; $display("tile %0d lane %0d col %0d seg0 got %h want %h",t,lane,t*16+lane,
       dut.u_accel.metadata_ram.mem[b+0], bias[t*16+lane][15:0]);
    end
    if(dut.u_accel.metadata_ram.mem[b+1] !== bias[t*16+lane][31:16]) begin
     errors=errors+1; $display("tile %0d lane %0d col %0d seg1 got %h want %h",t,lane,t*16+lane,
       dut.u_accel.metadata_ram.mem[b+1], bias[t*16+lane][31:16]);
    end
    if(dut.u_accel.metadata_ram.mem[b+2] !== bias[t*16+lane][47:32]) begin
     errors=errors+1; $display("tile %0d lane %0d col %0d seg2 got %h want %h",t,lane,t*16+lane,
       dut.u_accel.metadata_ram.mem[b+2], bias[t*16+lane][47:32]);
    end
    if(dut.u_accel.metadata_ram.mem[b+3] !== {8'b0,shift[t*16+lane]}) begin
     errors=errors+1; $display("tile %0d lane %0d col %0d seg3 got %h want %h",t,lane,t*16+lane,
       dut.u_accel.metadata_ram.mem[b+3], {8'b0,shift[t*16+lane]});
    end
   end
  end
  if(errors) $fatal(1,"META ERRORS=%0d of %0d",errors,checked*4);
  $display("PASS metadata gather: %0d words checked",checked*4);

  // Second phase: overlap the next tile's gather with this tile's START and
  // metadata read (the real schedule), then check what the engine latched.
  errors=0;
  for(t=0;t<16;t=t+1) begin
   transfer(0, 32'hf00000a0, t*16, 4'hf, 0);
   i=0; while(dut.meta_busy && i<4000) begin @(negedge clk); i=i+1; end
   if(dut.meta_busy) $fatal(1,"gather timeout A tile %0d",t);
   transfer(0, 32'hf0000004, 32'h1, 4'hf, 0);
   if(t<15) transfer(0, 32'hf00000a0, (t+1)*16, 4'hf, 0);
   i=0; while(dut.u_accel.engine_state!=3 && i<2000) begin @(negedge clk); i=i+1; end
   if(dut.u_accel.engine_state!=3) $fatal(1,"engine did not reach row init tile %0d st=%0d",t,dut.u_accel.engine_state);
   for(lane=0;lane<16;lane=lane+1) begin
    checked=checked+1;
    if(dut.u_accel.bias[lane] !== bias[t*16+lane][47:0] ||
       dut.u_accel.shift[lane] !== shift[t*16+lane]) begin
     errors=errors+1;
     if(errors<10) $display("START tile %0d lane %0d col %0d acc bias %h/%h shift %h/%h",t,lane,t*16+lane,
       dut.u_accel.bias[lane],bias[t*16+lane],dut.u_accel.shift[lane],shift[t*16+lane]);
    end
   end
   transfer(0, 32'hf0000004, 32'h4, 4'hf, 0);
   i=0; while(dut.u_accel.busy && i<2000) begin @(negedge clk); i=i+1; end
   i=0; while(dut.meta_busy && i<4000) begin @(negedge clk); i=i+1; end
  end
  if(errors) $fatal(1,"START-OVERLAP ERRORS=%0d",errors);
  $display("PASS metadata/START overlap: %0d lanes checked",checked);
  $finish;
 end
 initial begin #2000000; $fatal(1,"global timeout"); end
endmodule
