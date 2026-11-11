// Alternative implementation: 512 KiB shared memory in 64 RAMSP4096X16 macros.
// Compile instead of rtl/qingyu_shared_sram.sv, never alongside it.
module qingyu_shared_sram (
 input wire clk, rst_n,
 input wire icb_cmd_valid, output wire icb_cmd_ready,
 input wire icb_cmd_read, input wire [31:0] icb_cmd_addr,
 input wire [31:0] icb_cmd_wdata, input wire [3:0] icb_cmd_wmask,
 output reg icb_rsp_valid, input wire icb_rsp_ready,
 output wire [31:0] icb_rsp_rdata, output reg icb_rsp_err
);
 wire good=(icb_cmd_addr[31:19]==13'h1400);
 wire accept=icb_cmd_valid && icb_cmd_ready;
 wire [31:0] memory_data;
 reg response_read;
 assign icb_cmd_ready=!icb_rsp_valid || icb_rsp_ready;
 assign icb_rsp_rdata=response_read ? memory_data : 32'b0;
 qingyu_banked_sram #(.DP(131072),.DW(32)) u_storage(
  .clk(clk),.cs(rst_n && accept && good),.we(!icb_cmd_read),
  .addr(icb_cmd_addr[18:2]),.din(icb_cmd_wdata),.wem(icb_cmd_wmask),.dout(memory_data)
 );
 always @(posedge clk) begin
  if(!rst_n) begin icb_rsp_valid<=0;icb_rsp_err<=0;response_read<=0;end
  else begin
   if(icb_rsp_valid && icb_rsp_ready) icb_rsp_valid<=0;
   if(accept) begin
    icb_rsp_valid<=1;icb_rsp_err<=!good;response_read<=good && icb_cmd_read;
   end
  end
 end
endmodule
