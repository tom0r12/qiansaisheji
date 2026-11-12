`timescale 1ns/1ps
module tb_encoder_miter;
 reg clk=0;always #5 clk=~clk;
 reg rst_n=0,start_valid=0,in_valid=0,in_last=0,out_ready=0;
 reg [15:0] start_symbols=0;reg [2:0] start_k=0,in_count=0;
 reg start_delta=0;reg [8:0] start_row_bytes=16;
 reg [31:0] in_data=0;
 wire [1:0] start_ready,in_ready,out_valid,out_last,busy,done,error;
 wire [31:0] out_data[0:1],total_cycles[0:1],encoded_bits[0:1];
 wire [5:0] out_valid_bits[0:1];
 reference_encoder ref_dut(.clk,.rst_n,.start_valid,.start_ready(start_ready[0]),.start_symbols,.start_k,.start_delta,.start_row_bytes,
  .in_valid,.in_ready(in_ready[0]),.in_data,.in_count,.in_last,.out_valid(out_valid[0]),.out_ready,.out_data(out_data[0]),.out_valid_bits(out_valid_bits[0]),.out_last(out_last[0]),
  .busy(busy[0]),.done(done[0]),.error(error[0]),.total_cycles(total_cycles[0]),.encoded_bits(encoded_bits[0]));
 candidate_encoder dut(.clk,.rst_n,.start_valid,.start_ready(start_ready[1]),.start_symbols,.start_k,.start_delta,.start_row_bytes,
  .in_valid,.in_ready(in_ready[1]),.in_data,.in_count,.in_last,.out_valid(out_valid[1]),.out_ready,.out_data(out_data[1]),.out_valid_bits(out_valid_bits[1]),.out_last(out_last[1]),
  .busy(busy[1]),.done(done[1]),.error(error[1]),.total_cycles(total_cycles[1]),.encoded_bits(encoded_bits[1]));
 integer cycle=0,case_id=-1,frames=0,outputs=0,held_checks=0;
 reg dump_enable=0;string dump_path;
 initial if($value$plusargs("VCD=%s",dump_path))begin dump_enable=1;$dumpfile(dump_path);$dumpvars(0,tb_encoder_miter);end
 always @(posedge clk)begin
  cycle=cycle+1;
  if(cycle>100000)$fatal(1,"watchdog");
  if(rst_n)begin
   if({start_ready[0],in_ready[0],out_valid[0],out_last[0],busy[0],done[0],error[0],total_cycles[0],encoded_bits[0]}!==
      {start_ready[1],in_ready[1],out_valid[1],out_last[1],busy[1],done[1],error[1],total_cycles[1],encoded_bits[1]})begin
    $display("MISMATCH control case=%0d cycle=%0d ref_ready=%b dut_ready=%b ref_valid=%b dut_valid=%b ref_encoded=%0d dut_encoded=%0d ref_cycles=%0d dut_cycles=%0d",case_id,cycle,in_ready[0],in_ready[1],out_valid[0],out_valid[1],encoded_bits[0],encoded_bits[1],total_cycles[0],total_cycles[1]);
    $fatal(1,"encoder control differs");
   end
   if(out_valid[0]&&{out_data[0],out_valid_bits[0]}!=={out_data[1],out_valid_bits[1]})begin
    $display("MISMATCH payload case=%0d cycle=%0d ref=%h/%0d dut=%h/%0d",case_id,cycle,out_data[0],out_valid_bits[0],out_data[1],out_valid_bits[1]);
    $fatal(1,"encoder payload differs");
   end
   if(out_valid[0]&&out_ready)begin
    outputs=outputs+1;
    if(case_id==0&&(out_data[0]!==32'h000080bf||out_valid_bits[0]!==6'd9||!out_last[0]))$fatal(1,"independent raw single-byte golden differs");
   end
   if(out_valid[0]&&!out_ready)held_checks=held_checks+1;
  end
 end
 function automatic [7:0] value(input integer position,input integer pattern);
  case(pattern)
   0:value=8'h7f;
   1:value=8'(position*73+19);
   2:value=8'(position%16+3*(position/16));
   3:value=0;
   default:value=8'(position%2==0?128:127);
  endcase
 endfunction
 task automatic frame(input integer n,input integer k,input integer delta,input integer pattern,input integer stalls);
  integer sent,count,j,ticks;reg accept;
  begin
   case_id=frames;
   @(negedge clk);start_symbols=16'(n);start_k=3'(k);start_delta=delta!=0;start_row_bytes=16;start_valid=1;out_ready=0;
   @(posedge clk);if(!(&start_ready))$fatal(1,"not ready at start");
   @(negedge clk);start_valid=0;sent=0;ticks=0;
   while(!done[0])begin
    count=n-sent;if(count>4)count=4;
    in_valid=sent<n;in_count=3'(count);in_last=sent+count==n;in_data=0;
    for(j=0;j<count;j=j+1)in_data[j*8+:8]=value(sent+j,pattern);
    out_ready=stalls==0||((ticks%31)>=11);
    @(posedge clk);accept=in_valid&&in_ready[0];
    if(accept)sent=sent+count;
    #1;ticks=ticks+1;if(error[0]||ticks>20000)$fatal(1,"reference error/timeout");
    @(negedge clk);
   end
   in_valid=0;out_ready=0;frames=frames+1;
   $display("FRAME PASS id=%0d symbols=%0d k=%0d delta=%0d cycles=%0d",case_id,n,k,delta,total_cycles[0]);
  end
 endtask
 integer k,p;
 initial begin
  repeat(4)@(negedge clk);rst_n=1;
  frame(1,3,0,0,0);
  for(k=0;k<8;k=k+1)for(p=1;p<=4;p=p+1)begin
   frame(65,k,0,p,1);frame(96,k,1,p,1);
  end
  // Joint reset followed by new first-row epoch.
  @(negedge clk);rst_n=0;repeat(3)@(negedge clk);rst_n=1;
  frame(48,2,1,2,1);
  $display("PASS encoder frontend miter frames=%0d outputs=%0d held_checks=%0d",frames,outputs,held_checks);
  $finish;
 end
endmodule
