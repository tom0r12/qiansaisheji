`timescale 1ns/1ps
// Inject transport faults through the public DMA interfaces. START must return
// an error without starting arithmetic; a later hardware reset must recover.
module tb_fio_queue_faults;
 reg clk=0,rst_n=0;
 always #5 clk=~clk;
 reg cv=0,cr=0,rr=0;
 reg [31:0] ca=0,cd=0;
 wire cq,rv,re; wire [31:0] rd;
 wire [5:0] dv,dq,dr,sv,sr,se;
 wire [191:0] da,dd,sd;
 wire [23:0] dm;
 wire mv,mq,mread,mrv,mrr,merr;
 wire [31:0] ma,md,mdata; wire [3:0] mm;
 wire host_valid; wire [31:0] host_code;
 wire [31:0] unused0,unused1;
 assign dr[0]=0;assign dr[1]=0;assign dr[3]=1;assign dr[4]=1;assign dr[5]=1;
 assign dd[191:96]=0;
 assign dm[3:0]=4'hf;assign dm[7:4]=4'hf;assign dm[23:12]=0;
 assign sr[1:0]=2'b11;assign sr[5:3]=3'b111;
 qingyu_fio dut(
  .clk(clk),.rst_n(rst_n),.cpu_cmd_valid(1'b0),.cpu_cmd_read(1'b0),.cpu_cmd_addr(32'b0),
  .cpu_cmd_wdata(32'b0),.cpu_cmd_wmask(4'b0),.cpu_cmd_ready(),.cpu_rsp_valid(),
  .cpu_rsp_ready(1'b1),.cpu_rsp_err(),.cpu_rsp_rdata(),
  .mem_cmd_valid(dv[2]),.mem_cmd_ready(dq[2]),.mem_cmd_read(dr[2]),.mem_cmd_addr(da[95:64]),
  .mem_cmd_wdata(dd[95:64]),.mem_cmd_wmask(dm[11:8]),.mem_rsp_valid(sv[2]),
  .mem_rsp_ready(sr[2]),.mem_rsp_err(se[2]),.mem_rsp_rdata(sd[95:64]),
  .cw_cmd_valid(dv[0]),.cw_cmd_ready(dq[0]),.cw_cmd_addr(da[31:0]),.cw_cmd_wdata(dd[31:0]),
  .cw_rsp_valid(sv[0]),.cw_rsp_err(se[0]),
  .sw_cmd_valid(dv[1]),.sw_cmd_ready(dq[1]),.sw_cmd_addr(da[63:32]),.sw_cmd_wdata(dd[63:32]),
  .sw_rsp_valid(sv[1]),.sw_rsp_err(se[1]),
  .ld_cmd_valid(dv[3]),.ld_cmd_ready(dq[3]),.ld_cmd_addr(da[127:96]),
  .ld_rsp_valid(sv[3]),.ld_rsp_err(se[3]),.ld_rsp_rdata(sd[127:96]),
  .in_cmd_valid(dv[4]),.in_cmd_ready(dq[4]),.in_cmd_addr(da[159:128]),
  .in_rsp_valid(sv[4]),.in_rsp_err(se[4]),.in_rsp_rdata(sd[159:128]),
  .sr_cmd_valid(dv[5]),.sr_cmd_ready(dq[5]),.sr_cmd_addr(da[191:160]),
  .sr_rsp_valid(sv[5]),.sr_rsp_err(se[5]),.sr_rsp_rdata(sd[191:160]),
  .icb_cmd_valid(cv),.icb_cmd_ready(cq),.icb_cmd_read(cr),.icb_cmd_addr(ca),
  .icb_cmd_wdata(cd),.icb_cmd_wmask(4'hf),.icb_rsp_valid(rv),.icb_rsp_ready(rr),
  .icb_rsp_err(re),.icb_rsp_rdata(rd),.host_valid(host_valid),.host_code(host_code));
 qingyu_icb_merge #(.NP(6),.OUTSTANDING(4),.ONE_PER_PORT(6'b111111)) merge(
  .clk(clk),.rst_n(rst_n),.s_cmd_valid(dv),.s_cmd_ready(dq),.s_cmd_read(dr),
  .s_cmd_addr(da),.s_cmd_wdata(dd),.s_cmd_wmask(dm),.s_rsp_valid(sv),.s_rsp_ready(sr),
  .s_rsp_err(se),.s_rsp_rdata(sd),.m_cmd_valid(mv),.m_cmd_ready(mq),.m_cmd_read(mread),
  .m_cmd_addr(ma),.m_cmd_wdata(md),.m_cmd_wmask(mm),.m_rsp_valid(mrv),.m_rsp_ready(mrr),
  .m_rsp_err(merr),.m_rsp_rdata(mdata));


 reg allow_cmd=0,allow_writes=1;
 reg response_valid=0,response_error=0;
 reg [31:0] response_data=0;
 integer accepted=0,returned=0,qread=0,qwrite=0,qcount=0,private_count=0;
 integer owners[0:31]; reg [31:0] addresses[0:31];
 integer p,n,matched,owner_now,target,mode,before_private,watchdog;
 reg [5:0] was_blocked=0; reg [68:0] held_payload[0:5];
 reg merged_blocked=0;reg[68:0] merged_payload;
 assign mq=rst_n&&allow_cmd&&(allow_writes||mread);
 assign mrv=response_valid;assign merr=response_error;assign mdata=response_data;
 always @(posedge clk) begin
  if(!rst_n)begin
   accepted<=0;returned<=0;qread<=0;qwrite<=0;qcount<=0;private_count<=0;
   was_blocked<=0;merged_blocked<=0;
  end else begin
   for(p=0;p<6;p=p+1)begin
    if(was_blocked[p]&&(!dv[p]||{dr[p],da[32*p+:32],dd[32*p+:32],dm[4*p+:4]}!==held_payload[p]))
     $fatal(1,"withdrawn/changed FIO held offer target=%0d mode=%0d port=%0d",target,mode,p);
    was_blocked[p]<=dv[p]&&!dq[p];
    held_payload[p]<={dr[p],da[32*p+:32],dd[32*p+:32],dm[4*p+:4]};
   end
   if(merged_blocked&&(!mv||{mread,ma,md,mm}!==merged_payload))$fatal(1,"changed merged offer");
   merged_blocked<=mv&&!mq;merged_payload<={mread,ma,md,mm};
   if(dut.u_accel.input_write||dut.u_accel.weight_write)private_count<=private_count+1;
   if(dut.dma_stop&&(dut.u_accel.input_write||dut.u_accel.weight_write||dut.u_accel.meta_wr_en))
    $fatal(1,"private commit during cancellation");
   if(mv&&mq)begin
    matched=0;owner_now=-1;
    for(p=0;p<6;p=p+1)if(dv[p]&&dq[p])begin matched++;owner_now=p;end
    if(matched!=1)$fatal(1,"command missing unique source");
    if(qcount>=16)$fatal(1,"test queue overflow");
    owners[qwrite]<=owner_now;addresses[qwrite]<=ma;
    qwrite<=(qwrite+1)%32;accepted<=accepted+1;
   end
   if(mrv&&mrr)begin
    if(qcount==0)$fatal(1,"unexpected response");
    matched=0;
    for(p=0;p<6;p=p+1)if(sv[p]&&sr[p])begin
     matched++;if(p!=owners[qread])$fatal(1,"response owner mismatch");
    end
    if(matched!=1)$fatal(1,"response not consumed once");
    qread<=(qread+1)%32;returned<=returned+1;
   end
   case({mv&&mq,mrv&&mrr})2'b10:qcount<=qcount+1;2'b01:qcount<=qcount-1;default:begin end endcase
  end
 end
 task automatic reset_dut;
  begin
   @(negedge clk);rst_n=0;cv=0;rr=0;response_valid=0;allow_cmd=1;allow_writes=1;
   repeat(4)@(negedge clk);rst_n=1;repeat(3)@(negedge clk);
  end
 endtask
 task automatic write_csr(input[31:0] address,input[31:0] value,input bit expected_error);
  integer w;reg[31:0] held;reg err;
  begin
   @(negedge clk);cv=1;cr=0;ca=address;cd=value;rr=0;w=0;
   @(posedge clk);while(!cq)begin @(posedge clk);w++;if(w>2000)$fatal(1,"CSR accept timeout %h",address);end
   @(negedge clk);cv=0;w=0;
   while(!rv)begin @(negedge clk);w++;if(w>2000)$fatal(1,"CSR response timeout");end
   held=rd;err=re;
   repeat(3)begin @(negedge clk);if(!rv||rd!==held||re!==err)$fatal(1,"unstable CSR response");end
   if(err!==expected_error)$fatal(1,"CSR error target=%0d mode=%0d addr=%h expected=%b actual=%b",target,mode,address,expected_error,err);
   rr=1;@(negedge clk);rr=0;
  end
 endtask
 task automatic wait_accepts(input integer count);
  integer w;
  begin w=0;while(accepted<count)begin @(negedge clk);w++;if(w>2000)$fatal(1,"accept timeout");end end
 endtask
 task automatic respond(input bit error);
  integer w;
  begin
   w=0;while(qcount==0)begin @(negedge clk);w++;if(w>2000)$fatal(1,"response queue empty");end
   @(negedge clk);response_valid=1;response_error=error;
   response_data=(addresses[qread]>=32'ha000c800&&addresses[qread]<32'ha000c900)?32'h10101010:32'h00010001;
   @(posedge clk);w=0;while(!mrr)begin @(posedge clk);w++;if(w>2000)$fatal(1,"response blocked");end
   @(negedge clk);response_valid=0;response_error=0;
  end
 endtask
 task automatic metadata;
  begin write_csr(32'hf00000a4,32'ha001c800,0);write_csr(32'hf00000a8,32'ha001c000,0);write_csr(32'hf00000a0,0,0);end
 endtask
 task automatic staging;
  begin write_csr(32'hf00000b4,32'ha000c001,0);write_csr(32'hf00000b0,32'ha0004000,0);end
 endtask
 task automatic await_held(input integer port);
  integer w;
  begin
   w=0;while(!(dv[port]&&!dq[port]))begin @(negedge clk);w++;if(w>2000)$fatal(1,"held target absent %0d",port);end
   repeat(4)@(negedge clk);
   if(!dut.dma_hold_v[port])$fatal(1,"offer guard was not populated");
  end
 endtask
 initial begin
  for(mode=0;mode<2;mode++)for(target=0;target<6;target++)begin
   reset_dut();
   if(target==0||target==1)begin
    // Queue the read that creates the blocked write, then an independent
    // metadata read whose response will carry the injected error.
    allow_writes=0;
    if(target==0)write_csr(32'hf00000d4,32'ha0000000,0);else staging();
    wait_accepts(1);metadata();wait_accepts(2);respond(0);
   end else begin
    // A staging write is in flight while a different source offers a read.
    staging();wait_accepts(1);respond(0);wait_accepts(2);allow_cmd=0;
    case(target)
     2:begin write_csr(32'hf00000bc,16,0);write_csr(32'hf00000c8,32'ha0000000,0);end
     3:metadata();
     4:write_csr(32'hf00000d4,32'ha0000000,0);
     5:begin end
    endcase
   end
   await_held(target);before_private=private_count;
   if(mode==0)respond(1);else write_csr(32'hf0000004,5,0);
   repeat(4)@(negedge clk);
   if(!dv[target]||!dut.dma_hold_v[target])$fatal(1,"cancel dropped held command");
   if(!dut.fused_status[0])$fatal(1,"status hid an unfinished transport drain");
   write_csr(32'hf0000004,3,1);
   write_csr(32'hf00000d4,32'ha0000000,1);
   // RESET has priority over START, but it cannot forget old transactions.
   write_csr(32'hf0000004,5,0);
   write_csr(32'hf00000d4,32'ha0000000,1);
   allow_cmd=1;allow_writes=1;watchdog=0;
   while(!dut.dma_quiet||qcount!=0||(|dv))begin
    if(qcount!=0)respond(0);else @(negedge clk);
    watchdog++;if(watchdog>1000)$fatal(1,"cancel did not drain");
   end
   repeat(8)@(negedge clk);
   if(private_count!=before_private||dut.accel_busy||accepted!=returned)$fatal(1,"cancel polluted private state or leaked response");
   write_csr(32'hf0000004,4,0);
   if(dut.operation_error)$fatal(1,"quiet RESET did not clear faults");
   // A fresh descriptor must commit exactly its own read/write pair.
   n=accepted;write_csr(32'hf00000d4,32'ha0000000,0);wait_accepts(n+1);respond(0);
   wait_accepts(n+2);respond(0);repeat(2)@(negedge clk);
   if(private_count!=before_private+1)$fatal(1,"new descriptor lost or inherited old private writes");
   $display("PASS queue FIO held_port=%0d cancel_mode=%0d",target,mode);
  end
  // LD is internally shared. A blocked metadata offer must remain metadata
  // even if a later weight descriptor becomes the higher-priority requester.
  reset_dut();target=3;mode=2;allow_cmd=0;metadata();await_held(3);
  write_csr(32'hf0000080,32'ha0004000,0);
  if(!dut.wl_req||!dut.dma_hold_v[3]||dut.dma_hold_ld_wl)$fatal(1,"LD contention stimulus absent");
  allow_cmd=1;wait_accepts(1);
  if(owners[qread]!=3||addresses[qread]!=32'ha001c800)$fatal(1,"held metadata payload stolen by W");
  respond(0);repeat(2)@(negedge clk);
  if(private_count!=0||dut.wl_word!=0||!dut.meta_busy)$fatal(1,"metadata response misattributed to W");
  watchdog=0;
  while(dut.meta_busy||dut.wl_busy||!dut.dma_quiet||qcount!=0||(|dv))begin
   if(qcount!=0)respond(0);else @(negedge clk);
   watchdog++;if(watchdog>10000)$fatal(1,"LD contention did not complete");
  end
  if(private_count!=512||accepted!=548||returned!=548||dut.operation_error)$fatal(1,"LD contention lost/duplicated data");
  $display("PASS queue FIO held metadata owner survives later weight priority");
  $display("PASS queue FIO all six held offers, concurrent errors, soft reset, drain and reload");$finish;
 end
 initial begin #10000000;$fatal(1,"queue fault regression timeout");end
endmodule
