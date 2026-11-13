`default_nettype none
// Synthesizable three-master boundary. s[0]=CPU, s[1]=engine;
// loader is a distinct master, never a replacement for either source.
// All owners use the same bounded response FIFO and unchanged downstream bus.
module q12_loader_bus_merge #(
 parameter integer OUTSTANDING=4
)(
 input wire clk,rst_n,
 input wire [1:0] s_cmd_valid,s_cmd_read,
 output wire [1:0] s_cmd_ready,
 input wire [63:0] s_cmd_addr,s_cmd_wdata,
 input wire [7:0] s_cmd_wmask,
 output wire [1:0] s_rsp_valid,s_rsp_err,
 input wire [1:0] s_rsp_ready,
 output wire [63:0] s_rsp_rdata,
 input wire loader_cmd_valid,loader_cmd_read,
 output wire loader_cmd_ready,
 input wire [31:0] loader_cmd_addr,loader_cmd_wdata,
 input wire [3:0] loader_cmd_wmask,
 output wire loader_rsp_valid,loader_rsp_err,
 input wire loader_rsp_ready,
 output wire [31:0] loader_rsp_rdata,
 output wire m_cmd_valid,m_cmd_read,
 input wire m_cmd_ready,
 output wire [31:0] m_cmd_addr,m_cmd_wdata,
 output wire [3:0] m_cmd_wmask,
 input wire m_rsp_valid,m_rsp_err,
 output wire m_rsp_ready,
 input wire [31:0] m_rsp_rdata
);
 qingyu_icb_merge #(.NP(3),.OUTSTANDING(OUTSTANDING),.ONE_PER_PORT(3'b000)) u_original(
  .clk(clk),.rst_n(rst_n),
  .s_cmd_valid({loader_cmd_valid,s_cmd_valid}),.s_cmd_read({loader_cmd_read,s_cmd_read}),
  .s_cmd_ready({loader_cmd_ready,s_cmd_ready}),
  .s_cmd_addr({loader_cmd_addr,s_cmd_addr}),.s_cmd_wdata({loader_cmd_wdata,s_cmd_wdata}),
  .s_cmd_wmask({loader_cmd_wmask,s_cmd_wmask}),
  .s_rsp_valid({loader_rsp_valid,s_rsp_valid}),.s_rsp_err({loader_rsp_err,s_rsp_err}),
  .s_rsp_ready({loader_rsp_ready,s_rsp_ready}),.s_rsp_rdata({loader_rsp_rdata,s_rsp_rdata}),
  .m_cmd_valid(m_cmd_valid),.m_cmd_ready(m_cmd_ready),.m_cmd_read(m_cmd_read),
  .m_cmd_addr(m_cmd_addr),.m_cmd_wdata(m_cmd_wdata),.m_cmd_wmask(m_cmd_wmask),
  .m_rsp_valid(m_rsp_valid),.m_rsp_ready(m_rsp_ready),.m_rsp_err(m_rsp_err),.m_rsp_rdata(m_rsp_rdata));
endmodule
`default_nettype wire
