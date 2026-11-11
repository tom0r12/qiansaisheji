// LOCAL ONLY: behavioural stand-ins for the SRAM_Lib_2025 macros (same port
// names), so the macro-level SoC fixture can be exercised with Verilator before
// the server run.  The server always uses the vendor Verilog models instead.
module RAMSP128X16 (input CLK, CEN, GWEN, RET1N, input [15:0] WEN, input [6:0] A,
                    input [15:0] D, input [2:0] EMA, input [1:0] EMAW, output reg [15:0] Q);
 reg [15:0] mem [0:127];
 integer b;
 always @(posedge CLK) if (!CEN) begin
  if (!GWEN) begin for (b=0;b<16;b=b+1) if (!WEN[b]) mem[A][b] <= D[b]; end
  else Q <= mem[A];
 end
endmodule
module RAMSP1024X16 (input CLK, CEN, GWEN, RET1N, input [15:0] WEN, input [9:0] A,
                     input [15:0] D, input [2:0] EMA, input [1:0] EMAW, output reg [15:0] Q);
 reg [15:0] mem [0:1023];
 integer b;
 always @(posedge CLK) if (!CEN) begin
  if (!GWEN) begin for (b=0;b<16;b=b+1) if (!WEN[b]) mem[A][b] <= D[b]; end
  else Q <= mem[A];
 end
endmodule
module RAMSP4096X16 (input CLK, CEN, GWEN, RET1N, input [15:0] WEN, input [11:0] A,
                     input [15:0] D, input [2:0] EMA, input [1:0] EMAW, output reg [15:0] Q);
 reg [15:0] mem [0:4095];
 integer b;
 always @(posedge CLK) if (!CEN) begin
  if (!GWEN) begin for (b=0;b<16;b=b+1) if (!WEN[b]) mem[A][b] <= D[b]; end
  else Q <= mem[A];
 end
endmodule
