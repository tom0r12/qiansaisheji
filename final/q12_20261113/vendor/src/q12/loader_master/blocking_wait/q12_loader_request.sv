`default_nettype none
// Synthesizable CPU request mailbox for an explicit external loading agent.
// It carries no tensor data and observes no CPU/shared-bus transactions.
// BASE+0 ID, +4 epoch, +8 chunk request(1..9), +12 blocking WAIT.
// WAIT returns data=0 only when the queued request is delivered and the
// public loader is ready again; data=1 is a bounded timeout, not success.
// Loader contract holds ready low until the last actual control-write ACK.
// Software still reads shared READY/EPOCH/words after this status is idle.
// A successful chunk-write response means the request was queued, not that
// source data is committed. Firmware must still read real shared READY/ACKs.
module q12_loader_request #(
 parameter [31:0] BASE=32'hf0020000,
 parameter integer WAIT_TIMEOUT_CYCLES=2000000
)(
 input wire clk,rst_n,
 input wire icb_cmd_valid,icb_cmd_read,
 output wire icb_cmd_ready,
 input wire [31:0] icb_cmd_addr,icb_cmd_wdata,
 input wire [3:0] icb_cmd_wmask,
 output wire icb_rsp_valid,icb_rsp_err,
 input wire icb_rsp_ready,
 output wire [31:0] icb_rsp_rdata,
 output reg request_valid,
 input wire request_ready,
 output reg [31:0] request_epoch,
 output reg [3:0] request_chunk
);
 localparam integer CW=(WAIT_TIMEOUT_CYCLES<2)?1:$clog2(WAIT_TIMEOUT_CYCLES+1);
 reg wait_pending;reg [CW-1:0] wait_cycles;
 reg response_valid,response_error;
 reg [31:0] response_data,epoch_q;
 wire selected=icb_cmd_addr[31:4]==BASE[31:4]&&icb_cmd_addr[1:0]==0;
 wire request_full=request_valid&&!request_ready;
 assign icb_cmd_ready=rst_n&&!response_valid&&!wait_pending;
 assign icb_rsp_valid=rst_n&&response_valid;
 assign icb_rsp_err=response_error;
 assign icb_rsp_rdata=response_data;
 always @(posedge clk)begin
  if(!rst_n)begin
   response_valid<=0;response_error<=0;response_data<=0;epoch_q<=0;
   wait_pending<=0;wait_cycles<=0;
   request_valid<=0;request_epoch<=0;request_chunk<=0;
  end else begin
   if(icb_rsp_valid&&icb_rsp_ready)response_valid<=0;
   if(request_valid&&request_ready)request_valid<=0;
   if(wait_pending)begin
    if(!request_valid&&request_ready)begin
     wait_pending<=0;response_valid<=1;response_error<=0;response_data<=0;
    end else if(wait_cycles>=CW'(WAIT_TIMEOUT_CYCLES-1))begin
     wait_pending<=0;response_valid<=1;response_error<=0;response_data<=1;
    end else wait_cycles<=wait_cycles+1'b1;
   end
   if(icb_cmd_valid&&icb_cmd_ready)begin
    response_valid<=1;response_error<=0;response_data<=0;
    if(!selected)response_error<=1;
    else if(icb_cmd_read)begin
     case(icb_cmd_addr[3:0])
      4'h0:response_data<=32'h4c445233;
      4'h4:response_data<=epoch_q;
      4'h8:response_data<={28'b0,request_chunk};
      4'hc:if(request_valid||!request_ready)begin response_valid<=0;wait_pending<=1;wait_cycles<=0;end
      default:response_error<=1;
     endcase
    end else if(icb_cmd_wmask!=4'hf)response_error<=1;
    else begin
     case(icb_cmd_addr[3:0])
      4'h4:if(request_full||icb_cmd_wdata==0)response_error<=1;else epoch_q<=icb_cmd_wdata;
      4'h8:if(request_full||epoch_q==0||icb_cmd_wdata<1||icb_cmd_wdata>9)response_error<=1;
       else begin request_valid<=1;request_epoch<=epoch_q;request_chunk<=icb_cmd_wdata[3:0];end
      default:response_error<=1;
     endcase
    end
   end
  end
 end
endmodule
`default_nettype wire
