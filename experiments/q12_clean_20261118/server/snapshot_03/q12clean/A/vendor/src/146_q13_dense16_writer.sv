`timescale 1ns/1ps
`default_nettype none
// Uncompressed output: four signed Y13 values become two little-endian
// 32-bit words. Each signed value occupies a sign-extended 16-bit halfword.
module q13_dense16_writer (
 input wire clk,rst_n,
 input wire start_valid,output wire start_ready,
 input wire [15:0] start_symbols,
 input wire in_valid,output wire in_ready,
 input wire [51:0] in_data,input wire [2:0] in_count,input wire in_last,
 output wire out_valid,input wire out_ready,output wire [31:0] out_data,
 output wire [5:0] out_valid_bits,output wire out_last,
 output reg busy,done,error,
 output reg [31:0] total_cycles,
 output reg [15:0] stored_symbols,output reg [9:0] output_words
);
 reg [63:0] pending_data;
 reg [1:0] pending_words;
 reg pending_last;
 reg [15:0] symbol_total,received_symbols;
 wire output_fire=out_valid&&out_ready;
 wire input_fire=in_valid&&in_ready;
 assign start_ready=rst_n&&!busy;
 assign out_valid=rst_n&&busy&&(pending_words!=0);
 assign out_data=pending_data[31:0];
 assign out_valid_bits=6'd32;
 assign out_last=pending_last&&(pending_words==1);
 assign in_ready=rst_n&&busy&&(received_symbols<symbol_total)&&
                 (pending_words==0 || (pending_words==1&&out_ready));
 wire bad_input=input_fire&&(in_count!=4 ||
                in_last!=(received_symbols+16'd4==symbol_total));
 always @(posedge clk)begin
  if(!rst_n)begin
   busy<=0;done<=0;error<=0;total_cycles<=0;stored_symbols<=0;output_words<=0;
   pending_data<=0;pending_words<=0;pending_last<=0;symbol_total<=0;received_symbols<=0;
  end else begin
   done<=0;
   if(busy)total_cycles<=total_cycles+1'b1;
   if(start_valid&&start_ready)begin
    total_cycles<=0;stored_symbols<=0;output_words<=0;received_symbols<=0;
    pending_data<=0;pending_words<=0;pending_last<=0;symbol_total<=start_symbols;
    error<=start_symbols==0 || start_symbols>1584 || start_symbols[1:0]!=0;
    busy<=start_symbols!=0 && start_symbols<=1584 && start_symbols[1:0]==0;
    done<=start_symbols==0 || start_symbols>1584 || start_symbols[1:0]!=0;
   end
   if(output_fire)begin
    pending_data<={32'b0,pending_data[63:32]};pending_words<=pending_words-1'b1;
    output_words<=output_words+1'b1;stored_symbols<=stored_symbols+16'd2;
    if(out_last)begin busy<=0;done<=1;end
   end
   if(input_fire)begin
    pending_data<={{3{in_data[51]}},in_data[51:39],{3{in_data[38]}},in_data[38:26],
                  {3{in_data[25]}},in_data[25:13],{3{in_data[12]}},in_data[12:0]};
    pending_words<=2;pending_last<=in_last;received_symbols<=received_symbols+16'd4;
   end
   if(bad_input)begin busy<=0;done<=1;error<=1;pending_words<=0;end
  end
 end
endmodule
`default_nettype wire
