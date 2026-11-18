`timescale 1ns/1ps
`default_nettype none
// ASIC build of the 512 KiB shared SRAM: the identical plain controller
// (qingyu_shared_ctrl, no cache/prefetch) on 64 RAMSP4096X16 macros.
// Compile instead of the behavioral qingyu_shared_sram, never alongside it.
module qingyu_shared_sram (
 input wire clk, rst_n,
 input wire icb_cmd_valid, output wire icb_cmd_ready,
 input wire icb_cmd_read, input wire [31:0] icb_cmd_addr, icb_cmd_wdata,
 input wire [3:0] icb_cmd_wmask,
 output wire icb_rsp_valid, input wire icb_rsp_ready,
 output wire [31:0] icb_rsp_rdata, output wire icb_rsp_err
);
 wire ram_cs, ram_we;
 wire [16:0] ram_addr;
 wire [31:0] ram_wdata, ram_rdata;
 wire [3:0] ram_wmask;
 qingyu_shared_ctrl u_ctrl(
  .clk(clk),.rst_n(rst_n),
  .icb_cmd_valid(icb_cmd_valid),.icb_cmd_ready(icb_cmd_ready),
  .icb_cmd_read(icb_cmd_read),.icb_cmd_addr(icb_cmd_addr),
  .icb_cmd_wdata(icb_cmd_wdata),.icb_cmd_wmask(icb_cmd_wmask),
  .icb_rsp_valid(icb_rsp_valid),.icb_rsp_ready(icb_rsp_ready),
  .icb_rsp_rdata(icb_rsp_rdata),.icb_rsp_err(icb_rsp_err),
  .ram_cs(ram_cs),.ram_we(ram_we),.ram_addr(ram_addr),
  .ram_wdata(ram_wdata),.ram_wmask(ram_wmask),.ram_rdata(ram_rdata)
 );
 qingyu_banked_sram #(.DP(131072),.DW(32)) u_storage(
  .clk(clk),.cs(ram_cs),.we(ram_we),.addr(ram_addr),
  .din(ram_wdata),.wem(ram_wmask),.dout(ram_rdata)
 );
endmodule
`default_nettype wire
