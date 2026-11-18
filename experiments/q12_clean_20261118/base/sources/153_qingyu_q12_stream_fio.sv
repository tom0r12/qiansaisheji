`timescale 1ns/1ps
`default_nettype none
// Original CPU control endpoint and original memory-bus DMA master boundary.
// New commit words authorize source reads; they never carry source tensor data.
module qingyu_q12_stream_fio #(
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
 output wire shared_cache_clear,
 output reg host_valid,output reg [31:0] host_code
);
 reg pending,wait_pending,response_error;
 reg commit_send_pending,commit_reply_pending;
 reg [31:0] response_data,source_pointer,output_pointer;
 reg [31:0] source_words,task_epoch,commit_epoch_q,available_words;
 reg [31:0] offered_commit_words,offered_commit_epoch;
 reg completed,failed;reg [7:0] failure_code;
 wire engine_ready,engine_busy,engine_done,engine_error;
 wire [7:0] engine_error_code;
 wire [31:0] task_cycles,core_cycles,load_cycles,factor_cycles,cache_cycles,compute_cycles,store_cycles;
 wire engine_commit_ready,engine_commit_rsp_valid,engine_commit_rsp_error;
 wire [3:0] engine_commit_error_code;
 wire selected=icb_cmd_addr[31:8]==24'hf00000 && icb_cmd_addr[1:0]==0;
 wire host_selected=icb_cmd_addr==32'hf0010000;
 wire command_fire=icb_cmd_valid&&icb_cmd_ready;
 wire start_command=command_fire&&!icb_cmd_read&&selected&&icb_cmd_addr[7:0]==8'h04&&
  icb_cmd_wmask==4'hf&&icb_cmd_wdata==1&&engine_ready;
 wire active_error=engine_busy&&engine_error;
 wire [31:0] current_status={16'b0,(active_error?engine_error_code:failure_code),
  4'b0,engine_ready,(failed||active_error),completed,engine_busy};
 wire [31:0] sampled_status=engine_done?
  {16'b0,engine_error_code,4'b0,engine_ready,engine_error,1'b1,1'b0}:current_status;
 assign icb_cmd_ready=rst_n&&!pending;
 assign icb_rsp_valid=rst_n&&pending&&!wait_pending&&!commit_send_pending&&!commit_reply_pending;
 assign icb_rsp_rdata=response_data;
 assign icb_rsp_err=response_error;
 q12_stream_engine_overlap #(.TIMEOUT_CYCLES(ENGINE_TIMEOUT_CYCLES)) engine(
  .clk(clk),.rst_n(rst_n),.start_valid(start_command),.start_ready(engine_ready),
  .start_source(source_pointer),.start_output(output_pointer),
  .start_total_words(source_words),.start_available_words(available_words),.start_epoch(task_epoch),
  .commit_valid(commit_send_pending),.commit_ready(engine_commit_ready),
  .commit_available_words(offered_commit_words),.commit_epoch(offered_commit_epoch),
  .commit_rsp_valid(engine_commit_rsp_valid),.commit_rsp_error(engine_commit_rsp_error),
  .commit_error_code(engine_commit_error_code),
  .busy(engine_busy),.done(engine_done),.error(engine_error),.error_code(engine_error_code),
  .shared_cache_clear(shared_cache_clear),
  .task_cycles(task_cycles),.core_cycles(core_cycles),.core_load_cycles(load_cycles),.core_factor_cycles(factor_cycles),
  .core_cache_cycles(cache_cycles),.core_compute_cycles(compute_cycles),.core_store_cycles(store_cycles),
  .icb_cmd_valid(dma_cmd_valid),.icb_cmd_ready(dma_cmd_ready),.icb_cmd_read(dma_cmd_read),
  .icb_cmd_addr(dma_cmd_addr),.icb_cmd_wdata(dma_cmd_wdata),.icb_cmd_wmask(dma_cmd_wmask),
  .icb_rsp_valid(dma_rsp_valid),.icb_rsp_ready(dma_rsp_ready),.icb_rsp_rdata(dma_rsp_rdata),.icb_rsp_err(dma_rsp_err)
 );
 always @(posedge clk)begin
  if(!rst_n)begin
   pending<=0;wait_pending<=0;response_error<=0;response_data<=0;
   commit_send_pending<=0;commit_reply_pending<=0;offered_commit_words<=0;offered_commit_epoch<=0;
   source_pointer<=0;output_pointer<=0;source_words<=0;task_epoch<=0;commit_epoch_q<=0;available_words<=0;
   completed<=0;failed<=0;failure_code<=0;host_valid<=0;host_code<=0;
  end else begin
   host_valid<=0;
   if(icb_rsp_valid&&icb_rsp_ready)pending<=0;
   if(engine_done)begin completed<=1;failed<=engine_error;failure_code<=engine_error_code;end
   if(pending&&wait_pending&&(!engine_busy||engine_error))begin wait_pending<=0;response_data<=sampled_status;end
   if(commit_send_pending)begin
    if(engine_commit_ready)begin commit_send_pending<=0;commit_reply_pending<=1;end
    else if(!engine_busy || engine_error)begin
     commit_send_pending<=0;response_error<=1;response_data<=32'h000000ff;
    end
   end
   if(commit_reply_pending&&engine_commit_rsp_valid)begin
    commit_reply_pending<=0;response_error<=engine_commit_rsp_error;
    response_data<={28'b0,engine_commit_error_code};
    if(!engine_commit_rsp_error)available_words<=offered_commit_words;
   end
   if(command_fire)begin
    pending<=1;wait_pending<=0;response_error<=0;response_data<=0;
    if(host_selected&&!icb_cmd_read&&icb_cmd_wmask==4'hf)begin host_valid<=1;host_code<=icb_cmd_wdata;end
    else if(!selected)response_error<=1;
    else if(icb_cmd_read)begin
     case(icb_cmd_addr[7:0])
      8'h00:response_data<=32'h51313231;
      8'h08:response_data<=source_pointer;
      8'h0c:response_data<=output_pointer;
      8'h10:response_data<=sampled_status;
      8'h14:if(engine_busy&&!engine_error)wait_pending<=1;else response_data<=sampled_status;
      8'h18:response_data<=task_cycles;
      8'h1c:response_data<=core_cycles;
      8'h20:response_data<=load_cycles;
      8'h24:response_data<=factor_cycles;
      8'h28:response_data<=cache_cycles;
      8'h2c:response_data<=compute_cycles;
      8'h30:response_data<=store_cycles;
      8'h34:response_data<=source_words;
      8'h38:response_data<=task_epoch;
      8'h3c:response_data<=available_words;
      8'h40:response_data<=commit_epoch_q;
      default:response_error<=1;
     endcase
    end else if(icb_cmd_wmask!=4'hf)response_error<=1;
    else begin
     case(icb_cmd_addr[7:0])
      8'h04:begin
       if(start_command)begin completed<=0;failed<=0;failure_code<=0;end
       else if(icb_cmd_wdata==2&&!engine_busy)begin completed<=0;failed<=0;failure_code<=0;end
       else response_error<=1;
      end
      8'h08:if(engine_busy)response_error<=1;else source_pointer<=icb_cmd_wdata;
      8'h0c:if(engine_busy)response_error<=1;else output_pointer<=icb_cmd_wdata;
      8'h34:if(engine_busy)response_error<=1;else source_words<=icb_cmd_wdata;
      8'h38:if(engine_busy)response_error<=1;else task_epoch<=icb_cmd_wdata;
      8'h40:commit_epoch_q<=icb_cmd_wdata;
      8'h3c:begin
       if(engine_busy)begin
        offered_commit_words<=icb_cmd_wdata;offered_commit_epoch<=commit_epoch_q;commit_send_pending<=1;
       end else if(commit_epoch_q!=task_epoch || icb_cmd_wdata>source_words)response_error<=1;
       else available_words<=icb_cmd_wdata;
      end
      default:response_error<=1;
     endcase
    end
   end
  end
 end
endmodule
`default_nettype wire
