`timescale 1ns/1ps
`default_nettype none
// Functional 512 KiB SRAM. Write response and byte write commit on the same
// accepted edge; reads retain synchronous one-cycle latency. Not a PPA model.
module qingyu_shared_sram (
 input wire clk, input wire rst_n,
 input wire icb_cmd_valid, output wire icb_cmd_ready,
 input wire icb_cmd_read, input wire [31:0] icb_cmd_addr,
 input wire [31:0] icb_cmd_wdata, input wire [3:0] icb_cmd_wmask,
 output wire icb_rsp_valid, input wire icb_rsp_ready,
 output wire [31:0] icb_rsp_rdata, output wire icb_rsp_err
);
 reg [31:0] mem [0:131071];
 reg read_pending;
 reg [31:0] read_data;
 reg read_error;
 wire good = icb_cmd_addr[31:19] == 13'h1400;
 wire [16:0] word_index = icb_cmd_addr[18:2];
 // A held write under response backpressure changes no storage. Its command
 // and response handshakes must occur together on the actual memory edge.
 assign icb_cmd_ready = rst_n && !read_pending && (icb_cmd_read || icb_rsp_ready);
 assign icb_rsp_valid = rst_n && (read_pending || (icb_cmd_valid && !icb_cmd_read));
 assign icb_rsp_rdata = read_pending ? read_data : 32'b0;
 assign icb_rsp_err = read_pending ? read_error : !good;
 wire accept = icb_cmd_valid && icb_cmd_ready;
 integer b;
 always @(posedge clk) begin
  if (!rst_n) begin
   read_pending <= 1'b0;
   read_data <= 32'b0;
   read_error <= 1'b0;
  end else begin
   if (read_pending && icb_rsp_ready) read_pending <= 1'b0;
   if (accept && icb_cmd_read) begin
    read_pending <= 1'b1;
    read_error <= !good;
    read_data <= good ? mem[word_index] : 32'b0;
   end
   if (accept && !icb_cmd_read && good)
    for (b=0;b<4;b=b+1)
     if (icb_cmd_wmask[b]) mem[word_index][8*b+:8] <= icb_cmd_wdata[8*b+:8];
  end
 end
endmodule
`default_nettype wire
