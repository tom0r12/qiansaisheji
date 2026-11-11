// Functional model of the project's 512 KiB shared SRAM with NP ICB ports.
// The physical memory is 32 independent 16 KiB banks (2 x RAMSP4096X16 each,
// see rtl/asic/qingyu_shared_sram_mp.sv), word-interleaved: bank = word
// address mod 32, so sequential streams spread over all banks.  Every bank serves one access per
// cycle; ports that address different banks proceed in the same cycle.  On a
// bank conflict the lower port index wins (fixed priority), the others see
// cmd_ready low and retry.  One-cycle response, as the single-port model.
// Not an area/power model.
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
 output reg  [32*NP-1:0] rsp_rdata,
 output reg  [NP-1:0]    rsp_err
);
 reg [31:0] mem [0:131071];
 wire [NP-1:0] good, can, fire;
 wire [4:0] bank [0:NP-1];
 genvar p, q;
 generate
  for (p=0; p<NP; p=p+1) begin: g_port
   wire [31:0] a = cmd_addr[32*p+:32];
   assign good[p] = a[31:19] == (32'hA0000000 >> 19);
   assign bank[p] = a[6:2];
   assign can[p] = !rsp_valid[p] || rsp_ready[p];
   // blocked by an accepted higher-priority access to the same bank
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
 endgenerate
 integer i, b;
 always @(posedge clk) begin
  if (!rst_n) begin
   rsp_valid <= 0; rsp_rdata <= 0; rsp_err <= 0;
  end else begin
   for (i=0; i<NP; i=i+1) begin
    if (rsp_valid[i] && rsp_ready[i]) rsp_valid[i] <= 1'b0;
    if (fire[i]) begin
     rsp_valid[i] <= 1'b1;
     rsp_err[i] <= !good[i];
     rsp_rdata[32*i+:32] <= good[i] && cmd_read[i] ? mem[cmd_addr[32*i+2+:17]] : 32'b0;
     if (good[i] && !cmd_read[i])
      for (b=0; b<4; b=b+1)
       if (cmd_wmask[4*i+b]) mem[cmd_addr[32*i+2+:17]][8*b+:8] <= cmd_wdata[32*i+8*b+:8];
    end
   end
  end
 end
endmodule
