`timescale 1ns/1ps
`default_nettype none
// Fixed-width input reader, no entropy coding/prediction. X: signed12 values
// (6336, 76032 bits). W groups: signed10 values (2048, 20480 bits), sign-
// extended to the signed12 rowpair fields. LSB-first back-to-back packing in
// 32-bit words. Emits the frozen rowpair protocol: two values in low24, count2.
module q12_fixed12_reader (
 input wire clk,rst_n,
 input wire start_valid,output wire start_ready,
 input wire [15:0] start_symbols,input wire [31:0] start_encoded_bits,
 input wire in_valid,output wire in_ready,input wire [31:0] in_data,
 input wire [5:0] in_valid_bits,input wire in_last,
 output wire out_valid,input wire out_ready,output wire [47:0] out_data,
 output wire [2:0] out_count,output reg out_last,
 output reg busy,done,error,output reg [31:0] total_cycles,consumed_bits
);
 reg [55:0] buffer;
 reg [5:0] fill;
 reg wide;                     // 1: signed12 values, 0: signed10 values
 reg [15:0] symbol_total,emitted_symbols;
 reg [11:0] words_left;
 wire start_x=start_symbols==16'd6336 && start_encoded_bits==32'd76032;
 wire start_w=start_symbols==16'd2048 && start_encoded_bits==32'd20480;
 wire valid_start=start_x||start_w;
 wire [5:0] beat_bits=wide?6'd24:6'd20;
 assign start_ready=rst_n&&!busy;
 assign out_valid=busy&&!error&&fill>=beat_bits;
 assign out_data=wide?{24'b0,buffer[23:0]}:
                 {24'b0,{2{buffer[19]}},buffer[19:10],{2{buffer[9]}},buffer[9:0]};
 assign out_count=3'd2;
 wire out_fire=out_valid&&out_ready;
 assign in_ready=rst_n&&busy&&!error&&words_left!=0&&
                 (fill<beat_bits || (out_ready&&fill<=beat_bits+6'd24));
 wire in_fire=in_valid&&in_ready;
 wire bad_input=in_fire&&(in_valid_bits!=6'd32 || in_last!=(words_left==12'd1));
 wire [5:0] fill_after_out=out_fire?fill-beat_bits:fill;
 wire [55:0] buffer_after_out=out_fire?(wide?{24'b0,buffer[55:24]}:{20'b0,buffer[55:20]}):buffer;
 always @(posedge clk)begin
  if(!rst_n)begin
   buffer<=0;fill<=0;wide<=1;symbol_total<=0;emitted_symbols<=0;words_left<=0;
   busy<=0;done<=0;error<=0;total_cycles<=0;consumed_bits<=0;
  end else begin
   done<=0;
   if(busy)total_cycles<=total_cycles+1'b1;
   if(start_valid&&start_ready)begin
    buffer<=0;fill<=0;wide<=!start_w;symbol_total<=start_symbols;emitted_symbols<=0;
    words_left<=valid_start?start_encoded_bits[16:5]:12'd0;
    total_cycles<=0;consumed_bits<=0;error<=!valid_start;busy<=valid_start;done<=!valid_start;
   end else if(busy)begin
    if(bad_input)begin busy<=0;done<=1;error<=1;end
    else begin
     if(out_fire)begin
      emitted_symbols<=emitted_symbols+16'd2;
      if(emitted_symbols+16'd2==symbol_total)begin busy<=0;done<=1;end
     end
     if(in_fire)begin
      buffer<=buffer_after_out|({24'b0,in_data}<<fill_after_out);
      fill<=fill_after_out+6'd32;
      words_left<=words_left-1'b1;consumed_bits<=consumed_bits+32'd32;
     end else begin
      buffer<=buffer_after_out;fill<=fill_after_out;
     end
    end
   end
  end
 end
 always @* out_last=busy&&(emitted_symbols+16'd2==symbol_total);
endmodule
`default_nettype wire
