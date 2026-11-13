`timescale 1ns/1ps
// Independent initialized-before-use monitor; never initializes DUT data.
module q12_data_init_check(
 input wire clk,rst_n,begin_fire,new_pair,error,metadata_fault,
 input wire w_fire,burst_write,meta_fire,metadata_grant,
 input wire [1:0] burst_fill_q,burst_drain_q,
 input wire [2:0] burst_fill_word_q,
 input wire [5:0] meta_count_q,
 input wire [4:0] meta_write_q
);
 reg [7:0] burst_seen[0:2];
 reg [31:0] bias_seen,shift_seen;
 integer bursts_checked,metadata_checked;
 always @(posedge clk) begin
  if(!rst_n || begin_fire)begin bursts_checked<=0;metadata_checked<=0;end
  else begin
   if(burst_write)begin
    if(burst_seen[burst_drain_q]!==8'hff)$fatal(1,"Burst read before complete initialization");
    bursts_checked<=bursts_checked+1;
   end
   if(metadata_grant)begin
    if(bias_seen[meta_write_q]!==1'b1 || shift_seen[meta_write_q]!==1'b1)$fatal(1,"Metadata read before initialization");
    metadata_checked<=metadata_checked+1;
   end
  end
  if(!rst_n || begin_fire || new_pair || error || metadata_fault)begin
   for(integer i=0;i<3;i=i+1)burst_seen[i]<=0;
  end else begin
   if(burst_write)burst_seen[burst_drain_q]<=0;
   if(w_fire)burst_seen[burst_fill_q][burst_fill_word_q]<=1;
  end
  if(!rst_n || begin_fire || new_pair)begin bias_seen<=0;shift_seen<=0;end
  else if(meta_fire)begin
   if(meta_count_q<32)bias_seen[meta_count_q[4:0]]<=1;
   else if(meta_count_q<40)shift_seen[{meta_count_q[2:0],2'b00}+:4]<=4'hf;
  end
 end
 final $display("Q12_DATA_INIT_CHECK bursts=%0d metadata=%0d",bursts_checked,metadata_checked);
endmodule
bind q12_task4 q12_data_init_check init_guard(.*);
