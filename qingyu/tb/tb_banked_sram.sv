`timescale 1ns/1ps
module banked_memory_case #(parameter DP=16384,DW=32,ID=0)(output reg done=0);
 localparam AW=$clog2(DP), MW=DW/8, BANKS=DP/4096;
 reg clk=0,cs=0,we=0;
 reg [AW-1:0] addr=0;
 reg [DW-1:0] din=0;
 reg [MW-1:0] wem=0;
 wire [DW-1:0] dout;
 reg [DW-1:0] expected[0:DP-1];
 integer checks=0,b,i,k,a,n;
 reg [DW-1:0] value,held;
 reg [MW-1:0] mask;
 reg [31:0] rng=32'h86132acb;
 always #5 clk=~clk;
 qingyu_banked_sram #(.DP(DP),.DW(DW)) dut(.*);
 function automatic [31:0] step(input [31:0] x);
  reg [31:0] y;
  begin y=x^(x<<13);y=y^(y>>17);step=y^(y<<5);end
 endfunction
 task automatic write_word(input integer address,input [DW-1:0] data,input [MW-1:0] bytes);
  begin
   @(negedge clk);cs=1;we=1;addr=address;din=data;wem=bytes;
   @(posedge clk);#2;
   for(integer j=0;j<MW;j=j+1) if(bytes[j]) expected[address][8*j+:8]=data[8*j+:8];
  end
 endtask
 task automatic read_word(input integer address);
  begin
   @(negedge clk);cs=1;we=0;addr=address;wem=0;
   @(posedge clk);#2;
   if(dout !== expected[address])
    $fatal(1,"BANKED_READ_FAIL case=%0d addr=%0d expected=%h actual=%h",ID,address,expected[address],dout);
   checks=checks+1;
  end
 endtask
 initial begin
  // Every bank, both address edges; no reliance on zero-filled SRAM.
  for(b=0;b<BANKS;b=b+1) begin
   for(i=0;i<2;i=i+1) begin
    a=b*4096+(i?4095:0);
    for(k=0;k<MW;k=k+1) value[k*8+:8]=(b*17+i*79+k*29);
    write_word(a,value,{MW{1'b1}});
   end
  end
  for(b=0;b<BANKS;b=b+1) begin
   a=b*4096;
   read_word(a);read_word(a+4095);
   // Every byte lane independently; untouched bytes must be retained.
   for(k=0;k<MW;k=k+1) begin
    mask=0;mask[k]=1;value=~expected[a];
    write_word(a,value,mask);read_word(a);read_word(a+4095);
   end
   write_word(a,{DW{1'b1}},{MW{1'b0}});read_word(a);
  end
  // Different banks on successive cycles, then disabled write/read holds.
  for(b=BANKS-1;b>=0;b=b-1) read_word(b*4096);
  held=dout;
  @(negedge clk);cs=0;we=1;addr=DP-1;wem='1;din='0;
  repeat(3) begin @(posedge clk);#2;if(dout !== held) $fatal(1,"disabled memory output changed");end
  read_word(DP-1);
  // Deterministic mixed masks and bank selections against a byte scoreboard.
  for(n=0;n<256;n=n+1) begin
   rng=step(rng);a=(rng%BANKS)*4096;
   rng=step(rng);mask=rng;
   for(k=0;k<MW;k=k+1) begin rng=step(rng);value[8*k+:8]=rng[7:0];end
   write_word(a,value,mask);read_word(a);
  end
  @(negedge clk);cs=0;we=0;
  $display("QINGYU_BANKED_CASE_PASS id=%0d depth=%0d width=%0d macros=%0d reads_checked=%0d",ID,DP,DW,BANKS*(DW/16),checks);
  done=1;
 end
endmodule
module tb_banked_sram;
 wire shared_done,itcm_done,dtcm_done;
 banked_memory_case #(.DP(131072),.DW(32),.ID(0)) shared_case(shared_done);
 banked_memory_case #(.DP(8192),.DW(64),.ID(1)) itcm_case(itcm_done);
 banked_memory_case #(.DP(16384),.DW(32),.ID(2)) dtcm_case(dtcm_done);
 initial begin
  wait(shared_done && itcm_done && dtcm_done);
  $display("QINGYU_BANKED_MEMORY_FUNCTIONAL_PASS: 80 candidate macros; standalone tests only");
  $finish;
 end
 initial begin #1000000;$fatal(1,"banked memory test timed out");end
endmodule
