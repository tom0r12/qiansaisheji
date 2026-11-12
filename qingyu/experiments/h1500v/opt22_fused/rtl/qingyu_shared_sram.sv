// Functional shared SRAM. Replace storage mapping with the official macro flow.
// 512 KiB at project integration address 0xA0000000; not an area/power model.
module qingyu_shared_sram (
 input wire clk, input wire rst_n,
 input wire icb_cmd_valid, output wire icb_cmd_ready,
 input wire icb_cmd_read, input wire [31:0] icb_cmd_addr,
 input wire [31:0] icb_cmd_wdata, input wire [3:0] icb_cmd_wmask,
 output reg icb_rsp_valid, input wire icb_rsp_ready,
 output reg [31:0] icb_rsp_rdata, output reg icb_rsp_err
);
 reg [31:0] mem [0:131071];
 wire good = (icb_cmd_addr[31:19] == (32'hA0000000 >> 19));
 wire [16:0] word_index = icb_cmd_addr[18:2];
 assign icb_cmd_ready = !icb_rsp_valid || icb_rsp_ready;
 integer b;
 always @(posedge clk) begin
  if (!rst_n) begin
   icb_rsp_valid <= 0; icb_rsp_rdata <= 0; icb_rsp_err <= 0;
  end else begin
   if (icb_rsp_valid && icb_rsp_ready) icb_rsp_valid <= 0;
   if (icb_cmd_valid && icb_cmd_ready) begin
    icb_rsp_valid <= 1;
    icb_rsp_err <= !good;
    icb_rsp_rdata <= good && icb_cmd_read ? mem[word_index] : 32'b0;
    if (good && !icb_cmd_read)
     for (b=0;b<4;b=b+1)
      if (icb_cmd_wmask[b]) mem[word_index][8*b+:8] <= icb_cmd_wdata[8*b+:8];
   end
  end
 end
endmodule
