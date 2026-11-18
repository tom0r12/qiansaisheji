`timescale 1ns/1ps
module tb_v8_core;
 logic clk=0,rst_n=0; always #5 clk=~clk;
 logic begin_valid=0,begin_ready,x_valid=0,x_ready,w_valid=0,w_ready,meta_valid=0,meta_ready;
 logic [47:0] x_data=0,w_data=0;logic [31:0]meta_data=0;logic [51:0]out_data;
 logic [2:0]pair_group,pair_done_index;logic[1:0]pair_slot_base;
 logic x_done,pair_loaded,pair_done,out_valid,out_ready=1,busy,done,error;
 logic[3:0]out_tile;logic[8:0]out_word_index;
 logic[31:0]total_cycles,load_cycles,factor_cycles,cache_read_cycles,compute_cycles,store_cycles;
 reg[47:0]xm[0:1599],wm[0:4095];reg[31:0]mm[0:319],acc[0:25343];reg[51:0]gold[0:6335];
 integer nx=0,nw=0,nm=0,ny=0,ticks=0,stall_mode=0,abort_mode=0,aborts=0,bad_mode=0,seq_mode=0;
 logic xack=0,wack=0,mack=0,oldstall=0,feeding=0;logic[51:0]held_data;logic[3:0]held_tile;logic[8:0]held_index;
 string vroot="", directory="";

 q12_task4 dut(.*);

 task automatic load_vec(input string d);
  $readmemh({d,"/x.hex"},xm);$readmemh({d,"/w.hex"},wm);$readmemh({d,"/meta.hex"},mm);
  $readmemh({d,"/gold.hex"},gold);$readmemh({d,"/acc.hex"},acc);
  if(bad_mode==1)mm[0]=32'h00400000;
  if(bad_mode==2)mm[39]=32'h00000030;
 endtask

 task automatic run_one_task(input string d, input bit do_reset);
  load_vec(d);
  feeding=0; x_valid=0; w_valid=0; meta_valid=0;
  if(do_reset)begin
   rst_n=0; repeat(4)@(negedge clk); rst_n=1;
  end else begin
   @(negedge clk);
  end
  nx=0;nw=0;nm=0;ny=0;oldstall=0;ticks=0;
  wait(begin_ready);
  @(negedge clk); begin_valid=1; feeding=1;
  @(negedge clk); begin_valid=0;
  if(abort_mode!=0)begin
   wait(ny>=17);@(negedge clk);feeding=0;rst_n=0;
   repeat(3)@(negedge clk);nx=0;nw=0;nm=0;ny=0;oldstall=0;rst_n=1;
   wait(begin_ready);@(negedge clk);begin_valid=1;feeding=1;aborts=aborts+1;
   @(negedge clk);begin_valid=0;
  end
  wait(done);
  @(posedge clk);
  feeding=0; x_valid=0; w_valid=0; meta_valid=0;
  if(bad_mode!=0)begin
   if(!error||ny!=0||nm!=40||nw!=512||nx!=1600)$fatal(1,"invalid metadata not safely rejected");
   $display("PASS_ONE case=%s rejected=%0d outputs=%0d",d,bad_mode,ny);
  end else begin
   if(nx!=1600||nw!=4096||nm!=320||ny!=6336)$fatal(1,"counts mismatch nx=%0d nw=%0d nm=%0d ny=%0d",nx,nw,nm,ny);
   $display("PASS_ONE case=%s outputs=%0d aborts=%0d",d,ny*4,aborts);
  end
 endtask

 initial begin
  if(!$value$plusargs("VROOT=%s",vroot))$fatal(1,"missing VROOT");
  if($value$plusargs("CASE=%s",directory))begin end
  if($value$plusargs("STALL=%d",stall_mode))begin end
  if($value$plusargs("ABORT=%d",abort_mode))begin end
  if($value$plusargs("BAD=%d",bad_mode))begin end
  if($value$plusargs("SEQ=%d",seq_mode))begin end
  if(seq_mode!=0)begin
   // Continuous back-to-back tasks WITHOUT reset between tasks (赛题分项任务1(2): 连续任务验证)
   run_one_task({vroot,"/minmin"}, 1);
   run_one_task({vroot,"/maxmax"}, 0);
   run_one_task({vroot,"/minmax"}, 0);
   run_one_task({vroot,"/rne"},    0);
   run_one_task({vroot,"/random"}, 0);
   $display("PASS_SEQ tasks=5 total_outputs=%0d", 5*25344);
  end else begin
   run_one_task({vroot,"/",directory}, 1);
  end
  $finish;
 end

 always @(negedge clk)begin
  if(!rst_n||!feeding)begin x_valid=0;w_valid=0;meta_valid=0;out_ready=1;end
  else begin
   if(!x_valid||xack)begin x_valid=nx<1600 && (stall_mode==0||ticks%5!=0);x_data=nx<1600?xm[nx]:0;end
   if(!w_valid||wack)begin w_valid=nw<4096 && (stall_mode==0||ticks%11!=0);w_data=nw<4096?wm[nw]:0;end
   if(!meta_valid||mack)begin meta_valid=nm<320 && (stall_mode==0||ticks%13!=0);meta_data=nm<320?mm[nm]:0;end
   out_ready=stall_mode==0 || (ticks%7!=0 && ticks%17!=0);
  end
 end

 always @(posedge clk)begin
  ticks=ticks+1;xack=0;wack=0;mack=0;
  if(ticks>200000)$fatal(1,"timeout");
  if(rst_n&&feeding)begin
   if(x_valid&&x_ready)begin nx=nx+1;xack=1;end
   if(w_valid&&w_ready)begin nw=nw+1;wack=1;end
   if(meta_valid&&meta_ready)begin nm=nm+1;mack=1;end
   if(error&&bad_mode==0)$fatal(1,"unexpected error");
   if(oldstall && (!out_valid||out_data!==held_data||out_tile!==held_tile||out_word_index!==held_index))$fatal(1,"held output changed");
   oldstall=out_valid&&!out_ready;held_data=out_data;held_tile=out_tile;held_index=out_word_index;
   if(out_valid&&out_ready)begin
    if(out_data!==gold[ny]||out_tile!=ny/396||out_word_index!=ny%396)$fatal(1,"output mismatch n=%0d got=%h expected=%h index=%0d",ny,out_data,gold[ny],out_word_index);
    for(integer i=0;i<4;i=i+1)if($signed(dut.corrected[i])!==$signed(acc[ny*4+i]))$fatal(1,"acc mismatch n=%0d got=%0d expected=%0d",ny*4+i,$signed(dut.corrected[i]),$signed(acc[ny*4+i]));
    ny=ny+1;
   end
  end
 end
endmodule
