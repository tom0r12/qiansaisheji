`timescale 1ns/1ps
// Candidate building block for CPU/shared memories; not yet integrated.
// Synchronous reads; byte write enables. Consume dout only after a read.
// No reset/initial contents are promised by a physical SRAM.
module qingyu_banked_sram #(
 parameter integer DP=16384, DW=32, AW=$clog2(DP)
)(
 input wire clk, cs, we,
 input wire [AW-1:0] addr,
 input wire [DW-1:0] din,
 input wire [DW/8-1:0] wem,
 output wire [DW-1:0] dout
);
 localparam integer BANKS=DP/4096;
 localparam integer SLICES=DW/16;
 localparam integer BANK_AW=(BANKS>1)?$clog2(BANKS):1;
 wire [DW-1:0] bank_q [0:BANKS-1];
 reg [BANK_AW-1:0] read_bank;
 wire [BANK_AW-1:0] command_bank=addr >> 12;
 always @(posedge clk)
  if(cs && !we) read_bank<=command_bank;
 assign dout=bank_q[read_bank];
 generate
  if(DP<4096 || DP%4096!=0 || (DP & (DP-1))!=0 ||
     DW%16!=0 || DW<16 || (2**AW)!=DP) begin: invalid
   QINGYU_UNSUPPORTED_BANKED_SRAM invalid_configuration();
  end
  for(genvar b=0;b<BANKS;b=b+1) begin: banks
   wire selected=cs && (command_bank==b);
   for(genvar s=0;s<SLICES;s=s+1) begin: slices
    wire [15:0] write_n={{8{~wem[2*s+1]}},{8{~wem[2*s]}}};
    RAMSP4096X16 macro_ram(
     .CLK(clk), .CEN(~selected), .GWEN(~we), .WEN(write_n),
     .A(addr[11:0]), .D(din[16*s+:16]), .Q(bank_q[b][16*s+:16]),
     .EMA(3'b010), .EMAW(2'b00), .RET1N(1'b1)
    );
   end
  end
 endgenerate
endmodule
