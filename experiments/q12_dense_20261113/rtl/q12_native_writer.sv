`timescale 1ns/1ps
`default_nettype none
// Full fixed-width signed matrix, with a value-independent linear bit address.
// There is no compression transform or variable-length representation.
module q12_native_writer #(parameter integer VALUE_BITS=10)(
 input wire clk,rst_n,
 input wire start_valid,output wire start_ready,
 input wire in_valid,output wire in_ready,input wire [51:0] in_data,
 input wire in_last,
 output wire out_valid,input wire out_ready,output wire [31:0] out_data,
 output wire out_last,output reg busy,done,error,
 output reg [31:0] total_cycles,output reg [9:0] output_words
);
 localparam integer UNIT_BITS=(VALUE_BITS%2!=0)?4:((VALUE_BITS%4!=0)?8:16);
 localparam integer CAPACITY=80/UNIT_BITS,WORD_UNITS=32/UNIT_BITS;
 localparam integer GROUP_UNITS=4*VALUE_BITS/UNIT_BITS;
 localparam integer COUNT_BITS=$clog2(CAPACITY+1);
 reg [79:0] data_q;
 reg [COUNT_BITS-1:0] units_q;
 reg [8:0] groups_q;
 wire [4*VALUE_BITS-1:0] incoming;
 wire [3:0] invalid_lane;
 for(genvar lane=0;lane<4;lane++)begin: lanes
  assign incoming[lane*VALUE_BITS+:VALUE_BITS]=in_data[lane*13+:VALUE_BITS];
  assign invalid_lane[lane]=(in_data[lane*13+:13] !=
     {{(13-VALUE_BITS){in_data[lane*13+VALUE_BITS-1]}},in_data[lane*13+:VALUE_BITS]});
 end
 wire take_out=out_valid && out_ready;
 wire [COUNT_BITS-1:0] remaining=take_out ?
   (units_q>=COUNT_BITS'(WORD_UNITS)?units_q-COUNT_BITS'(WORD_UNITS):{COUNT_BITS{1'b0}}):units_q;
 wire [79:0] residual=take_out?{32'b0,data_q[79:32]}:data_q;
 assign start_ready=!busy && units_q==0;
 assign out_valid=busy && (units_q>=COUNT_BITS'(WORD_UNITS) || (groups_q==396 && units_q!=0));
 assign out_data=data_q[31:0];
 assign out_last=(groups_q==396) && units_q<=COUNT_BITS'(WORD_UNITS);
 assign in_ready=busy && groups_q<396 && remaining<=COUNT_BITS'(CAPACITY-GROUP_UNITS);
 always @(posedge clk)begin
  if(!rst_n)begin
   data_q<=0;units_q<=0;groups_q<=0;busy<=0;done<=0;error<=0;total_cycles<=0;output_words<=0;
  end else begin
   done<=0;
   if(busy)total_cycles<=total_cycles+1'b1;
   if(take_out)begin
    data_q<=residual;units_q<=remaining;output_words<=output_words+1'b1;
    if(out_last)begin busy<=0;done<=1;end
   end
   if(in_valid && in_ready)begin
    data_q<=residual | ({{(80-4*VALUE_BITS){1'b0}},incoming} << (int'(remaining)*UNIT_BITS));
    units_q<=remaining+COUNT_BITS'(GROUP_UNITS);groups_q<=groups_q+1'b1;
    if((|invalid_lane) || (in_last != (groups_q==395)))begin
     busy<=0;error<=1;done<=1;units_q<=0;
    end
   end
   if(start_valid && start_ready)begin
    data_q<=0;units_q<=0;groups_q<=0;busy<=1;error<=0;total_cycles<=1;output_words<=0;
   end
  end
 end
endmodule
`default_nettype wire
