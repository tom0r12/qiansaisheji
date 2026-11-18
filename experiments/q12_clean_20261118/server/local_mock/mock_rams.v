// LOCAL MOCK ONLY - NOT MANUFACTURER MODELS. Behavioral stand-ins with the
// RAMSP*X16 port list, used solely to exercise the vendor-flow testbench and
// ASIC wrappers locally before the server run with SRAM_Lib_2025 models.
module RAMSP128X16(input CLK,CEN,GWEN,input [15:0] WEN,input [6:0] A,input [15:0] D,output reg [15:0] Q,input [2:0] EMA,input [1:0] EMAW,input RET1N);
 reg [15:0] m[0:127]; integer i;
 always @(posedge CLK) if(!CEN) begin if(!GWEN) begin for(i=0;i<16;i=i+1) if(!WEN[i]) m[A][i]<=D[i]; end else Q<=m[A]; end
endmodule
module RAMSP1024X16(input CLK,CEN,GWEN,input [15:0] WEN,input [9:0] A,input [15:0] D,output reg [15:0] Q,input [2:0] EMA,input [1:0] EMAW,input RET1N);
 reg [15:0] m[0:1023]; integer i;
 always @(posedge CLK) if(!CEN) begin if(!GWEN) begin for(i=0;i<16;i=i+1) if(!WEN[i]) m[A][i]<=D[i]; end else Q<=m[A]; end
endmodule
module RAMSP4096X16(input CLK,CEN,GWEN,input [15:0] WEN,input [11:0] A,input [15:0] D,output reg [15:0] Q,input [2:0] EMA,input [1:0] EMAW,input RET1N);
 reg [15:0] m[0:4095]; integer i;
 always @(posedge CLK) if(!CEN) begin if(!GWEN) begin for(i=0;i<16;i=i+1) if(!WEN[i]) m[A][i]<=D[i]; end else Q<=m[A]; end
endmodule
