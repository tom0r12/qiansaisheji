`timescale 1ns/1ps
// Qingyu FFN1 accelerator. See docs/engineering_contract.md.
module qingyu_accel #(
    parameter integer ROWS = 99,
    parameter integer K = 64,
    parameter integer LANES = 4,
    parameter integer STREAM_MAC = 0,
    parameter integer DOUBLE_BUFFER = 0,
    parameter integer PIPE_MAC = 0,
    parameter integer READ_AHEAD = 0,
    parameter integer WEIGHT_STREAM = 0,
    parameter integer OUT16 = 0
) (
    input  wire         clk,
    input  wire         rst_n,
`ifdef QINGYU_BLOCK_COPY
    input wire input_write,
    input wire [12:0] input_elem,
    input wire [15:0] input_data,
    // combo4: XPAIR writes the K-pair {input_data_hi,input_data} in one cycle.
    input wire input_pair,
    input wire [15:0] input_data_hi,
    output wire [7:0] block_remaining,
    output wire block_next_valid,
    output wire [31:0] block_next_data,
    input wire block_pop,
    // opt8: FIO write-back engine releases the stream slot it just copied.
    input wire block_release,
    output wire weight_load_ok,
    input wire weight_write,
    input wire [2:0] weight_pair,
    input wire [5:0] weight_k,
    input wire [31:0] weight_word,
    // Block metadata port: one 16-bit metadata word per cycle, written into
    // the single 128x16 metadata RAM.  The FIO only asserts it while the
    // engine is outside its metadata read phase, so no port arbitration is
    // needed.  Address layout is the legacy MMIO layout (lane*4+segment).
    input wire meta_wr_en,
    input wire [5:0] meta_wr_addr,
    input wire [15:0] meta_wr_data,
    output wire meta_read_phase,
    output wire block_valid, block_slot, block_has_row,
    output wire [31:0] block_data,
`endif
    output wire         accel_busy,
    input  wire         icb_cmd_valid,
    output wire         icb_cmd_ready,
    input  wire         icb_cmd_read,
    input  wire [15:0]  icb_cmd_addr,
    input  wire [31:0]  icb_cmd_wdata,
    input  wire [3:0]   icb_cmd_wmask,
    output reg          icb_rsp_valid,
    input  wire         icb_rsp_ready,
    output reg  [31:0]  icb_rsp_rdata,
    output reg          icb_rsp_err
);
 // Protocol fixture only: a deterministic stream, not the arithmetic RTL.
 // 99 rows x 16 INT16 outputs = 792 packed words, in 8-row SRAM batches.
 integer index_q=0,batch_q=0,releases=0,pops=0;
 wire reset_cmd=icb_cmd_valid&&icb_cmd_ready&&!icb_cmd_read&&
                icb_cmd_addr==16'h4&&icb_cmd_wdata[2];
 wire [7:0] batch_size=(batch_q%13==12)?8'd24:8'd64;
 function automatic [31:0] pattern(input integer word_id);
  pattern=32'h5310a987^(32'(word_id)*32'h9e3779b9);
 endfunction
 assign block_remaining=batch_size-8'(index_q);
 assign block_valid=index_q<int'(batch_size);
 assign block_next_valid=index_q+1<int'(batch_size);
 assign block_data=pattern((batch_q/13)*792+(batch_q%13)*64+index_q);
 assign block_next_data=pattern((batch_q/13)*792+(batch_q%13)*64+index_q+1);
 assign block_slot=batch_q%2;
 assign block_has_row=block_remaining>=8;
 assign weight_load_ok=1;
 assign meta_read_phase=0;
 assign accel_busy=0;
 assign icb_cmd_ready=!icb_rsp_valid;
 always @(posedge clk)begin
  if(!rst_n)begin
   index_q<=0;batch_q<=0;releases<=0;pops<=0;
   icb_rsp_valid<=0;icb_rsp_rdata<=0;icb_rsp_err<=0;
  end else begin
   if(icb_rsp_valid&&icb_rsp_ready)icb_rsp_valid<=0;
   if(icb_cmd_valid&&icb_cmd_ready)begin
    icb_rsp_valid<=1;icb_rsp_rdata<=0;icb_rsp_err<=0;
   end
   if(block_pop)begin
    if(!block_valid)$fatal(1,"output popped empty independent stream");
    index_q<=index_q+1;pops<=pops+1;
   end
   if(block_release)begin
    if(index_q!=int'(batch_size))$fatal(1,"output slot released before all words issued");
    index_q<=0;batch_q<=batch_q+1;releases<=releases+1;
   end
   if(reset_cmd)begin index_q<=0;batch_q<=0;releases<=0;pops<=0;end
  end
 end
endmodule
