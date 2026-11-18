`timescale 1ns/1ps
`default_nettype none
// Fixed-width input reader emitting core-order 4-value beats directly.
// The host packs values offline in the accelerator's row-pair consumption
// order (permitted offline reordering; no entropy coding, no prediction):
//  X (6336 signed12): row pairs p=0..48, k=0..31: x[2p][2k],x[2p][2k+1],
//     x[2p+1][2k],x[2p+1][2k+1]; then row 98 alone, k=0..31: x[98][2k],x[98][2k+1]
//     (the odd half of those final 32 beats is emitted as zero).
//  W group (2048 values, signed12 or signed10): m=0..31, c=0,2,..,30:
//     w[2m][c],w[2m+1][c],w[2m][c+1],w[2m+1][c+1].
// Values are packed LSB-first back to back in 32-bit words.
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
 reg [95:0] buffer;
 reg [6:0] fill;               // valid bits, 0..80
 reg [1:0] mode;               // 0: X12, 1: W12, 2: W10
 reg [10:0] beat,beat_total;
 reg [11:0] words_left;
 wire start_x=start_symbols==16'd6336 && start_encoded_bits==32'd76032;
 wire start_w12=start_symbols==16'd2048 && start_encoded_bits==32'd24576;
 wire start_w10=start_symbols==16'd2048 && start_encoded_bits==32'd20480;
 wire valid_start=start_x||start_w12||start_w10;
 wire x_tail=mode==2'd0 && beat>=11'd1568;
 wire [6:0] need=mode==2'd2 ? 7'd40 : (x_tail ? 7'd24 : 7'd48);
 assign start_ready=rst_n&&!busy;
 assign out_valid=busy&&!error&&fill>=need;
 assign out_data=mode==2'd2 ?
   {{2{buffer[39]}},buffer[39:30],{2{buffer[29]}},buffer[29:20],{2{buffer[19]}},buffer[19:10],{2{buffer[9]}},buffer[9:0]} :
   (x_tail ? {24'b0,buffer[23:0]} : buffer[47:0]);
 assign out_count=3'd4;
 wire out_fire=out_valid&&out_ready;
 wire [6:0] fill_after_out=out_fire?fill-need:fill;
 wire [95:0] buffer_after_out=out_fire?(buffer>>need):buffer;
 assign in_ready=rst_n&&busy&&!error&&words_left!=0&&fill_after_out<=7'd48;
 wire in_fire=in_valid&&in_ready;
 wire bad_input=in_fire&&(in_valid_bits!=6'd32 || in_last!=(words_left==12'd1));
 always @(posedge clk)begin
  if(!rst_n)begin
   buffer<=0;fill<=0;mode<=0;beat<=0;beat_total<=0;words_left<=0;
   busy<=0;done<=0;error<=0;total_cycles<=0;consumed_bits<=0;
  end else begin
   done<=0;
   if(start_valid&&start_ready)begin
    buffer<=0;fill<=0;mode<=start_w10?2'd2:(start_w12?2'd1:2'd0);beat<=0;
    beat_total<=start_x?11'd1600:11'd512;
    words_left<=valid_start?start_encoded_bits[16:5]:12'd0;
    total_cycles<=0;consumed_bits<=0;error<=!valid_start;busy<=valid_start;done<=!valid_start;
   end else if(busy)begin
    if(bad_input)begin busy<=0;done<=1;error<=1;end
    else begin
     if(out_fire)begin
      beat<=beat+11'd1;
      if(beat+11'd1==beat_total)begin busy<=0;done<=1;end
     end
     if(in_fire)begin
      buffer<=buffer_after_out|({64'b0,in_data}<<fill_after_out);
      fill<=fill_after_out+7'd32;
      words_left<=words_left-1'b1;
     end else begin
      buffer<=buffer_after_out;fill<=fill_after_out;
     end
    end
   end
  end
 end
 always @* out_last=busy&&(beat+11'd1==beat_total);
endmodule
`default_nettype wire

