`timescale 1ns/1ps
module tb_task_inout_repro;
 reg clk=0;always #5 clk=~clk;
 reg [7:0] value=8'ha5;reg [3:0] amount=8;
 wire [15:0] payload;wire [7:0] count;
 task_inout_repro dut(.clk,.value,.amount,.payload,.count);
 integer i;
 initial begin
  for(i=0;i<10;i=i+1)begin
   @(posedge clk);#1;
   if(payload!=={value,8'b0}||count!=={4'b0,amount})begin
    $display("REPRO mismatch payload=%h expected=%h count=%0d expected=%0d",payload,{value,8'b0},count,amount);
    $fatal(1,"task inout effect lost");
   end
   @(negedge clk);value=value+8'd7;amount=amount==8?4'd1:amount+1'b1;
  end
  $display("PASS task inout minimum repro golden");$finish;
 end
endmodule
