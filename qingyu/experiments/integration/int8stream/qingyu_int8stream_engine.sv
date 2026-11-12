`timescale 1ns/1ps
`default_nettype none
// Experimental complete-packet engine. CPU/MMIO attachment is a separate layer.
// All external data movement uses this single original-system-bus master port.
module qingyu_int8stream_engine #(
 parameter integer TIMEOUT_CYCLES=2000000
)(
 input wire clk,rst_n,
 input wire start_valid,output wire start_ready,
 input wire [31:0] start_source,start_output,
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
  SHIFT_REQ=10,SHIFT_RUN=11,ENCODE_START=12,OUTPUT_REQ=13,OUTPUT_RUN=14,
  LENGTH_REQ=15,LENGTH_WORD=16,LENGTH_WAIT=17,MAGIC_REQ=18,MAGIC_WORD=19,
  MAGIC_WAIT=20,ABORT_DRAIN=21,INVALIDATE_REQ=22,INVALIDATE_WORD=23,INVALIDATE_WAIT=24;
 reg [5:0] state;
 reg [31:0] source_base,output_base,x_bits,w_bits[0:7],w_base[0:7];
 reg [34:0] layout_cursor;
 reg [3:0] header_index,layout_index,tile;
 reg [2:0] group;
 reg decode_weights,decoder_started,packer_started;
 reg read_finished,decode_finished,pack_finished,x_finished;
 reg encode_finished,write_finished;
 reg [31:0] output_bits;
 reg abort_issued;
 reg [8:0] output_index;
 reg [10:0] packed_index;
 wire transport_busy,transport_draining;
 wire pipe_rst_n=rst_n && state!=ABORT_DRAIN;
 wire core_begin_ready,core_busy,core_done,core_error,core_x_done;
 wire core_pair_loaded,core_pair_done;
 wire [2:0] core_group,core_pair_done_index;
 wire [1:0] core_slot;
 wire core_x_ready,core_w_ready,core_meta_ready,core_out_valid;
 wire [31:0] core_out_data;
 wire [3:0] core_out_tile;
 wire [8:0] core_out_index;
 wire decoder_start_ready,decoder_in_ready,decoder_out_valid,decoder_out_last;
 wire [31:0] decoder_out_data,decoder_cycles,decoder_bits;
 wire [2:0] decoder_out_count;
 wire decoder_busy,decoder_done,decoder_error;
 wire pack_start_ready,pack_in_ready,pack_out_valid,pack_out_last;
 wire [31:0] pack_out_data,pack_cycles;
 wire [10:0] pack_out_index;
 wire pack_busy,pack_done,pack_error;
 wire [2:0] pack_error_code;
 wire encoder_start_ready,encoder_in_ready,encoder_out_valid,encoder_out_last;
 wire [31:0] encoder_out_data,encoder_cycles,encoder_bits;
 wire [5:0] encoder_valid_bits;
 wire encoder_busy,encoder_done,encoder_error;
 wire rd_desc_ready,rd_word_valid,rd_word_last,rd_done_valid,rd_done_error;
 wire [31:0] rd_word_data;
 wire wr_desc_ready,wr_word_ready,wr_done_valid,wr_done_error;
 reg rd_desc_valid,rd_word_ready,wr_desc_valid,wr_desc_prefix,wr_word_valid,wr_word_last;
 reg [31:0] rd_desc_base,rd_desc_count,wr_desc_base,wr_desc_count,wr_word_data;
 wire decoding=state==DECODE_START || state==DECODE_REQ || state==DECODE_RUN;
 wire encoding=state==ENCODE_START || state==OUTPUT_REQ || state==OUTPUT_RUN;
 wire [31:0] active_bits=decode_weights?w_bits[group]:x_bits;
 wire [31:0] active_base=decode_weights?w_base[group]:source_base+32'd808;
 wire [31:0] active_words=(active_bits+32'd31)>>5;
 wire decoder_start_valid=state==DECODE_START && !decoder_started;
 wire pack_start_valid=state==DECODE_START && !packer_started;
 wire encoder_start_valid=state==ENCODE_START;
 wire encoder_input=state==OUTPUT_RUN && output_index<9'd396 && core_out_valid;
 wire core_out_ready=state==OUTPUT_RUN && output_index<9'd396 && encoder_in_ready;
 wire pack_out_ready=state==DECODE_RUN && (decode_weights?core_w_ready:core_x_ready);
 wire invalid_core_output=encoder_input && encoder_in_ready && (core_out_tile!=tile || core_out_index!=output_index);
 wire invalid_core_group=((state==DECODE_RUN && decode_weights && pack_out_valid && core_w_ready) ||
                          (metadata_phase && rd_word_valid && core_meta_ready)) && core_group!=group;
 wire metadata_phase=state==BIAS_RUN || state==SHIFT_RUN;
 wire invalid_pack_output=pack_out_valid && state==DECODE_RUN &&
  (pack_out_index!=packed_index || pack_out_last!=(packed_index==(decode_weights?11'd511:11'd1599)));
 wire invalid_encoder_word=state==OUTPUT_RUN && encoder_out_valid &&
  (encoder_valid_bits==0 || encoder_valid_bits>32 || (!encoder_out_last && encoder_valid_bits!=32));
 wire header_fault=state==HEADER_RUN && rd_word_valid && rd_word_ready &&
  ((header_index==0 && rd_word_data!=32'h31523851) ||
   (header_index==1 && (rd_word_data==0 || rd_word_data>50886)) ||
   (header_index>=2 && header_index<=9 && (rd_word_data==0 || rd_word_data>16448)));
 wire metadata_bad=state==SHIFT_RUN && rd_word_valid && rd_word_ready &&
  (rd_word_data[7:0]>47 || rd_word_data[15:8]>47 || rd_word_data[23:16]>47 || rd_word_data[31:24]>47);
 wire datapath_fault=(decoding && (decoder_error||pack_error)) ||
  (encoding && encoder_error) || core_error || invalid_core_output || invalid_core_group || metadata_bad || header_fault ||
  invalid_pack_output || invalid_encoder_word;
 wire transport_fault=(rd_done_valid&&rd_done_error)||(wr_done_valid&&wr_done_error);
 wire expired=busy && task_cycles>=32'(TIMEOUT_CYCLES);
 wire abort_now=busy && state!=ABORT_DRAIN && (datapath_fault||transport_fault||expired);
 assign busy=state!=IDLE;
 assign start_ready=rst_n && state==IDLE && !transport_busy && !transport_draining && core_begin_ready;
 // Optional internal diagnostics remain visible to the verification hierarchy;
 // they do not control completion, which belongs to the originating bus ACK.
 wire unused_component_telemetry=^{core_busy,core_done,core_pair_loaded,core_pair_done,core_pair_done_index,core_slot,
  decoder_cycles,decoder_bits,decoder_busy,pack_cycles,pack_busy,pack_error_code,encoder_cycles,encoder_busy};

 qingyu_icb_stream_prefix #(.OUTSTANDING(8),.READ_DEPTH(16),.WRITE_DEPTH(8)) transport(
  .clk(clk),.rst_n(rst_n),.soft_abort(abort_now || (state==ABORT_DRAIN && !abort_issued)),
  .rd_desc_valid(rd_desc_valid),.rd_desc_ready(rd_desc_ready),.rd_desc_base(rd_desc_base),.rd_desc_count(rd_desc_count),
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
 rice32_decoder #(.LANES(4)) decoder(
  .clk(clk),.rst_n(pipe_rst_n),.start_valid(decoder_start_valid),.start_ready(decoder_start_ready),
  .start_symbols(decode_weights?16'd2048:16'd6336),.start_encoded_bits(active_bits),
  .start_k(decode_weights?3'd5:3'd2),.start_delta(!decode_weights),.start_row_bytes(decode_weights?9'd32:9'd64),
  .in_valid(state==DECODE_RUN&&rd_word_valid),.in_ready(decoder_in_ready),.in_data(rd_word_data),
  .in_valid_bits(rd_word_last && active_bits[4:0]!=0 ? {1'b0,active_bits[4:0]} : 6'd32),.in_last(rd_word_last),
  .out_valid(decoder_out_valid),.out_ready(pack_in_ready),.out_data(decoder_out_data),
  .out_count(decoder_out_count),.out_last(decoder_out_last),.busy(decoder_busy),.done(decoder_done),.error(decoder_error),
  .total_cycles(decoder_cycles),.consumed_bits(decoder_bits)
 );
 rowpair_pack reorder(
  .clk(clk),.rst_n(pipe_rst_n),.start_valid(pack_start_valid),.start_ready(pack_start_ready),.start_mode_w(decode_weights),
  .in_valid(decoder_out_valid),.in_ready(pack_in_ready),.in_data(decoder_out_data),.in_count(decoder_out_count),
  .in_last(decoder_out_last),.upstream_error(decoder_error),
  .out_valid(pack_out_valid),.out_ready(pack_out_ready),.out_data(pack_out_data),.out_last(pack_out_last),
  .out_word_index(pack_out_index),.busy(pack_busy),.done(pack_done),.error(pack_error),
  .error_code(pack_error_code),.total_cycles(pack_cycles)
 );
 winograd_int8_task8 compute(
  .clk(clk),.rst_n(pipe_rst_n),.begin_valid(state==BEGIN_CORE),.begin_ready(core_begin_ready),
  .x_valid(state==DECODE_RUN&&!decode_weights&&pack_out_valid),.x_ready(core_x_ready),.x_data(pack_out_data),
  .w_valid(state==DECODE_RUN&&decode_weights&&pack_out_valid),.w_ready(core_w_ready),.w_data(pack_out_data),
  .meta_valid(metadata_phase&&rd_word_valid),.meta_ready(core_meta_ready),.meta_data(rd_word_data),
  .pair_group(core_group),.pair_slot_base(core_slot),.x_done(core_x_done),.pair_loaded(core_pair_loaded),
  .pair_done(core_pair_done),.pair_done_index(core_pair_done_index),
  .out_valid(core_out_valid),.out_ready(core_out_ready),.out_data(core_out_data),.out_tile(core_out_tile),.out_word_index(core_out_index),
  .busy(core_busy),.done(core_done),.error(core_error),.total_cycles(core_cycles),.load_cycles(core_load_cycles),
  .factor_cycles(core_factor_cycles),.cache_read_cycles(core_cache_cycles),.compute_cycles(core_compute_cycles),.store_cycles(core_store_cycles)
 );
 rice32_encoder #(.LANES(4)) encoder(
  .clk(clk),.rst_n(pipe_rst_n),.start_valid(encoder_start_valid),.start_ready(encoder_start_ready),
  .start_symbols(16'd1584),.start_k(3'd3),.start_delta(1'b1),.start_row_bytes(9'd16),
  .in_valid(encoder_input),.in_ready(encoder_in_ready),.in_data(core_out_data),.in_count(3'd4),.in_last(core_out_index==9'd395),
  .out_valid(encoder_out_valid),.out_ready(state==OUTPUT_RUN&&wr_word_ready),.out_data(encoder_out_data),
  .out_valid_bits(encoder_valid_bits),.out_last(encoder_out_last),.busy(encoder_busy),.done(encoder_done),.error(encoder_error),
  .total_cycles(encoder_cycles),.encoded_bits(encoder_bits)
 );

 always @* begin
  rd_desc_valid=0;rd_desc_base=0;rd_desc_count=0;rd_word_ready=0;
  wr_desc_valid=0;wr_desc_prefix=0;wr_desc_base=0;wr_desc_count=0;
  wr_word_valid=0;wr_word_data=0;wr_word_last=0;
  case(state)
   HEADER_REQ:begin rd_desc_valid=1;rd_desc_base=source_base;rd_desc_count=10;end
   HEADER_RUN:rd_word_ready=1;
   DECODE_REQ:begin rd_desc_valid=1;rd_desc_base=active_base;rd_desc_count=active_words;end
   DECODE_RUN:rd_word_ready=decoder_in_ready;
   BIAS_REQ:begin rd_desc_valid=1;rd_desc_base=source_base+32'd40+{23'b0,group,6'b0};rd_desc_count=16;end
   SHIFT_REQ:begin rd_desc_valid=1;rd_desc_base=source_base+32'd552+{24'b0,group,5'b0};rd_desc_count=8;end
   BIAS_RUN,SHIFT_RUN:rd_word_ready=core_meta_ready;
   OUTPUT_REQ:begin
    wr_desc_valid=1;wr_desc_prefix=1;wr_desc_base=output_base+32'd68+32'(tile)*32'd1592;wr_desc_count=398;
   end
   OUTPUT_RUN:begin wr_word_valid=encoder_out_valid;wr_word_data=encoder_out_data;wr_word_last=encoder_out_last;end
   LENGTH_REQ:begin wr_desc_valid=1;wr_desc_base=output_base+32'd4+{26'b0,tile,2'b0};wr_desc_count=1;end
   LENGTH_WORD:begin wr_word_valid=1;wr_word_data=output_bits;wr_word_last=1;end
   MAGIC_REQ:begin wr_desc_valid=1;wr_desc_base=output_base;wr_desc_count=1;end
   MAGIC_WORD:begin wr_word_valid=1;wr_word_data=32'h31593851;wr_word_last=1;end
   INVALIDATE_REQ:begin wr_desc_valid=1;wr_desc_base=output_base;wr_desc_count=1;end
   INVALIDATE_WORD:begin wr_word_valid=1;wr_word_data=0;wr_word_last=1;end
   ABORT_DRAIN:rd_word_ready=1;
   default:begin end
  endcase
 end

 integer i;
 always @(posedge clk)begin
  if(!rst_n)begin
   state<=IDLE;done<=0;error<=0;error_code<=0;shared_cache_clear<=0;task_cycles<=0;
   abort_issued<=0;output_index<=0;packed_index<=0;
   source_base<=0;output_base<=0;x_bits<=0;header_index<=0;layout_index<=0;layout_cursor<=0;
   group<=0;tile<=0;decode_weights<=0;decoder_started<=0;packer_started<=0;
   read_finished<=0;decode_finished<=0;pack_finished<=0;x_finished<=0;encode_finished<=0;write_finished<=0;output_bits<=0;
   for(i=0;i<8;i=i+1)begin w_bits[i]<=0;w_base[i]<=0;end
  end else begin
   done<=0;shared_cache_clear<=0;
   if(state!=ABORT_DRAIN)abort_issued<=0;
   if(encoder_input&&encoder_in_ready)output_index<=output_index+1'b1;
   if(pack_out_valid&&pack_out_ready)packed_index<=packed_index+1'b1;
   if(busy)task_cycles<=task_cycles+1;
   if(rd_done_valid)read_finished<=1;
   if(decoder_done)decode_finished<=1;
   if(pack_done)pack_finished<=1;
   if(core_x_done)x_finished<=1;
   if(encoder_done)begin encode_finished<=1;output_bits<=encoder_bits;end
   if(wr_done_valid)write_finished<=1;
   case(state)
    IDLE:if(start_valid&&start_ready)begin
     source_base<=start_source;output_base<=start_output;task_cycles<=1;error<=0;error_code<=0;
     group<=0;tile<=0;header_index<=0;layout_index<=0;decode_weights<=0;x_finished<=0;
     read_finished<=0;decode_finished<=0;pack_finished<=0;encode_finished<=0;write_finished<=0;
     shared_cache_clear<=1;
     if(start_source[1:0]!=0 || start_output[1:0]!=0 || start_source<32'ha0000000 || start_output<32'ha0000000 ||
        {3'b0,start_source}+35'd808>35'ha0080000 || {3'b0,start_output}+35'd25540>35'ha0080000)begin
      error<=1;error_code<=8'h01;state<=ABORT_DRAIN;
     end else state<=BEGIN_CORE;
    end
    BEGIN_CORE:if(core_begin_ready)state<=HEADER_REQ;
    HEADER_REQ:if(rd_desc_ready)begin state<=HEADER_RUN;read_finished<=0;end
    HEADER_RUN:begin
     if(rd_word_valid&&rd_word_ready)begin
      if(header_index==1)begin
       x_bits<=rd_word_data;
      end
      if(header_index>=2 && header_index<=9)begin
       w_bits[header_index-2]<=rd_word_data;
      end
      header_index<=header_index+1;
     end
     if(rd_done_valid&&!rd_done_error)begin
      layout_cursor<={3'b0,source_base}+35'd808+((35'(x_bits)+35'd31)>>5)*35'd4;
      layout_index<=0;state<=LAYOUT;
     end
    end
    LAYOUT:begin
     if(layout_index<8)begin
      w_base[layout_index[2:0]]<=layout_cursor[31:0];
      layout_cursor<=layout_cursor+((35'(w_bits[layout_index[2:0]])+35'd31)>>5)*35'd4;
      layout_index<=layout_index+1;
     end else if(layout_cursor>35'ha0080000 ||
       !({3'b0,output_base}+35'd25540<={3'b0,source_base} || {3'b0,output_base}>=layout_cursor))begin
      error<=1;error_code<=8'h05;state<=ABORT_DRAIN;
     end else begin
      state<=INVALIDATE_REQ;decoder_started<=0;packer_started<=0;
      read_finished<=0;decode_finished<=0;pack_finished<=0;
     end
    end
    INVALIDATE_REQ:if(wr_desc_ready)state<=INVALIDATE_WORD;
    INVALIDATE_WORD:if(wr_word_ready)state<=INVALIDATE_WAIT;
    INVALIDATE_WAIT:if(wr_done_valid&&!wr_done_error)state<=DECODE_START;
    DECODE_START:begin
     packed_index<=0;
     if(decoder_start_valid&&decoder_start_ready)decoder_started<=1;
     if(pack_start_valid&&pack_start_ready)packer_started<=1;
     if((decoder_started||decoder_start_ready)&&(packer_started||pack_start_ready))state<=DECODE_REQ;
    end
    DECODE_REQ:if(rd_desc_ready)state<=DECODE_RUN;
    DECODE_RUN:if(read_finished&&decode_finished&&pack_finished&&(decode_weights||x_finished))begin
     if(decode_weights)state<=BIAS_REQ;
     else begin
      decode_weights<=1;state<=DECODE_START;decoder_started<=0;packer_started<=0;
      read_finished<=0;decode_finished<=0;pack_finished<=0;
     end
    end
    BIAS_REQ:if(rd_desc_ready)state<=BIAS_RUN;
    BIAS_RUN:if(rd_done_valid&&!rd_done_error)state<=SHIFT_REQ;
    SHIFT_REQ:if(rd_desc_ready)state<=SHIFT_RUN;
    SHIFT_RUN:if(rd_done_valid&&!rd_done_error)begin state<=ENCODE_START;encode_finished<=0;write_finished<=0;end
    ENCODE_START:if(encoder_start_ready)begin state<=OUTPUT_REQ;output_index<=0;end
    OUTPUT_REQ:if(wr_desc_ready)state<=OUTPUT_RUN;
    OUTPUT_RUN:if(encode_finished&&write_finished)begin state<=LENGTH_REQ;write_finished<=0;end
    LENGTH_REQ:if(wr_desc_ready)state<=LENGTH_WORD;
    LENGTH_WORD:if(wr_word_ready)state<=LENGTH_WAIT;
    LENGTH_WAIT:if(wr_done_valid&&!wr_done_error)begin
     if(tile==15)state<=MAGIC_REQ;
     else begin
      tile<=tile+1;
      if(tile[0])begin
       group<=group+1;state<=DECODE_START;decoder_started<=0;packer_started<=0;
       read_finished<=0;decode_finished<=0;pack_finished<=0;
      end else begin state<=ENCODE_START;encode_finished<=0;write_finished<=0;end
     end
    end
    MAGIC_REQ:if(wr_desc_ready)state<=MAGIC_WORD;
    MAGIC_WORD:if(wr_word_ready)state<=MAGIC_WAIT;
    MAGIC_WAIT:if(wr_done_valid&&!wr_done_error)begin state<=IDLE;done<=1;end
    ABORT_DRAIN:begin
     abort_issued<=1;
     if(abort_issued&&!transport_busy&&!transport_draining)begin state<=IDLE;done<=1;end
    end
    default:begin state<=ABORT_DRAIN;error<=1;error_code<=8'hff;end
   endcase
   // A fault always wins over a same-edge success transition. The bus endpoint
   // keeps its reset released and drains already offered/accepted operations.
   if(abort_now)begin
    state<=ABORT_DRAIN;error<=1;abort_issued<=1;
    error_code<=header_fault?(header_index==0?8'h02:header_index==1?8'h03:8'h04):
                 invalid_core_group?8'h18:invalid_pack_output?8'h19:invalid_encoder_word?8'h1a:
                 transport_fault?8'h10:expired?8'h11:metadata_bad?8'h12:
                 invalid_core_output?8'h13:core_error?8'h14:decoder_error?8'h15:pack_error?8'h16:8'h17;
   end
  end
 end
endmodule
`default_nettype wire
