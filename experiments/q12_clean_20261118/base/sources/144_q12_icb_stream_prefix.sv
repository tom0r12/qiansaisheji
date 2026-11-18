`timescale 1ns/1ps
`default_nettype none
module q12_icb_stream_prefix #(
 parameter integer OUTSTANDING=4,
 parameter integer READ_DEPTH=16,
 parameter integer WRITE_DEPTH=8
)(
 input wire clk,rst_n,soft_abort,
 input wire rd_desc_valid,output wire rd_desc_ready,
 input wire [31:0] rd_desc_base,rd_desc_count,
 output wire rd_word_valid,input wire rd_word_ready,
 output wire [31:0] rd_word_data,output wire rd_word_last,
 output reg rd_done_valid,input wire rd_done_ready,output reg rd_done_error,
 input wire wr_desc_valid,output wire wr_desc_ready,
 input wire wr_desc_prefix,
 input wire [31:0] wr_desc_base,wr_desc_count,
 input wire wr_word_valid,output wire wr_word_ready,
 input wire [31:0] wr_word_data,input wire wr_word_last,
 output reg wr_done_valid,input wire wr_done_ready,output reg wr_done_error,
 output wire busy,output wire draining,
 output wire icb_cmd_valid,input wire icb_cmd_ready,
 output wire icb_cmd_read,output wire [31:0] icb_cmd_addr,icb_cmd_wdata,
 output wire [3:0] icb_cmd_wmask,
 input wire icb_rsp_valid,output wire icb_rsp_ready,
 input wire [31:0] icb_rsp_rdata,input wire icb_rsp_err
);
 localparam integer OPW=$clog2(OUTSTANDING), RPW=$clog2(READ_DEPTH), WPW=$clog2(WRITE_DEPTH);
 reg rd_active,wr_active,fault_q,prefer_read;
 reg wr_prefix,wr_closed;
 reg [31:0] rd_base,rd_total,rd_issued,rd_delivered;
 reg [31:0] wr_base,wr_total,wr_supplied,wr_issued,wr_retired;
 reg owner_read[0:OUTSTANDING-1],owner_last[0:OUTSTANDING-1];
 reg [OPW-1:0] owner_head,owner_tail;
 reg [OPW:0] owner_count,read_pending;
 reg [31:0] read_data[0:READ_DEPTH-1],write_data[0:WRITE_DEPTH-1];
 reg read_last[0:READ_DEPTH-1];
 reg [RPW-1:0] read_head,read_tail;
 reg [WPW-1:0] write_head,write_tail;
 reg [RPW:0] read_count;
 reg [WPW:0] write_count;
 reg held_valid,held_read,held_last;
 reg [31:0] held_addr,held_data;

 function automatic descriptor_good(input [31:0] base,count);
  reg [34:0] end_address;
  begin
   end_address={3'b0,base}+({3'b0,count}<<2);
   descriptor_good=base[1:0]==0 && base>=32'ha0000000 &&
                   count!=0 && count<=32'd131072 && end_address<=35'ha0080000;
  end
 endfunction
 wire rd_desc_fire=rd_desc_valid&&rd_desc_ready;
 wire wr_desc_fire=wr_desc_valid&&wr_desc_ready;
 assign rd_desc_ready=rst_n&&!soft_abort&&!fault_q&&!rd_active&&!rd_done_valid;
 assign wr_desc_ready=rst_n&&!soft_abort&&!fault_q&&!wr_active&&!wr_done_valid;
 assign rd_word_valid=rst_n&&(read_count!=0);
 assign rd_word_data=read_data[read_head];
 assign rd_word_last=read_last[read_head];
 wire read_pop=rd_word_valid&&rd_word_ready;
 assign wr_word_ready=rst_n&&wr_active&&(!wr_prefix||!wr_closed)&&!fault_q&&!soft_abort&&
                      wr_supplied<wr_total&&write_count<(WPW+1)'(WRITE_DEPTH);
 wire write_input_fire=wr_word_valid&&wr_word_ready;
 wire bad_last=write_input_fire&&(wr_prefix?
                (!wr_word_last&&(wr_supplied==wr_total-1)):
                (wr_word_last!=(wr_supplied==wr_total-1)));
 wire valid_write_descriptor=descriptor_good(wr_desc_base,wr_desc_count)&&
                              (!wr_desc_prefix||wr_desc_count<=32'd646);
 assign icb_rsp_ready=rst_n&&(owner_count!=0);
 wire response_fire=icb_rsp_valid&&icb_rsp_ready;
 wire response_read=owner_read[owner_head];
 wire stop_now=soft_abort||bad_last||(response_fire&&icb_rsp_err);
 wire credit_available=(owner_count<(OPW+1)'(OUTSTANDING))||response_fire;
 // A held read is the only unaccepted reservation and cannot coexist with a
 // second fresh offer. This sum also includes every returned buffered word.
 wire read_space=({{(32-RPW-1){1'b0}},read_count}+
                  {{(32-OPW-1){1'b0}},read_pending}<READ_DEPTH)||read_pop;
 wire read_eligible=rd_active&&rd_issued<rd_total&&read_space;
 wire write_eligible=wr_active&&wr_issued<wr_total&&(write_count!=0);
 wire choose_read=read_eligible&&(!write_eligible||prefer_read);
 wire offer_new=rst_n&&!fault_q&&!stop_now&&credit_available&&(read_eligible||write_eligible);
 assign icb_cmd_valid=rst_n&&(held_valid||offer_new);
 assign icb_cmd_read=held_valid?held_read:choose_read;
 assign icb_cmd_addr=held_valid?held_addr:
                     choose_read?(rd_base+(rd_issued<<2)):(wr_base+(wr_issued<<2));
 assign icb_cmd_wdata=held_valid?held_data:choose_read?32'b0:write_data[write_head];
 assign icb_cmd_wmask=4'hf;
 wire command_last=held_valid?held_last:
                    choose_read?(rd_issued==rd_total-1):(wr_issued==wr_total-1);
 wire command_fire=icb_cmd_valid&&icb_cmd_ready;
 wire read_accept=command_fire&&icb_cmd_read;
 wire write_accept=command_fire&&!icb_cmd_read;
 wire write_pop=write_accept&&!fault_q&&!stop_now;
 wire write_push=write_input_fire&&!stop_now;
 wire read_push=response_fire&&response_read&&!icb_rsp_err&&!fault_q&&!stop_now;
 assign busy=rd_active||wr_active||rd_done_valid||wr_done_valid||held_valid||(owner_count!=0);
 assign draining=fault_q;

 always @(posedge clk) begin
  if(!rst_n) begin
   rd_active<=0;wr_active<=0;fault_q<=0;prefer_read<=1;wr_prefix<=0;wr_closed<=0;
   rd_base<=0;rd_total<=0;rd_issued<=0;rd_delivered<=0;
   wr_base<=0;wr_total<=0;wr_supplied<=0;wr_issued<=0;wr_retired<=0;
   rd_done_valid<=0;rd_done_error<=0;wr_done_valid<=0;wr_done_error<=0;
   owner_head<=0;owner_tail<=0;owner_count<=0;read_pending<=0;
   read_head<=0;read_tail<=0;read_count<=0;
   write_head<=0;write_tail<=0;write_count<=0;
   held_valid<=0;held_read<=0;held_last<=0;held_addr<=0;held_data<=0;
  end else begin
   if(rd_done_valid&&rd_done_ready)rd_done_valid<=0;
   if(wr_done_valid&&wr_done_ready)wr_done_valid<=0;
   if(fault_q&&!rd_active&&!wr_active&&!rd_done_valid&&!wr_done_valid&&
      owner_count==0&&!held_valid&&read_count==0)fault_q<=0;
   if(stop_now)fault_q<=1;
   if(rd_desc_fire)begin
    rd_done_error<=!descriptor_good(rd_desc_base,rd_desc_count);
    if(descriptor_good(rd_desc_base,rd_desc_count))begin
     rd_active<=1;rd_base<=rd_desc_base;rd_total<=rd_desc_count;rd_issued<=0;rd_delivered<=0;
    end else rd_done_valid<=1;
   end
   if(wr_desc_fire)begin
    wr_done_error<=!valid_write_descriptor;
    if(valid_write_descriptor)begin
     wr_active<=1;wr_base<=wr_desc_base;wr_total<=wr_desc_count;
     wr_prefix<=wr_desc_prefix;wr_closed<=!wr_desc_prefix;
     wr_supplied<=0;wr_issued<=0;wr_retired<=0;
    end else wr_done_valid<=1;
   end
   // Payload ownership is retained across abort/error until real acceptance.
   if(icb_cmd_valid&&!icb_cmd_ready&&!held_valid)begin
    held_valid<=1;held_read<=icb_cmd_read;held_last<=command_last;
    held_addr<=icb_cmd_addr;held_data<=icb_cmd_wdata;
   end
   if(command_fire)begin
    held_valid<=0;prefer_read<=!icb_cmd_read;
    owner_read[owner_tail]<=icb_cmd_read;owner_last[owner_tail]<=command_last;
    owner_tail<=owner_tail==OPW'(OUTSTANDING-1)?'0:owner_tail+1'b1;
    if(icb_cmd_read)rd_issued<=rd_issued+1'b1;
    else wr_issued<=wr_issued+1'b1;
   end
   if(response_fire)begin
    owner_head<=owner_head==OPW'(OUTSTANDING-1)?'0:owner_head+1'b1;
    if(!response_read)wr_retired<=wr_retired+1'b1;
   end
   case({command_fire,response_fire})
    2'b10:owner_count<=owner_count+1'b1;
    2'b01:owner_count<=owner_count-1'b1;
    default:begin end
   endcase
   case({read_accept,response_fire&&response_read})
    2'b10:read_pending<=read_pending+1'b1;
    2'b01:read_pending<=read_pending-1'b1;
    default:begin end
   endcase
   if(read_push)begin
    read_data[read_tail]<=icb_rsp_rdata;read_last[read_tail]<=owner_last[owner_head];
    read_tail<=read_tail==RPW'(READ_DEPTH-1)?'0:read_tail+1'b1;
   end
   if(read_pop)begin
    read_head<=read_head==RPW'(READ_DEPTH-1)?'0:read_head+1'b1;rd_delivered<=rd_delivered+1'b1;
   end
   case({read_push,read_pop})
    2'b10:read_count<=read_count+1'b1;
    2'b01:read_count<=read_count-1'b1;
    default:begin end
   endcase
   if(fault_q||stop_now)begin
    write_count<=0;write_head<=0;write_tail<=0;
   end else begin
    if(write_push)begin
     write_data[write_tail]<=wr_word_data;wr_supplied<=wr_supplied+1'b1;
     if(wr_prefix&&wr_word_last)begin wr_total<=wr_supplied+1'b1;wr_closed<=1;end
     write_tail<=write_tail==WPW'(WRITE_DEPTH-1)?'0:write_tail+1'b1;
    end
    if(write_pop)write_head<=write_head==WPW'(WRITE_DEPTH-1)?'0:write_head+1'b1;
    case({write_push,write_pop})
     2'b10:write_count<=write_count+1'b1;
     2'b01:write_count<=write_count-1'b1;
     default:begin end
    endcase
   end
   if(fault_q&&owner_count==0&&!held_valid&&read_count==0)begin
    if(rd_active)begin rd_active<=0;rd_done_valid<=1;rd_done_error<=1;end
    if(wr_active)begin wr_active<=0;wr_done_valid<=1;wr_done_error<=1;end
   end else if(!fault_q&&!stop_now)begin
    if(rd_active&&rd_delivered==rd_total)begin rd_active<=0;rd_done_valid<=1;rd_done_error<=0;end
    if(wr_active&&wr_closed&&wr_retired==wr_total)begin wr_active<=0;wr_done_valid<=1;wr_done_error<=0;end
   end
  end
 end
endmodule
`default_nettype wire

