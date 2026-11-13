`timescale 1ns/1ps
`default_nettype none
// Fixed-width output storage: four signed13 values become two 32-bit words.
// Every value has its own signed16 slot. No delta coding, entropy coding,
// variable lengths, omitted zeros, or data-dependent output traffic.
module q12_dense16_writer (
 input wire clk,rst_n,
 input wire start_valid,output wire start_ready,
 input wire in_valid,output wire in_ready,input wire [51:0] in_data,
 input wire in_last,
 output wire out_valid,input wire out_ready,output wire [31:0] out_data,
 output wire out_last,output reg busy,done,error,
 output reg [31:0] total_cycles,output reg [9:0] output_words
);
 reg [51:0] values_q;
 reg valid_q,half_q,last_q;
 reg [8:0] groups_q;
 wire [25:0] pair_data=half_q ? values_q[51:26] : values_q[25:0];
 assign out_data={{3{pair_data[25]}},pair_data[25:13],
                  {3{pair_data[12]}},pair_data[12:0]};
 assign out_valid=valid_q;
 assign out_last=valid_q && half_q && last_q;
 assign start_ready=!busy && !valid_q;
 // Simultaneous retirement/refill avoids a bubble between pairs of words.
 assign in_ready=busy && groups_q<9'd396 &&
                 (!valid_q || (half_q && out_ready));
 always @(posedge clk) begin
  if(!rst_n) begin
   values_q<=0;valid_q<=0;half_q<=0;last_q<=0;groups_q<=0;
   busy<=0;done<=0;error<=0;total_cycles<=0;output_words<=0;
  end else begin
   done<=0;
   if(busy)total_cycles<=total_cycles+1'b1;
   if(out_valid && out_ready)begin
    output_words<=output_words+1'b1;
    if(half_q)begin
     valid_q<=0;half_q<=0;
     if(last_q)begin busy<=0;done<=1;end
    end else half_q<=1;
   end
   if(in_valid && in_ready)begin
    values_q<=in_data;valid_q<=1;half_q<=0;last_q<=in_last;
    groups_q<=groups_q+1'b1;
    if(in_last != (groups_q==9'd395))begin
     valid_q<=0;busy<=0;error<=1;done<=1;
    end
   end
   if(start_valid && start_ready)begin
    busy<=1;error<=0;groups_q<=0;total_cycles<=1;output_words<=0;
    valid_q<=0;half_q<=0;last_q<=0;
   end
  end
 end
endmodule
`default_nettype wire
