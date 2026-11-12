`timescale 1ns/1ps
`default_nettype none
// 512 KiB in 64 RAMSP4096X16 macros. Writes acknowledge on the same edge
// that asserts the actual macro write enable. Reads remain synchronous.
module qingyu_shared_sram (
 input wire clk, rst_n,
 input wire icb_cmd_valid, output wire icb_cmd_ready,
 input wire icb_cmd_read, input wire [31:0] icb_cmd_addr,
 input wire [31:0] icb_cmd_wdata, input wire [3:0] icb_cmd_wmask,
 output wire icb_rsp_valid, input wire icb_rsp_ready,
 output wire [31:0] icb_rsp_rdata, output wire icb_rsp_err
);
 reg read_pending;
 reg read_error;
 wire good=(icb_cmd_addr[31:19]==13'h1400);
 wire accept=icb_cmd_valid && icb_cmd_ready;
 wire [31:0] memory_data;
 assign icb_cmd_ready = rst_n && !read_pending && (icb_cmd_read || icb_rsp_ready);
 assign icb_rsp_valid = rst_n && (read_pending || (icb_cmd_valid && !icb_cmd_read));
 assign icb_rsp_err = read_pending ? read_error : !good;
 // No next transaction is accepted while a read response is pending, so the
 // macro output remains stable for any number of response-stall cycles.
 assign icb_rsp_rdata = read_pending && !read_error ? memory_data : 32'b0;
 qingyu_banked_sram #(.DP(131072),.DW(32)) u_storage(
  .clk(clk),.cs(rst_n && accept && good),.we(!icb_cmd_read),
  .addr(icb_cmd_addr[18:2]),.din(icb_cmd_wdata),.wem(icb_cmd_wmask),.dout(memory_data)
 );
 always @(posedge clk) begin
  if(!rst_n) begin read_pending<=0;read_error<=0;end
  else begin
   if(read_pending && icb_rsp_ready) read_pending<=0;
   if(accept && icb_cmd_read) begin
    read_pending<=1;read_error<=!good;
   end
  end
 end
endmodule
`default_nettype wire
