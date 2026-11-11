// Macro implementation of qingyu_shared_sram_mp: 512 KiB = 32 banks x 16 KiB,
// each bank 2 x RAMSP4096X16 (same 64 macros as rtl/asic/qingyu_shared_sram.sv).
// Compile instead of the functional qingyu_shared_sram_mp, never alongside it.
// Per bank, the lowest-index requesting port is granted.  A response that the
// master does not take in its first cycle is held in a per-port register,
// because another port may re-access that bank and change the macro output.
module qingyu_shared_sram_mp #(
 parameter integer NP = 5
) (
 input  wire clk, input wire rst_n,
 input  wire [NP-1:0]    cmd_valid,
 output wire [NP-1:0]    cmd_ready,
 input  wire [NP-1:0]    cmd_read,
 input  wire [32*NP-1:0] cmd_addr,
 input  wire [32*NP-1:0] cmd_wdata,
 input  wire [4*NP-1:0]  cmd_wmask,
 output reg  [NP-1:0]    rsp_valid,
 input  wire [NP-1:0]    rsp_ready,
 output wire [32*NP-1:0] rsp_rdata,
 output reg  [NP-1:0]    rsp_err
);
 localparam integer BANKS = 32;
 wire [NP-1:0] good, can, fire;
 wire [4:0] bank [0:NP-1];
 wire [31:0] bank_q [0:BANKS-1];
 genvar p, q, k;
 generate
  for (p=0; p<NP; p=p+1) begin: g_port
   wire [31:0] a = cmd_addr[32*p+:32];
   assign good[p] = a[31:19] == 13'h1400;
   assign bank[p] = a[18:14];
   assign can[p] = !rsp_valid[p] || rsp_ready[p];
   wire [NP-1:0] beaten;
   for (q=0; q<NP; q=q+1) begin: g_q
    if (q < p) begin: hi
     assign beaten[q] = fire[q] && good[q] && good[p] && bank[q]==bank[p];
    end else begin: lo
     assign beaten[q] = 1'b0;
    end
   end
   assign cmd_ready[p] = can[p] && !(|beaten);
   assign fire[p] = cmd_valid[p] && cmd_ready[p];
  end
  for (k=0; k<BANKS; k=k+1) begin: g_bank
   // one-hot grant: accepted access to this bank (at most one by construction)
   reg        sel;
   reg        we;
   reg [11:0] addr;
   reg [31:0] din;
   reg [3:0]  wem;
   integer j;
   always @* begin
    sel=1'b0; we=1'b0; addr=12'b0; din=32'b0; wem=4'b0;
    for (j=NP-1; j>=0; j=j-1)
     if (fire[j] && good[j] && bank[j]==k) begin
      sel=1'b1; we=!cmd_read[j]; addr=cmd_addr[32*j+2+:12];
      din=cmd_wdata[32*j+:32]; wem=cmd_wmask[4*j+:4];
     end
   end
   qingyu_banked_sram #(.DP(4096),.DW(32)) u_bank(
    .clk(clk),.cs(rst_n && sel),.we(we),.addr(addr),.din(din),.wem(wem),.dout(bank_q[k]));
  end
 endgenerate
 reg [4:0] rsp_bank [0:NP-1];
 reg [NP-1:0] rsp_read, hold_v;
 reg [31:0] hold [0:NP-1];
 generate
  for (p=0; p<NP; p=p+1) begin: g_rsp
   assign rsp_rdata[32*p+:32] = hold_v[p] ? hold[p] : (rsp_read[p] ? bank_q[rsp_bank[p]] : 32'b0);
  end
 endgenerate
 integer i;
 always @(posedge clk) begin
  if (!rst_n) begin
   rsp_valid <= 0; rsp_err <= 0; rsp_read <= 0; hold_v <= 0;
  end else begin
   for (i=0; i<NP; i=i+1) begin
    if (rsp_valid[i] && !rsp_ready[i] && !hold_v[i]) begin
     hold_v[i] <= 1'b1;
     hold[i] <= rsp_read[i] ? bank_q[rsp_bank[i]] : 32'b0;
    end
    if (rsp_valid[i] && rsp_ready[i]) begin rsp_valid[i] <= 1'b0; hold_v[i] <= 1'b0; end
    if (fire[i]) begin
     rsp_valid[i] <= 1'b1; rsp_err[i] <= !good[i];
     rsp_read[i] <= good[i] && cmd_read[i]; rsp_bank[i] <= bank[i];
     hold_v[i] <= 1'b0;
    end
   end
  end
 end
endmodule
