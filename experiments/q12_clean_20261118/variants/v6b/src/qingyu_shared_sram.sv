`timescale 1ns/1ps
`default_nettype none
// Plain single-port shared SRAM controller for the original 32-bit sysmem ICB.
// No read-ahead, prefetch or cache: every architectural access is exactly one
// macro access, issued in its accept cycle.
//  * Writes commit at the accept edge, so their (error-free) response is
//    returned in that same cycle when the bus can take it (posted-write ACK).
//  * Reads return the macro Q one cycle later (registered response).
// cmd_ready depends only on local state (no ready->ready combinational path).
module qingyu_shared_ctrl (
 input wire clk, rst_n,
 input wire icb_cmd_valid, output wire icb_cmd_ready,
 input wire icb_cmd_read, input wire [31:0] icb_cmd_addr, icb_cmd_wdata,
 input wire [3:0] icb_cmd_wmask,
 output wire icb_rsp_valid, input wire icb_rsp_ready,
 output wire [31:0] icb_rsp_rdata, output wire icb_rsp_err,
 output wire ram_cs, ram_we,
 output wire [16:0] ram_addr,
 output wire [31:0] ram_wdata,
 output wire [3:0] ram_wmask,
 input wire [31:0] ram_rdata
);
 wire good = icb_cmd_addr[31:19] == 13'h1400 && icb_cmd_addr[1:0] == 2'b00;
 reg response_pending, response_read, response_error;
 assign icb_cmd_ready = rst_n && !response_pending;
 wire accept = icb_cmd_valid && icb_cmd_ready;
 wire immediate = !icb_cmd_read || !good;
 assign icb_rsp_valid = rst_n && (response_pending || (icb_cmd_valid && icb_cmd_ready && immediate));
 assign icb_rsp_err = response_pending ? response_error : !good;
 assign icb_rsp_rdata = (response_pending && response_read) ? ram_rdata : 32'b0;
 assign ram_cs = accept && good;
 assign ram_we = !icb_cmd_read;
 assign ram_addr = icb_cmd_addr[18:2];
 assign ram_wdata = icb_cmd_wdata;
 assign ram_wmask = icb_cmd_wmask;
 always @(posedge clk) begin
  if (!rst_n) begin response_pending <= 1'b0; response_read <= 1'b0; response_error <= 1'b0; end
  else if (accept) begin
   response_pending <= !immediate || !icb_rsp_ready;
   response_read <= good && icb_cmd_read;
   response_error <= !good;
  end else if (response_pending && icb_rsp_ready) response_pending <= 1'b0;
 end
endmodule
`default_nettype wire

`timescale 1ns/1ps
`default_nettype none
// Simulation storage (behavioral). The ASIC build instantiates the identical
// controller with 64 RAMSP4096X16 macros (qingyu_banked_sram).
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
 reg [31:0] mem [0:131071];
 reg [31:0] ram_q;
 assign ram_rdata = ram_q;
 integer b;
 always @(posedge clk) if (ram_cs) begin
  if (!ram_we) ram_q <= mem[ram_addr];
  else begin
   for (b=0;b<4;b=b+1)
    if (ram_wmask[b]) mem[ram_addr][8*b+:8] <= ram_wdata[8*b+:8];
   ram_q <= 32'bx; // never rely on macro Q retention across writes
  end
 end
endmodule
`default_nettype wire
