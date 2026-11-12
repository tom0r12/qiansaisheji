`timescale 1ns/1ps
// Incremental area/timing boundary for the new accelerator and interfaces.
// CPU-side ports replace the reused E203 only at this assessment boundary.
// The shared SRAM arbitration is real RTL; its 64 physical memory macros
// remain linked and timed. Only those 64 macro areas may be subtracted.
// Wiring/priority matches opt15 qingyu_e203_soc_top; no functional RTL edits.
module qingyu_score_top (
 input wire clk, rst_n,
 input wire sysmem_icb_cmd_valid, sysmem_icb_cmd_read,
 input wire [31:0] sysmem_icb_cmd_addr, sysmem_icb_cmd_wdata,
 input wire [3:0] sysmem_icb_cmd_wmask,
 output wire sysmem_icb_cmd_ready,
 output wire sysmem_icb_rsp_valid, sysmem_icb_rsp_err,
 output wire [31:0] sysmem_icb_rsp_rdata,
 input wire sysmem_icb_rsp_ready,
 input wire sysfio_icb_cmd_valid, sysfio_icb_cmd_read,
 input wire [31:0] sysfio_icb_cmd_addr, sysfio_icb_cmd_wdata,
 input wire [3:0] sysfio_icb_cmd_wmask,
 output wire sysfio_icb_cmd_ready,
 output wire sysfio_icb_rsp_valid, sysfio_icb_rsp_err,
 output wire [31:0] sysfio_icb_rsp_rdata,
 input wire sysfio_icb_rsp_ready,
 output wire qingyu_host_valid,
 output wire [31:0] qingyu_host_code
);
`ifndef QINGYU_BLOCK_COPY
 QINGYU_SCORE_REQUIRES_BLOCK_COPY invalid_configuration();
`endif
 wire block_mem_cmd_valid, block_mem_cmd_ready, block_mem_cmd_read;
 wire [31:0] block_mem_cmd_addr, block_mem_cmd_wdata;
 wire [3:0] block_mem_cmd_wmask;
 wire block_mem_rsp_valid, block_mem_rsp_ready, block_mem_rsp_err;
 wire [31:0] block_mem_rsp_rdata;
 wire cw_cmd_valid, cw_cmd_ready, cw_rsp_valid, cw_rsp_err;
 wire [31:0] cw_cmd_addr, cw_cmd_wdata;
 wire ld_cmd_valid, ld_cmd_ready, ld_rsp_valid, ld_rsp_err;
 wire [31:0] ld_cmd_addr, ld_rsp_rdata;
 wire sr_cmd_valid, sr_cmd_ready, sr_rsp_valid, sr_rsp_err;
 wire [31:0] sr_cmd_addr, sr_rsp_rdata;
 wire sw_cmd_valid, sw_cmd_ready, sw_rsp_valid, sw_rsp_err;
 wire [31:0] sw_cmd_addr, sw_cmd_wdata;
 wire in_cmd_valid, in_cmd_ready, in_rsp_valid, in_rsp_err;
 wire [31:0] in_cmd_addr, in_rsp_rdata;
 wire [191:0] mp_rsp_rdata;
 wire [5:0] mp_rsp_valid, mp_rsp_err, mp_cmd_ready;

 // Port order = bank priority: 0 cw, 1 sw, 2 mem(CPU/block), 3 ld, 4 in, 5 sr.
 qingyu_shared_sram_mp #(.NP(6)) u_shared (
  .clk(clk), .rst_n(rst_n),
  .cmd_valid({sr_cmd_valid, in_cmd_valid, ld_cmd_valid, block_mem_cmd_valid, sw_cmd_valid, cw_cmd_valid}),
  .cmd_ready(mp_cmd_ready),
  .cmd_read({1'b1, 1'b1, 1'b1, block_mem_cmd_read, 1'b0, 1'b0}),
  .cmd_addr({sr_cmd_addr, in_cmd_addr, ld_cmd_addr, block_mem_cmd_addr, sw_cmd_addr, cw_cmd_addr}),
  .cmd_wdata({32'b0, 32'b0, 32'b0, block_mem_cmd_wdata, sw_cmd_wdata, cw_cmd_wdata}),
  .cmd_wmask({4'h0, 4'h0, 4'h0, block_mem_cmd_wmask, 4'hf, 4'hf}),
  .rsp_valid(mp_rsp_valid),
  .rsp_ready({1'b1, 1'b1, 1'b1, block_mem_rsp_ready, 1'b1, 1'b1}),
  .rsp_rdata(mp_rsp_rdata), .rsp_err(mp_rsp_err)
 );
 assign {sr_cmd_ready, in_cmd_ready, ld_cmd_ready, block_mem_cmd_ready, sw_cmd_ready, cw_cmd_ready} = mp_cmd_ready;
 assign {sr_rsp_valid, in_rsp_valid, ld_rsp_valid, block_mem_rsp_valid, sw_rsp_valid, cw_rsp_valid} = mp_rsp_valid;
 assign {sr_rsp_err, in_rsp_err, ld_rsp_err, block_mem_rsp_err, sw_rsp_err, cw_rsp_err} = mp_rsp_err;
 assign sr_rsp_rdata = mp_rsp_rdata[191:160];
 assign in_rsp_rdata = mp_rsp_rdata[159:128];
 assign ld_rsp_rdata = mp_rsp_rdata[127:96];
 assign block_mem_rsp_rdata = mp_rsp_rdata[95:64];

 qingyu_fio u_fio (
  .clk(clk), .rst_n(rst_n),
  .cpu_cmd_valid(sysmem_icb_cmd_valid), .cpu_cmd_ready(sysmem_icb_cmd_ready),
  .cpu_cmd_read(sysmem_icb_cmd_read), .cpu_cmd_addr(sysmem_icb_cmd_addr),
  .cpu_cmd_wdata(sysmem_icb_cmd_wdata), .cpu_cmd_wmask(sysmem_icb_cmd_wmask),
  .cpu_rsp_valid(sysmem_icb_rsp_valid), .cpu_rsp_ready(sysmem_icb_rsp_ready),
  .cpu_rsp_err(sysmem_icb_rsp_err), .cpu_rsp_rdata(sysmem_icb_rsp_rdata),
  .mem_cmd_valid(block_mem_cmd_valid), .mem_cmd_ready(block_mem_cmd_ready),
  .mem_cmd_read(block_mem_cmd_read), .mem_cmd_addr(block_mem_cmd_addr),
  .mem_cmd_wdata(block_mem_cmd_wdata), .mem_cmd_wmask(block_mem_cmd_wmask),
  .mem_rsp_valid(block_mem_rsp_valid), .mem_rsp_ready(block_mem_rsp_ready),
  .mem_rsp_err(block_mem_rsp_err), .mem_rsp_rdata(block_mem_rsp_rdata),
  .cw_cmd_valid(cw_cmd_valid), .cw_cmd_ready(cw_cmd_ready),
  .cw_cmd_addr(cw_cmd_addr), .cw_cmd_wdata(cw_cmd_wdata),
  .cw_rsp_valid(cw_rsp_valid), .cw_rsp_err(cw_rsp_err),
  .ld_cmd_valid(ld_cmd_valid), .ld_cmd_ready(ld_cmd_ready), .ld_cmd_addr(ld_cmd_addr),
  .ld_rsp_valid(ld_rsp_valid), .ld_rsp_err(ld_rsp_err), .ld_rsp_rdata(ld_rsp_rdata),
  .sr_cmd_valid(sr_cmd_valid), .sr_cmd_ready(sr_cmd_ready), .sr_cmd_addr(sr_cmd_addr),
  .sr_rsp_valid(sr_rsp_valid), .sr_rsp_err(sr_rsp_err), .sr_rsp_rdata(sr_rsp_rdata),
  .sw_cmd_valid(sw_cmd_valid), .sw_cmd_ready(sw_cmd_ready),
  .sw_cmd_addr(sw_cmd_addr), .sw_cmd_wdata(sw_cmd_wdata),
  .sw_rsp_valid(sw_rsp_valid), .sw_rsp_err(sw_rsp_err),
  .in_cmd_valid(in_cmd_valid), .in_cmd_ready(in_cmd_ready), .in_cmd_addr(in_cmd_addr),
  .in_rsp_valid(in_rsp_valid), .in_rsp_err(in_rsp_err), .in_rsp_rdata(in_rsp_rdata),
  .icb_cmd_valid(sysfio_icb_cmd_valid), .icb_cmd_ready(sysfio_icb_cmd_ready),
  .icb_cmd_read(sysfio_icb_cmd_read), .icb_cmd_addr(sysfio_icb_cmd_addr),
  .icb_cmd_wdata(sysfio_icb_cmd_wdata), .icb_cmd_wmask(sysfio_icb_cmd_wmask),
  .icb_rsp_valid(sysfio_icb_rsp_valid), .icb_rsp_ready(sysfio_icb_rsp_ready),
  .icb_rsp_err(sysfio_icb_rsp_err), .icb_rsp_rdata(sysfio_icb_rsp_rdata),
  .host_valid(qingyu_host_valid), .host_code(qingyu_host_code)
 );
endmodule
