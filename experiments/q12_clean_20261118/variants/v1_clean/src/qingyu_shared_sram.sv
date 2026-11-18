`timescale 1ns/1ps
`default_nettype none
// Plain synchronous single-port 512 KiB shared SRAM behind the original 32-bit
// sysmem ICB. No read-ahead, prefetch or cache: every architectural access is
// exactly one memory access. Fully pipelined: one command per cycle, fixed
// one-cycle response latency (macro Q). Behavioral storage for simulation; the
// ASIC build maps the same controller onto 64 RAMSP4096X16 macros.
module qingyu_shared_sram (
 input wire clk, rst_n,
 input wire icb_cmd_valid, output wire icb_cmd_ready,
 input wire icb_cmd_read, input wire [31:0] icb_cmd_addr, icb_cmd_wdata,
 input wire [3:0] icb_cmd_wmask,
 output reg icb_rsp_valid, input wire icb_rsp_ready,
 output wire [31:0] icb_rsp_rdata, output reg icb_rsp_err
);
 wire good = icb_cmd_addr[31:19] == 13'h1400 && icb_cmd_addr[1:0] == 2'b00;
 assign icb_cmd_ready = rst_n && (!icb_rsp_valid || icb_rsp_ready);
 wire accept = icb_cmd_valid && icb_cmd_ready;
 wire ram_cs = accept && good;
 wire ram_we = !icb_cmd_read;
 wire [16:0] ram_addr = icb_cmd_addr[18:2];
 reg response_read;
 reg [31:0] mem [0:131071];
 reg [31:0] ram_q;
 assign icb_rsp_rdata = response_read ? ram_q : 32'b0;
 integer b;
 always @(posedge clk) if (ram_cs) begin
  if (!ram_we) ram_q <= mem[ram_addr];
  else begin
   for (b=0;b<4;b=b+1)
    if (icb_cmd_wmask[b]) mem[ram_addr][8*b+:8] <= icb_cmd_wdata[8*b+:8];
   ram_q <= 32'bx;
  end
 end
 always @(posedge clk) begin
  if (!rst_n) begin icb_rsp_valid <= 1'b0; icb_rsp_err <= 1'b0; response_read <= 1'b0; end
  else begin
   if (icb_rsp_valid && icb_rsp_ready) icb_rsp_valid <= 1'b0;
   if (accept) begin
    icb_rsp_valid <= 1'b1; icb_rsp_err <= !good; response_read <= good && icb_cmd_read;
   end
  end
 end
endmodule
`default_nettype wire
