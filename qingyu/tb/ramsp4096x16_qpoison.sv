`timescale 1ns/1ps
// LOCAL FUNCTIONAL STAND-IN ONLY. Not a vendor or timing/power model.
module RAMSP4096X16(input wire CLK,CEN,GWEN,input wire [15:0] WEN,
 input wire [11:0] A,input wire [15:0] D,output reg [15:0] Q,
 input wire [2:0] EMA,input wire [1:0] EMAW,input wire RET1N);
 reg [15:0] mem[0:4095];integer j;
 always @(posedge CLK)if(!CEN)begin
  if(GWEN)Q<=mem[A];
  else begin
   for(j=0;j<16;j=j+1)if(!WEN[j])mem[A][j]<=D[j];
   Q<=16'bx;
  end
 end
endmodule
