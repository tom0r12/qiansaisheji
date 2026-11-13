`timescale 1ns/1ps
`default_nettype none
// Native signed12 matrix representation, packed consecutively into 32-bit
// bus words. Exactly 12 bits per element, independent of the value. No codec.
module q12_dense12_writer (
 input wire clk,rst_n,
 input wire start_valid,output wire start_ready,
 input wire in_valid,output wire in_ready,input wire [51:0] in_data,
 input wire in_last,
 output wire out_valid,input wire out_ready,output wire [31:0] out_data,
 output wire out_last,output reg busy,done,error,
 output reg [31:0] total_cycles,output reg [9:0] output_words
);
 reg [63:0] data_q;
 reg [6:0] bits_q;
 reg [8:0] groups_q;
 wire [47:0] incoming={in_data[50:39],in_data[37:26],in_data[24:13],in_data[11:0]};
 wire invalid_value=(in_data[51]!=in_data[50]) || (in_data[38]!=in_data[37]) ||
                    (in_data[25]!=in_data[24]) || (in_data[12]!=in_data[11]);
 wire take_out=out_valid && out_ready;
 wire [6:0] remaining=bits_q-(take_out?7'd32:7'd0);
 wire [63:0] residual=take_out?{32'b0,data_q[63:32]}:data_q;
 assign start_ready=!busy && bits_q==0;
 assign out_valid=busy && bits_q>=32;
 assign out_data=data_q[31:0];
 assign out_last=(groups_q==396) && bits_q==32;
 assign in_ready=busy && groups_q<396 && remaining<=16;
 always @(posedge clk)begin
  if(!rst_n)begin
   data_q<=0;bits_q<=0;groups_q<=0;busy<=0;done<=0;error<=0;
   total_cycles<=0;output_words<=0;
  end else begin
   done<=0;
   if(busy)total_cycles<=total_cycles+1'b1;
   if(take_out)begin
    data_q<=residual;bits_q<=remaining;output_words<=output_words+1'b1;
    if(out_last)begin busy<=0;done<=1;end
   end
   if(in_valid && in_ready)begin
    // remaining can only be 0 or 16: a small mux, not a variable shifter.
    data_q<=remaining==0 ? {16'b0,incoming} : {incoming,residual[15:0]};
    bits_q<=remaining+7'd48;groups_q<=groups_q+1'b1;
    if(invalid_value || (in_last != (groups_q==395)))begin
     busy<=0;error<=1;done<=1;bits_q<=0;
    end
   end
   if(start_valid && start_ready)begin
    data_q<=0;bits_q<=0;groups_q<=0;busy<=1;error<=0;
    total_cycles<=1;output_words<=0;
   end
  end
 end
endmodule
`default_nettype wire
