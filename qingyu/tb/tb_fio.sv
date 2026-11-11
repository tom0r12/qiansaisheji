`timescale 1ns/1ps
module tb_fio;
 reg clk=0,rst_n=0,valid=0,read_cmd=0,ready_rsp=0;
 reg [31:0] address=0,data=0;
 reg [3:0] mask=4'hf;
 wire ready_cmd,valid_rsp,error_rsp,host_valid;
 wire [31:0] result,host_code;
 integer host_writes=0;
 always #5 clk=~clk;
 qingyu_fio dut(.clk(clk),.rst_n(rst_n),.icb_cmd_valid(valid),
  .icb_cmd_ready(ready_cmd),.icb_cmd_read(read_cmd),.icb_cmd_addr(address),
  .icb_cmd_wdata(data),.icb_cmd_wmask(mask),.icb_rsp_valid(valid_rsp),
  .icb_rsp_ready(ready_rsp),.icb_rsp_rdata(result),.icb_rsp_err(error_rsp),
  .host_valid(host_valid),.host_code(host_code));
 always @(posedge clk) if(host_valid) host_writes=host_writes+1;
 task automatic transfer(input bit rd,input [31:0] addr,input [31:0] wd,
                         input [3:0] wm,input bit exp_err,input [31:0] exp_data);
  reg [31:0] held; reg held_err; integer count;
  begin
   @(negedge clk); address=addr;data=wd;mask=wm;read_cmd=rd;valid=1;ready_rsp=0;
   count=0;
   while(!ready_cmd) begin @(negedge clk);count=count+1;if(count>50)$fatal(1,"command timeout");end
   @(negedge clk);valid=0;
   while(!valid_rsp) begin @(negedge clk);count=count+1;if(count>100)$fatal(1,"response timeout");end
   held=result;held_err=error_rsp;
   if(held_err!==exp_err || (!exp_err && rd && held!==exp_data))
    $fatal(1,"bad response addr=%h error=%b data=%h",addr,held_err,held);
   repeat(3) begin
    @(negedge clk);
    if(!valid_rsp || result!==held || error_rsp!==held_err || ready_cmd)
     $fatal(1,"response changed under backpressure");
   end
   ready_rsp=1;@(negedge clk);ready_rsp=0;
  end
 endtask
 initial begin
  repeat(3)@(negedge clk);rst_n=1;
  transfer(1,32'hf0000000,0,4'hf,0,32'h51590001);
  transfer(0,32'hf0010000,32'h13572468,4'hf,0,0);
  transfer(1,32'hf0010000,0,4'hf,0,32'h13572468);
  transfer(0,32'hf0010000,32'hdeadbeef,4'h3,1,0);
  transfer(1,32'hf0010000,0,4'hf,0,32'h13572468);
  transfer(1,32'hf0020000,0,4'hf,1,0);
  if(host_writes!=1) $fatal(1,"host side effect on rejected write");
  $display("PASS FIO ownership, stalled responses, decode, host word masks");$finish;
 end
 initial begin #100000;$fatal(1,"timeout");end
endmodule
