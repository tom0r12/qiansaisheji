`timescale 1ns/1ps
`default_nettype none
module qingyu_q12_loader_fio #(
 parameter integer ENGINE_TIMEOUT_CYCLES=2000000
)(
 input wire clk,rst_n,
 input wire icb_cmd_valid,output wire icb_cmd_ready,
 input wire icb_cmd_read,input wire [31:0] icb_cmd_addr,icb_cmd_wdata,
 input wire [3:0] icb_cmd_wmask,
 output wire icb_rsp_valid,input wire icb_rsp_ready,
 output wire [31:0] icb_rsp_rdata,output wire icb_rsp_err,
 output wire dma_cmd_valid,input wire dma_cmd_ready,output wire dma_cmd_read,
 output wire [31:0] dma_cmd_addr,dma_cmd_wdata,output wire [3:0] dma_cmd_wmask,
 input wire dma_rsp_valid,output wire dma_rsp_ready,
 input wire [31:0] dma_rsp_rdata,input wire dma_rsp_err,
 output wire loader_request_valid,input wire loader_request_ready,
 output wire [31:0] loader_request_epoch,output wire [3:0] loader_request_chunk,
 output wire shared_cache_clear,
 output reg host_valid,output reg [31:0] host_code
);

 wire mailbox=icb_cmd_addr[31:4]==28'hf002000;
 reg busy,route_mailbox;
 wire fq,frv,fre,mq,mrv,mre;wire [31:0] frd,mrd;
 wire fv=icb_cmd_valid&&!busy&&!mailbox;
 wire mv=icb_cmd_valid&&!busy&&mailbox;
 assign icb_cmd_ready=rst_n&&!busy&&(mailbox?mq:fq);
 assign icb_rsp_valid=rst_n&&busy&&(route_mailbox?mrv:frv);
 assign icb_rsp_err=route_mailbox?mre:fre;
 assign icb_rsp_rdata=route_mailbox?mrd:frd;
 always @(posedge clk)begin
  if(!rst_n)begin busy<=0;route_mailbox<=0;end
  else begin
   if(icb_rsp_valid&&icb_rsp_ready)busy<=0;
   if(icb_cmd_valid&&icb_cmd_ready)begin busy<=1;route_mailbox<=mailbox;end
  end
 end
 q12_loader_request u_request(.clk(clk),.rst_n(rst_n),
 .icb_cmd_valid(mv),.icb_cmd_ready(mq),.icb_cmd_read(icb_cmd_read),.icb_cmd_addr(icb_cmd_addr),
 .icb_cmd_wdata(icb_cmd_wdata),.icb_cmd_wmask(icb_cmd_wmask),.icb_rsp_valid(mrv),.icb_rsp_err(mre),
 .icb_rsp_ready(icb_rsp_ready&&busy&&route_mailbox),.icb_rsp_rdata(mrd),
 .request_valid(loader_request_valid),.request_ready(loader_request_ready),
 .request_epoch(loader_request_epoch),.request_chunk(loader_request_chunk));
 qingyu_q12_stream_fio #(.ENGINE_TIMEOUT_CYCLES(ENGINE_TIMEOUT_CYCLES)) u_engine_fio(
 .clk(clk),.rst_n(rst_n),.icb_cmd_valid(fv),.icb_cmd_ready(fq),.icb_cmd_read(icb_cmd_read),
 .icb_cmd_addr(icb_cmd_addr),.icb_cmd_wdata(icb_cmd_wdata),.icb_cmd_wmask(icb_cmd_wmask),
 .icb_rsp_valid(frv),.icb_rsp_err(fre),.icb_rsp_rdata(frd),.icb_rsp_ready(icb_rsp_ready&&busy&&!route_mailbox),
 .dma_cmd_valid(dma_cmd_valid),.dma_cmd_read(dma_cmd_read),.dma_cmd_ready(dma_cmd_ready),
 .dma_cmd_addr(dma_cmd_addr),.dma_cmd_wdata(dma_cmd_wdata),.dma_cmd_wmask(dma_cmd_wmask),
 .dma_rsp_valid(dma_rsp_valid),.dma_rsp_ready(dma_rsp_ready),.dma_rsp_err(dma_rsp_err),.dma_rsp_rdata(dma_rsp_rdata),
 .shared_cache_clear(shared_cache_clear),.host_valid(host_valid),.host_code(host_code));
endmodule
`default_nettype wire
