`timescale 1ns/1ps
`default_nettype none
// Streaming source-prefix variant. Only published, acknowledged source words may be fetched.
// CPU/MMIO producer verification remains a separate integration layer.
// All external data movement uses this single original-system-bus master port.
module q12_stream_engine_overlap #(
 parameter integer TIMEOUT_CYCLES=2000000
)(
 input wire clk,rst_n,
 input wire start_valid,output wire start_ready,
 input wire [31:0] start_source,start_output,
 input wire [31:0] start_total_words,start_available_words,start_epoch,
 input wire commit_valid,output wire commit_ready,
 input wire [31:0] commit_available_words,commit_epoch,
 output reg commit_rsp_valid,output wire commit_rsp_error,
 output wire [3:0] commit_error_code,
 output wire busy,output reg done,error,output reg [7:0] error_code,
 output reg shared_cache_clear,
 output reg [31:0] task_cycles,
 output wire [31:0] core_cycles,core_load_cycles,core_factor_cycles,
 output wire [31:0] core_cache_cycles,core_compute_cycles,core_store_cycles,
 output wire icb_cmd_valid,input wire icb_cmd_ready,
 output wire icb_cmd_read,output wire [31:0] icb_cmd_addr,icb_cmd_wdata,
 output wire [3:0] icb_cmd_wmask,
 input wire icb_rsp_valid,output wire icb_rsp_ready,
 input wire [31:0] icb_rsp_rdata,input wire icb_rsp_err
);
 localparam [5:0] IDLE=0,BEGIN_CORE=1,HEADER_REQ=2,HEADER_RUN=3,LAYOUT=4,
  DECODE_START=5,DECODE_REQ=6,DECODE_RUN=7,BIAS_REQ=8,BIAS_RUN=9,
  SHIFT_REQ=10,SHIFT_RUN=11,FORMAT_START=12,OUTPUT_REQ=13,OUTPUT_RUN=14,
  LENGTH_REQ=15,LENGTH_WORD=16,LENGTH_WAIT=17,MAGIC_REQ=18,MAGIC_WORD=19,
  MAGIC_WAIT=20,ABORT_DRAIN=21,INVALIDATE_REQ=22,INVALIDATE_WORD=23,INVALIDATE_WAIT=24,
  RUN=25,READ_DONE=26,WAIT_LOAD_DONE=27,FINISH_CLOSE=28;
 reg [5:0] state,read_state,write_state;
 reg load_done;
 reg [31:0] source_base,output_base,x_bits,w_bits[0:7],w_base[0:7];
 reg [34:0] layout_cursor;
 reg [3:0] header_index,layout_index,tile;
 reg [2:0] group;
 reg decode_weights,decoder_started,packer_started;
 reg read_finished,decode_finished,pack_finished,x_finished;
 reg format_finished,write_finished;
 reg [31:0] output_bits;
 reg abort_issued;
 reg [8:0] output_index;
 reg [10:0] packed_index;
 wire transport_busy,transport_draining;
 wire gate_start_ready,gate_active,gate_close_ready,gate_control_error,gate_descriptor_error;
 wire [3:0] gate_control_error_code;
 wire [31:0] gate_source,gate_total,gate_available,gate_epoch;
 wire gated_rd_valid,gated_rd_ready;
 wire [31:0] gated_rd_base,gated_rd_count;
 wire gate_close_valid=(state==FINISH_CLOSE) ||
  (state==ABORT_DRAIN && abort_issued && !transport_busy && !transport_draining);
 wire gate_closed=!gate_active || (gate_close_valid&&gate_close_ready);
 wire start_config_fault=state==BEGIN_CORE && gate_control_error && !gate_active;
 assign commit_rsp_error=commit_rsp_valid && gate_control_error;
 assign commit_error_code=commit_rsp_error ? gate_control_error_code : 4'b0;
 always @(posedge clk)begin
  if(!rst_n)commit_rsp_valid<=0;
  else commit_rsp_valid<=commit_valid&&commit_ready;
 end
 wire pipe_rst_n=rst_n && state!=ABORT_DRAIN;
 wire core_begin_ready,core_busy,core_done,core_error,core_x_done;
 wire core_pair_loaded,core_pair_done;
 wire [2:0] core_group,core_pair_done_index;
 wire [1:0] core_slot;
 wire core_x_ready,core_w_ready,core_meta_ready,core_out_valid;
 wire [51:0] core_out_data;
 wire [3:0] core_out_tile;
 wire [8:0] core_out_index;
 wire decoder_start_ready,decoder_in_ready,decoder_out_valid,decoder_out_last;
 wire [47:0] decoder_out_data;
 wire [31:0] decoder_cycles,decoder_bits;
 wire [2:0] decoder_out_count;
 wire decoder_busy,decoder_done,decoder_error;
 wire pack_start_ready,pack_in_ready,pack_out_valid,pack_out_last;
 wire [47:0] pack_out_data;
 wire [31:0] pack_cycles;
 wire [10:0] pack_out_index;
 wire pack_busy,pack_done,pack_error;
 wire [2:0] pack_error_code;
 wire formatter_start_ready,formatter_in_ready,formatter_out_valid,formatter_out_last;
 wire [31:0] formatter_out_data,formatter_cycles,formatter_bits;
 wire [5:0] formatter_valid_bits;
 wire [9:0] formatter_output_words;
 wire formatter_busy,formatter_done,formatter_error;
 wire rd_desc_ready,rd_word_valid,rd_word_last,rd_done_valid,rd_done_error;
 wire [31:0] rd_word_data;
 wire wr_desc_ready,wr_word_ready,wr_done_valid,wr_done_error;
 reg rd_desc_valid,rd_word_ready,wr_desc_valid,wr_desc_prefix,wr_word_valid,wr_word_last;
 reg [31:0] rd_desc_base,rd_desc_count,wr_desc_base,wr_desc_count,wr_word_data;
 wire decode_transfer=state==RUN && read_state==DECODE_RUN;
 wire format_transfer=state==RUN && write_state==OUTPUT_RUN;
 wire decoding=state==RUN && (read_state==DECODE_START || read_state==DECODE_REQ || read_state==DECODE_RUN);
 wire formatting=state==RUN && (write_state==FORMAT_START || write_state==OUTPUT_REQ || write_state==OUTPUT_RUN);
 wire [31:0] active_bits=decode_weights?w_bits[group]:x_bits;
 wire [31:0] active_base=decode_weights?w_base[group]:source_base+32'd1320;
 wire [31:0] active_words=(active_bits+32'd31)>>5;
 wire decoder_start_valid=state==RUN && read_state==DECODE_START && !decoder_started;
 wire pack_start_valid=state==RUN && read_state==DECODE_START && !packer_started;
 wire formatter_start_valid=state==RUN && write_state==FORMAT_START;
 wire formatter_input=format_transfer && output_index<9'd396 && core_out_valid;
 wire core_out_ready=format_transfer && output_index<9'd396 && formatter_in_ready;
 wire pack_out_ready=decode_transfer && (decode_weights?core_w_ready:core_x_ready);
 wire invalid_core_output=formatter_input && formatter_in_ready && (core_out_tile!=tile || core_out_index!=output_index);
 wire metadata_phase=state==RUN && (read_state==BIAS_RUN || read_state==SHIFT_RUN);
 wire invalid_core_group=((decode_transfer && decode_weights && pack_out_valid && core_w_ready) ||
                          (metadata_phase && rd_word_valid && core_meta_ready)) && core_group!=group;
 wire invalid_pack_output=pack_out_valid && decode_transfer &&
  (pack_out_index!=packed_index || pack_out_last!=(packed_index==(decode_weights?11'd511:11'd1599)));
 wire invalid_formatter_word=format_transfer && formatter_out_valid &&
  (formatter_valid_bits==0 || formatter_valid_bits>32 || (!formatter_out_last && formatter_valid_bits!=32));
 wire header_fault=state==HEADER_RUN && rd_word_valid && rd_word_ready &&
  ((header_index==0 && rd_word_data!=32'h31513151) ||
   (header_index==1 && (rd_word_data==0 || rd_word_data>76230)) ||
   (header_index>=2 && header_index<=9 && (rd_word_data==0 || rd_word_data>24640)));
 wire metadata_bad=state==RUN && read_state==SHIFT_RUN && rd_word_valid && rd_word_ready &&
  (rd_word_data[7:0]>47 || rd_word_data[15:8]>47 || rd_word_data[23:16]>47 || rd_word_data[31:24]>47);
 wire datapath_fault=(decoding && (decoder_error||pack_error)) ||
  (formatting && formatter_error) || core_error || invalid_core_output || invalid_core_group || metadata_bad || header_fault ||
  invalid_pack_output || invalid_formatter_word;
 // Descriptor error completion follows retained-read drain. A concurrent
 // writer failure can otherwise leave that reader blocked behind the core,
 // so observe the real failing response immediately and open the drain path.
 wire transport_fault=(icb_rsp_valid&&icb_rsp_ready&&icb_rsp_err)||
                      (rd_done_valid&&rd_done_error)||(wr_done_valid&&wr_done_error);
 wire expired=busy && task_cycles>=32'(TIMEOUT_CYCLES);
 wire abort_now=busy && state!=ABORT_DRAIN && (datapath_fault||transport_fault||expired||start_config_fault||gate_descriptor_error);
 assign busy=state!=IDLE;
 assign start_ready=rst_n && state==IDLE && !transport_busy && !transport_draining && core_begin_ready && gate_start_ready;
 // Optional internal diagnostics remain visible to the verification hierarchy;
 // they do not control completion, which belongs to the originating bus ACK.
 wire unused_component_telemetry=^{core_busy,core_done,core_pair_loaded,core_pair_done,core_pair_done_index,core_slot,
  decoder_cycles,decoder_bits,decoder_busy,pack_cycles,pack_busy,pack_error_code,formatter_cycles,formatter_busy,formatter_output_words,gate_source,gate_available,gate_epoch};

 q11_commit_gate source_guard(
  .clk(clk),.rst_n(rst_n),.start_valid(start_valid&&start_ready),.start_ready(gate_start_ready),
  .start_source_base(start_source),.start_total_words(start_total_words),
  .start_available_words(start_available_words),.start_epoch(start_epoch),
  .commit_valid(commit_valid),.commit_ready(commit_ready),
  .commit_available_words(commit_available_words),.commit_epoch(commit_epoch),
  .close_valid(gate_close_valid),.close_ready(gate_close_ready),.active(gate_active),
  .source_base(gate_source),.total_words(gate_total),.available_words(gate_available),.epoch(gate_epoch),
  .control_error(gate_control_error),.control_error_code(gate_control_error_code),.descriptor_error(gate_descriptor_error),
  .s_valid(rd_desc_valid),.s_ready(rd_desc_ready),.s_addr(rd_desc_base),.s_words(rd_desc_count),
  .m_valid(gated_rd_valid),.m_ready(gated_rd_ready),.m_addr(gated_rd_base),.m_words(gated_rd_count)
 );
 q12_icb_stream_prefix #(.OUTSTANDING(8),.READ_DEPTH(16),.WRITE_DEPTH(8)) transport(
  .clk(clk),.rst_n(rst_n),.soft_abort(abort_now || (state==ABORT_DRAIN && !abort_issued)),
  .rd_desc_valid(gated_rd_valid),.rd_desc_ready(gated_rd_ready),.rd_desc_base(gated_rd_base),.rd_desc_count(gated_rd_count),
  .rd_word_valid(rd_word_valid),.rd_word_ready(rd_word_ready),.rd_word_data(rd_word_data),.rd_word_last(rd_word_last),
  .rd_done_valid(rd_done_valid),.rd_done_ready(1'b1),.rd_done_error(rd_done_error),
  .wr_desc_valid(wr_desc_valid),.wr_desc_ready(wr_desc_ready),.wr_desc_prefix(wr_desc_prefix),
  .wr_desc_base(wr_desc_base),.wr_desc_count(wr_desc_count),
  .wr_word_valid(wr_word_valid),.wr_word_ready(wr_word_ready),.wr_word_data(wr_word_data),.wr_word_last(wr_word_last),
  .wr_done_valid(wr_done_valid),.wr_done_ready(1'b1),.wr_done_error(wr_done_error),
  .busy(transport_busy),.draining(transport_draining),
  .icb_cmd_valid(icb_cmd_valid),.icb_cmd_ready(icb_cmd_ready),.icb_cmd_read(icb_cmd_read),
  .icb_cmd_addr(icb_cmd_addr),.icb_cmd_wdata(icb_cmd_wdata),.icb_cmd_wmask(icb_cmd_wmask),
  .icb_rsp_valid(icb_rsp_valid),.icb_rsp_ready(icb_rsp_ready),.icb_rsp_rdata(icb_rsp_rdata),.icb_rsp_err(icb_rsp_err)
 );
 q12_rice_decoder decoder(
  .clk(clk),.rst_n(pipe_rst_n),.start_valid(decoder_start_valid),.start_ready(decoder_start_ready),
  .start_symbols(decode_weights?16'd2048:16'd6336),.start_encoded_bits(active_bits),
  .start_k(decode_weights?4'd9:4'd6),.start_delta(!decode_weights),.start_row_symbols(decode_weights?9'd32:9'd64),
  .in_valid(decode_transfer&&rd_word_valid),.in_ready(decoder_in_ready),.in_data(rd_word_data),
  .in_valid_bits(rd_word_last && active_bits[4:0]!=0 ? {1'b0,active_bits[4:0]} : 6'd32),.in_last(rd_word_last),
  .out_valid(decoder_out_valid),.out_ready(pack_in_ready),.out_data(decoder_out_data),
  .out_count(decoder_out_count),.out_last(decoder_out_last),.busy(decoder_busy),.done(decoder_done),.error(decoder_error),
  .total_cycles(decoder_cycles),.consumed_bits(decoder_bits)
 );
 q12_rowpair_pack reorder(
  .clk(clk),.rst_n(pipe_rst_n),.start_valid(pack_start_valid),.start_ready(pack_start_ready),.start_mode_w(decode_weights),
  .in_valid(decoder_out_valid),.in_ready(pack_in_ready),.in_data(decoder_out_data),.in_count(decoder_out_count),
  .in_last(decoder_out_last),.upstream_error(decoder_error),
  .out_valid(pack_out_valid),.out_ready(pack_out_ready),.out_data(pack_out_data),.out_last(pack_out_last),
  .out_word_index(pack_out_index),.busy(pack_busy),.done(pack_done),.error(pack_error),
  .error_code(pack_error_code),.total_cycles(pack_cycles)
 );
 q12_task4 compute(
  .clk(clk),.rst_n(pipe_rst_n),.begin_valid(state==BEGIN_CORE&&gate_active),.begin_ready(core_begin_ready),
  .x_valid(decode_transfer&&!decode_weights&&pack_out_valid),.x_ready(core_x_ready),.x_data(pack_out_data),
  .w_valid(decode_transfer&&decode_weights&&pack_out_valid),.w_ready(core_w_ready),.w_data(pack_out_data),
  .meta_valid(metadata_phase&&rd_word_valid),.meta_ready(core_meta_ready),.meta_data(rd_word_data),
  .pair_group(core_group),.pair_slot_base(core_slot),.x_done(core_x_done),.pair_loaded(core_pair_loaded),
  .pair_done(core_pair_done),.pair_done_index(core_pair_done_index),
  .out_valid(core_out_valid),.out_ready(core_out_ready),.out_data(core_out_data),.out_tile(core_out_tile),.out_word_index(core_out_index),
  .busy(core_busy),.done(core_done),.error(core_error),.total_cycles(core_cycles),.load_cycles(core_load_cycles),
  .factor_cycles(core_factor_cycles),.cache_read_cycles(core_cache_cycles),.compute_cycles(core_compute_cycles),.store_cycles(core_store_cycles)
 );
 q12_dense16_writer formatter(
  .clk(clk),.rst_n(pipe_rst_n),.start_valid(formatter_start_valid),.start_ready(formatter_start_ready),
  .in_valid(formatter_input),.in_ready(formatter_in_ready),.in_data(core_out_data),.in_last(core_out_index==9'd395),
  .out_valid(formatter_out_valid),.out_ready(format_transfer&&wr_word_ready),.out_data(formatter_out_data),
  .out_last(formatter_out_last),.busy(formatter_busy),.done(formatter_done),.error(formatter_error),
  .total_cycles(formatter_cycles),.output_words(formatter_output_words)
 );
 assign formatter_valid_bits=6'd32;
 assign formatter_bits=32'd25344; // 1584 independent signed16 values per tile.


 always @* begin
  rd_desc_valid=0;rd_desc_base=0;rd_desc_count=0;rd_word_ready=0;
  wr_desc_valid=0;wr_desc_prefix=0;wr_desc_base=0;wr_desc_count=0;
  wr_word_valid=0;wr_word_data=0;wr_word_last=0;
  case(state)
   HEADER_REQ:begin rd_desc_valid=1;rd_desc_base=source_base;rd_desc_count=10;end
   HEADER_RUN:rd_word_ready=1;
   INVALIDATE_REQ:begin wr_desc_valid=1;wr_desc_base=output_base;wr_desc_count=1;end
   INVALIDATE_WORD:begin wr_word_valid=1;wr_word_data=0;wr_word_last=1;end
   RUN:begin
    case(read_state)
     DECODE_REQ:begin rd_desc_valid=1;rd_desc_base=active_base;rd_desc_count=active_words;end
     DECODE_RUN:rd_word_ready=decoder_in_ready;
     BIAS_REQ:begin rd_desc_valid=1;rd_desc_base=source_base+32'd40+{22'b0,group,7'b0};rd_desc_count=32;end
     SHIFT_REQ:begin rd_desc_valid=1;rd_desc_base=source_base+32'd1064+{24'b0,group,5'b0};rd_desc_count=8;end
     BIAS_RUN,SHIFT_RUN:rd_word_ready=core_meta_ready;
     default:begin end
    endcase
    case(write_state)
     OUTPUT_REQ:begin
      wr_desc_valid=1;wr_desc_prefix=0;wr_desc_base=output_base+32'd68+32'(tile)*32'd3168;wr_desc_count=792;
     end
     OUTPUT_RUN:begin wr_word_valid=formatter_out_valid;wr_word_data=formatter_out_data;wr_word_last=formatter_out_last;end
     LENGTH_REQ:begin wr_desc_valid=1;wr_desc_base=output_base+32'd4+{26'b0,tile,2'b0};wr_desc_count=1;end
     LENGTH_WORD:begin wr_word_valid=1;wr_word_data=output_bits;wr_word_last=1;end
     MAGIC_REQ:begin wr_desc_valid=1;wr_desc_base=output_base;wr_desc_count=1;end
     MAGIC_WORD:begin wr_word_valid=1;wr_word_data=32'h31443151;wr_word_last=1;end
     default:begin end
    endcase
   end
   ABORT_DRAIN:rd_word_ready=1;
   default:begin end
  endcase
 end

 integer i;
 always @(posedge clk)begin
  if(!rst_n)begin
   state<=IDLE;read_state<=DECODE_START;write_state<=FORMAT_START;load_done<=0;
   done<=0;error<=0;error_code<=0;shared_cache_clear<=0;task_cycles<=0;
   abort_issued<=0;output_index<=0;packed_index<=0;
   source_base<=0;output_base<=0;x_bits<=0;header_index<=0;layout_index<=0;layout_cursor<=0;
   group<=0;tile<=0;decode_weights<=0;decoder_started<=0;packer_started<=0;
   read_finished<=0;decode_finished<=0;pack_finished<=0;x_finished<=0;format_finished<=0;write_finished<=0;output_bits<=0;
   for(i=0;i<8;i=i+1)begin w_bits[i]<=0;w_base[i]<=0;end
  end else begin
   done<=0;shared_cache_clear<=0;
   if(state!=ABORT_DRAIN)abort_issued<=0;
   if(formatter_input&&formatter_in_ready)output_index<=output_index+1'b1;
   if(pack_out_valid&&pack_out_ready)packed_index<=packed_index+1'b1;
   if(busy)task_cycles<=task_cycles+1;
   if(rd_done_valid)read_finished<=1;
   if(decoder_done)decode_finished<=1;
   if(pack_done)pack_finished<=1;
   if(core_x_done)x_finished<=1;
   if(formatter_done)begin format_finished<=1;output_bits<=formatter_bits;end
   if(wr_done_valid)write_finished<=1;
   case(state)
    IDLE:if(start_valid&&start_ready)begin
     source_base<=start_source;output_base<=start_output;task_cycles<=1;error<=0;error_code<=0;
     group<=0;tile<=0;header_index<=0;layout_index<=0;decode_weights<=0;x_finished<=0;load_done<=0;
     read_state<=DECODE_START;write_state<=FORMAT_START;output_index<=0;packed_index<=0;
     read_finished<=0;decode_finished<=0;pack_finished<=0;format_finished<=0;write_finished<=0;
     decoder_started<=0;packer_started<=0;
     shared_cache_clear<=1;
     if(start_source[1:0]!=0 || start_output[1:0]!=0 || start_source<32'ha0000000 || start_output<32'ha0000000 ||
        {3'b0,start_source}+35'd1320>35'ha0080000 || {3'b0,start_output}+35'd50756>35'ha0080000)begin
      error<=1;error_code<=8'h01;state<=ABORT_DRAIN;
     end else state<=BEGIN_CORE;
    end
    BEGIN_CORE:if(core_begin_ready&&gate_active)state<=HEADER_REQ;
    HEADER_REQ:if(rd_desc_valid&&rd_desc_ready)begin state<=HEADER_RUN;read_finished<=0;end
    HEADER_RUN:begin
     if(rd_word_valid&&rd_word_ready)begin
      if(header_index==1)x_bits<=rd_word_data;
      if(header_index>=2 && header_index<=9)w_bits[header_index-2]<=rd_word_data;
      header_index<=header_index+1;
     end
     if(rd_done_valid&&!rd_done_error)begin
      layout_cursor<={3'b0,source_base}+35'd1320+((35'(x_bits)+35'd31)>>5)*35'd4;
      layout_index<=0;state<=LAYOUT;
     end
    end
    LAYOUT:begin
     if(layout_index<8)begin
      w_base[layout_index[2:0]]<=layout_cursor[31:0];
      layout_cursor<=layout_cursor+((35'(w_bits[layout_index[2:0]])+35'd31)>>5)*35'd4;
      layout_index<=layout_index+1;
     end else if(layout_cursor>35'ha0080000 ||
       layout_cursor!={3'b0,source_base}+{1'b0,gate_total,2'b0} ||
       !({3'b0,output_base}+35'd50756<={3'b0,source_base} || {3'b0,output_base}>=layout_cursor))begin
      error<=1;error_code<=8'h05;state<=ABORT_DRAIN;
     end else state<=INVALIDATE_REQ;
    end
    INVALIDATE_REQ:if(wr_desc_ready)state<=INVALIDATE_WORD;
    INVALIDATE_WORD:if(wr_word_ready)state<=INVALIDATE_WAIT;
    INVALIDATE_WAIT:if(wr_done_valid&&!wr_done_error)begin
     state<=RUN;read_state<=DECODE_START;write_state<=FORMAT_START;
     decoder_started<=0;packer_started<=0;read_finished<=0;decode_finished<=0;pack_finished<=0;
     format_finished<=0;write_finished<=0;load_done<=0;
    end
    RUN:begin end
    FINISH_CLOSE:if(!transport_busy&&!transport_draining&&gate_closed)begin state<=IDLE;done<=1;end
    ABORT_DRAIN:begin
     abort_issued<=1;
     if(abort_issued&&!transport_busy&&!transport_draining&&gate_closed)begin state<=IDLE;done<=1;end
    end
    default:begin state<=ABORT_DRAIN;error<=1;error_code<=8'hff;end
   endcase

   // Load identity is independent of the currently encoded/computed tile.
   // The next stream may prefill only the existing bounded queues; private
   // W/meta writes still require the core's real ready handshake and group.
   if(state==RUN)begin
    case(read_state)
     DECODE_START:begin
      packed_index<=0;
      if(decoder_start_valid&&decoder_start_ready)decoder_started<=1;
      if(pack_start_valid&&pack_start_ready)packer_started<=1;
      if((decoder_started||decoder_start_ready)&&(packer_started||pack_start_ready))read_state<=DECODE_REQ;
     end
     DECODE_REQ:if(rd_desc_valid&&rd_desc_ready)read_state<=DECODE_RUN;
     DECODE_RUN:if(read_finished&&decode_finished&&pack_finished&&(decode_weights||x_finished))begin
      if(decode_weights)read_state<=BIAS_REQ;
      else begin
       decode_weights<=1;read_state<=DECODE_START;decoder_started<=0;packer_started<=0;
       read_finished<=0;decode_finished<=0;pack_finished<=0;
      end
     end
     BIAS_REQ:if(rd_desc_valid&&rd_desc_ready)read_state<=BIAS_RUN;
     BIAS_RUN:if(rd_done_valid&&!rd_done_error)read_state<=SHIFT_REQ;
     SHIFT_REQ:if(rd_desc_valid&&rd_desc_ready)read_state<=SHIFT_RUN;
     SHIFT_RUN:if(rd_done_valid&&!rd_done_error)begin
      if(group==7)begin load_done<=1;read_state<=READ_DONE;end
      else begin
       group<=group+1'b1;read_state<=DECODE_START;decoder_started<=0;packer_started<=0;
       read_finished<=0;decode_finished<=0;pack_finished<=0;
      end
     end
     READ_DONE:begin end
     default:begin state<=ABORT_DRAIN;error<=1;error_code<=8'hfd;end
    endcase
    case(write_state)
     FORMAT_START:if(formatter_start_ready)begin write_state<=OUTPUT_REQ;output_index<=0;end
     OUTPUT_REQ:if(wr_desc_ready)write_state<=OUTPUT_RUN;
     OUTPUT_RUN:if(format_finished&&write_finished)begin write_state<=LENGTH_REQ;write_finished<=0;end
     LENGTH_REQ:if(wr_desc_ready)write_state<=LENGTH_WORD;
     LENGTH_WORD:if(wr_word_ready)write_state<=LENGTH_WAIT;
     LENGTH_WAIT:if(wr_done_valid&&!wr_done_error)begin
      if(tile==15)write_state<=load_done?MAGIC_REQ:WAIT_LOAD_DONE;
      else begin
       tile<=tile+1'b1;write_state<=FORMAT_START;format_finished<=0;write_finished<=0;
      end
     end
     WAIT_LOAD_DONE:if(load_done)write_state<=MAGIC_REQ;
     MAGIC_REQ:if(wr_desc_ready)write_state<=MAGIC_WORD;
     MAGIC_WORD:if(wr_word_ready)write_state<=MAGIC_WAIT;
     MAGIC_WAIT:if(wr_done_valid&&!wr_done_error)state<=FINISH_CLOSE;
     default:begin state<=ABORT_DRAIN;error<=1;error_code<=8'hfc;end
    endcase
   end
   // Faults win over either FSM's same-edge success. Reset both private stream
   // endpoints together, while transport preserves offered/accepted bus work.
   if(abort_now)begin
    state<=ABORT_DRAIN;error<=1;abort_issued<=1;
    error_code<=start_config_fault?8'h21:gate_descriptor_error?8'h22:header_fault?(header_index==0?8'h02:header_index==1?8'h03:8'h04):
                 invalid_core_group?8'h18:invalid_pack_output?8'h19:invalid_formatter_word?8'h1a:
                 transport_fault?8'h10:expired?8'h11:metadata_bad?8'h12:
                 invalid_core_output?8'h13:core_error?8'h14:decoder_error?8'h15:pack_error?8'h16:8'h17;
   end
  end
 end
endmodule
`default_nettype wire
