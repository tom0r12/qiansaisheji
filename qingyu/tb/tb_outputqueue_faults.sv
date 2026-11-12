`timescale 1ns/1ps
// Inject transport faults through the public DMA interfaces. START must return
// an error without starting arithmetic; a later hardware reset must recover.
module tb_outputqueue_faults;
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
 qingyu_icb_merge #(.NP(6),.OUTSTANDING(4),.ONE_PER_PORT(6'b111011)) merge(
  .clk(clk),.rst_n(rst_n),.s_cmd_valid(dv),.s_cmd_ready(dq),.s_cmd_read(dr),
  .s_cmd_addr(da),.s_cmd_wdata(dd),.s_cmd_wmask(dm),.s_rsp_valid(sv),.s_rsp_ready(sr),
  .s_rsp_err(se),.s_rsp_rdata(sd),.m_cmd_valid(mv),.m_cmd_ready(mq),.m_cmd_read(mread),
  .m_cmd_addr(ma),.m_cmd_wdata(md),.m_cmd_wmask(mm),.m_rsp_valid(mrv),.m_rsp_ready(mrr),
  .m_rsp_err(merr),.m_rsp_rdata(mdata));

 reg allow_cmd=1,allow_rsp=1,random_stalls=0;
 reg response_valid=0,response_error=0;
 reg [31:0] random_state=1;
 integer cycle=0,accepted=0,returned=0,qhead=0,qtail=0,qcount=0;
 integer ids[0:31],due[0:31],owners[0:31];
 integer scenario=0,seed=1,dummy,fault_at=-1,cmd_limit=100000;
 integer response_delay=7,peak=0,simultaneous=0,hold_checks=0;
 integer expected_words=792,errors=0,watchdog,mode,p,k,accepted_before,pops_after_reset;
 integer releases_seen=0,issue_id=0,consecutive=0,longest_burst=0,last_accept=-2;
 integer mem_count=0,owner_now=-1,owner_matches=0,fault_port=2;
 integer fault_accepts=0;
 reg stopped=0;
 reg [5:0] blocked=0;
 reg [68:0] held[0:5];
 reg [31:0] memory [0:32767];
 function automatic [31:0] expected_address(input integer word_id);
  expected_address=32'ha0010000+(word_id/792)*32+((word_id%792)/8)*512+(word_id%8)*4;
 endfunction
 function automatic [31:0] expected_data(input integer word_id);
  expected_data=32'h5310a987^(32'(word_id)*32'h9e3779b9);
 endfunction
 assign mq=rst_n&&allow_cmd&&accepted<cmd_limit&&qcount<8&&
           (!random_stalls||random_state[3:0]!=0);
 assign mrv=response_valid;
 assign merr=response_error;
 assign mdata=0;
 always @(negedge clk)begin
  random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
  if(!rst_n)begin response_valid=0;response_error=0;end
  else if(!response_valid||mrr)begin
   response_valid=allow_rsp&&qcount!=0&&cycle>=due[qhead]&&
                  (!random_stalls||random_state[7:5]!=0);
   response_error=qcount!=0&&owners[qhead]==fault_port&&ids[qhead]==fault_at;
  end
 end
 always @(posedge clk)begin
  cycle=cycle+1;
  if(!rst_n)begin
   accepted=0;returned=0;qhead=0;qtail=0;qcount=0;peak=0;errors=0;
   issue_id=0;blocked=0;releases_seen=0;stopped=0;simultaneous=0;mem_count=0;fault_accepts=0;
   last_accept=-2;consecutive=0;longest_burst=0;
  end else begin
   if(dut.mem_inflight!=mem_count)$fatal(1,"inflight mismatch dut=%0d ref=%0d",dut.mem_inflight,mem_count);
   if(dut.dma_quiet&&qcount!=0)$fatal(1,"false quiet with pending responses");
   for(p=0;p<6;p=p+1)begin
    if(blocked[p])begin
     hold_checks=hold_checks+1;
     if(!dv[p]||{dr[p],da[32*p+:32],dd[32*p+:32],dm[4*p+:4]}!==held[p])
      $fatal(1,"changed held command port=%0d scenario=%0d",p,scenario);
    end
    blocked[p]=dv[p]&&!dq[p];
    held[p]={dr[p],da[32*p+:32],dd[32*p+:32],dm[4*p+:4]};
   end
   if(mrv&&mrr)begin
    if(qcount==0||!sv[owners[qhead]]||!sr[owners[qhead]])$fatal(1,"response owner mismatch");
    for(p=0;p<6;p=p+1)if(p!=owners[qhead]&&sv[p])$fatal(1,"duplicate response owner");
    if(owners[qhead]==2)mem_count=mem_count-1;
    if(merr)begin errors=errors+1;stopped=1;end
    qhead=(qhead+1)%32;qcount=qcount-1;returned=returned+1;
   end
   if(mv&&mq)begin
    owner_matches=0;owner_now=-1;
    for(p=0;p<6;p=p+1)if(dv[p]&&dq[p])begin owner_matches++;owner_now=p;end
    if(owner_matches!=1)$fatal(1,"command has no unique owner");
    if(owner_now==2)begin
     if(mread||mm!=15)$fatal(1,"unexpected output command");
     if(ma!==expected_address(issue_id)||md!==expected_data(issue_id))
      $fatal(1,"output data/address word=%0d actual=%h/%h expected=%h/%h",issue_id,ma,md,expected_address(issue_id),expected_data(issue_id));
     if(!(fault_port==2&&issue_id==fault_at))memory[(ma-32'ha0010000)>>2]=md;
     ids[qtail]=issue_id;issue_id=issue_id+1;mem_count=mem_count+1;
    end else begin
     if(scenario!=9||owner_now!=3||!mread||ma!=32'ha000c800)$fatal(1,"unexpected concurrent metadata command");
     ids[qtail]=0;
    end
    owners[qtail]=owner_now;due[qtail]=cycle+response_delay;
    qtail=(qtail+1)%32;qcount=qcount+1;accepted=accepted+1;
    consecutive=last_accept==cycle-1 ? consecutive+1 : 1;
    if(consecutive>longest_burst)longest_burst=consecutive;
    last_accept=cycle;
   end
   if(mv&&mq&&mrv&&mrr)simultaneous=simultaneous+1;
   if(mv&&mq&&mrv&&mrr&&merr)fault_accepts=fault_accepts+1;
   if(qcount>peak)peak=qcount;
   if(qcount>4)$fatal(1,"output exceeded four outstanding");
   if(dut.aw_release)begin
    releases_seen=releases_seen+1;
    if(qcount!=0||stopped||errors!=0||returned!=(releases_seen%13==0?(releases_seen/13)*792:(releases_seen/13)*792+(releases_seen%13)*64))
     $fatal(1,"slot released before final successful response");
   end
  end
 end
 task automatic reset_dut;
  begin
   @(negedge clk);rst_n=0;cv=0;rr=0;allow_cmd=1;allow_rsp=1;
   cmd_limit=100000;fault_at=-1;fault_port=2;response_delay=7;
   repeat(4)@(negedge clk);rst_n=1;repeat(3)@(negedge clk);
  end
 endtask
 task automatic csr(input[31:0] address,input[31:0] data,input bit error_expected);
  integer w;
  begin
   @(negedge clk);cv=1;cr=0;ca=address;cd=data;rr=0;w=0;
   @(posedge clk);while(!cq)begin @(posedge clk);w=w+1;if(w>2000)$fatal(1,"CSR accept timeout %h",address);end
   @(negedge clk);cv=0;w=0;
   while(!rv)begin @(negedge clk);w=w+1;if(w>2000)$fatal(1,"CSR response timeout %h",address);end
   if(re!==error_expected)$fatal(1,"CSR error mismatch %h got=%b expected=%b",address,re,error_expected);
   rr=1;@(negedge clk);rr=0;
  end
 endtask
 task automatic wait_quiet;
  integer w;
  begin
   w=0;
   while(qcount!=0||!dut.dma_quiet||(|dv))begin
    @(negedge clk);w=w+1;if(w>10000)$fatal(1,"drain timeout scenario=%0d",scenario);
   end
   repeat(5)@(negedge clk);
  end
 endtask
 task automatic wait_words(input integer count);
  integer w;
  begin
   w=0;while(returned<count)begin @(negedge clk);w=w+1;if(w>20000)$fatal(1,"output timeout accepted=%0d returned=%0d",accepted,returned);end
   wait_quiet();
  end
 endtask
 task automatic clear_reference;
  begin
   @(negedge clk);
   if(qcount!=0||!dut.dma_quiet)$fatal(1,"clear before drain");
   accepted=0;returned=0;issue_id=0;releases_seen=0;errors=0;stopped=0;
   peak=0;simultaneous=0;fault_at=-1;fault_port=2;cmd_limit=100000;allow_rsp=1;allow_cmd=1;
  end
 endtask
 task automatic restart_and_check;
  begin
   csr(32'hf0000004,4,0);clear_reference();
   csr(32'hf00000c0,32'ha0010000,0);wait_words(792);
   if(accepted!=792||returned!=792||releases_seen!=13||dut.operation_error)$fatal(1,"restarted tile failed");
   for(k=0;k<792;k=k+1)if(memory[(expected_address(k)-32'ha0010000)>>2]!==expected_data(k))$fatal(1,"memory readback mismatch");
  end
 endtask
 initial begin
  dummy=$value$plusargs("SEED=%d",seed);random_state=32'(seed)|1;
  reset_dut();scenario=0;random_stalls=1;
  csr(32'hf00000c0,32'ha0010000,0);csr(32'hf00000c0,32'ha0010020,0);
  wait_words(1584);
  if(accepted!=1584||releases_seen!=26||peak!=4||simultaneous==0)$fatal(1,"two-tile coverage missing");
  for(k=0;k<1584;k=k+1)if(memory[(expected_address(k)-32'ha0010000)>>2]!==expected_data(k))$fatal(1,"full readback mismatch");
  $display("PASS outputqueue two tiles 99 rows, tail 3, random stalls seed=%0d peak=%0d overlap=%0d",seed,peak,simultaneous);
  reset_dut();scenario=1;random_stalls=0;response_delay=2;
  csr(32'hf00000c0,32'ha0010000,0);wait_words(792);
  if(longest_burst<32)$fatal(1,"saturated output did not issue every cycle burst=%0d",longest_burst);
  $display("PASS outputqueue saturated actual-command-accept burst=%0d",longest_burst);
  // Errors at the first, middle, and final write response. Queued responses
  // must drain without early slot release, and a subsequent reset recovers.
  for(mode=0;mode<3;mode=mode+1)begin
   reset_dut();scenario=2+mode;random_stalls=1;
   fault_at=mode==0?0:mode==1?19:791;
   csr(32'hf00000c0,32'ha0010000,0);
   watchdog=0;while(errors==0)begin @(negedge clk);watchdog++;if(watchdog>10000)$fatal(1,"missing injected error");end
   wait_quiet();if(!dut.operation_error||dut.aw_active||dut.aw_cnt!=0)$fatal(1,"error failed to cancel descriptor");
   csr(32'hf0000004,3,1);restart_and_check();
   $display("PASS outputqueue response error position=%0d drain and full restart",mode);
  end
  // Reset while zero/one/four writes are accepted; the zero/one cases also
  // deliberately retain an unaccepted offer across software cancellation.
  for(mode=0;mode<3;mode=mode+1)begin
   reset_dut();scenario=5+mode;random_stalls=0;allow_rsp=0;
   cmd_limit=mode==0?0:mode==1?1:4;
   csr(32'hf00000c0,32'ha0010000,0);
   watchdog=0;
   while(accepted<cmd_limit||(mode<2&&!dut.dma_hold_v[2]))begin
    @(negedge clk);watchdog++;if(watchdog>1000)$fatal(1,"reset stimulus missing");
   end
   csr(32'hf0000004,4,0);pops_after_reset=dut.u_accel.pops;
   csr(32'hf0000004,3,1);csr(32'hf00000c0,32'ha0010000,1);
   cmd_limit=100000;allow_rsp=1;wait_quiet();
   if(dut.u_accel.pops!=pops_after_reset||accepted!=returned)$fatal(1,"old output consumed reset stream or leaked response");
   restart_and_check();
   $display("PASS outputqueue soft reset inflight_case=%0d held offer drain and full restart",mode);
  end
  // Hardware reset cancels the whole bus. Already committed words survive.
  reset_dut();scenario=8;allow_rsp=0;csr(32'hf00000c0,32'ha0010000,0);
  while(accepted<4)@(negedge clk);
  reset_dut();if(memory[0]!==expected_data(0))$fatal(1,"hardware reset cleared committed storage");
  restart_and_check();
  $display("PASS outputqueue hardware reset and full restart");
  // Independent metadata failure while output data is accepted and another
  // output offer is held. Cancellation must preserve its original identity.
  reset_dut();scenario=9;random_stalls=0;allow_rsp=0;cmd_limit=4;fault_port=3;fault_at=0;
  csr(32'hf00000a4,32'ha000c800,0);csr(32'hf00000a8,32'ha000c000,0);csr(32'hf00000a0,0,0);
  while(accepted<1)@(negedge clk);
  csr(32'hf00000c0,32'ha0010000,0);
  watchdog=0;while(accepted<4||!dut.dma_hold_v[2])begin
   @(negedge clk);watchdog++;if(watchdog>1000)$fatal(1,"cross-owner held stimulus missing");
  end
  // All four merger entries are occupied. Making the target ready before
  // returning metadata's error forces its pop and the held output push on
  // the very same edge, testing cancellation against a real new acceptance.
  cmd_limit=100000;allow_rsp=1;while(errors==0)@(negedge clk);
  if(fault_accepts!=1||dut.mem_inflight!=4)$fatal(1,"metadata fault/new output acceptance did not coincide");
  wait_quiet();
  if(!dut.operation_error||accepted!=returned||releases_seen!=0)$fatal(1,"cross-owner error drain failure");
  restart_and_check();
  $display("PASS outputqueue independent metadata fault with held output and full restart");
  if(hold_checks==0)$fatal(1,"no held-payload checks");
  $display("PASS outputqueue all scenarios seed=%0d hold_checks=%0d",seed,hold_checks);$finish;
 end
 initial begin #10000000;$fatal(1,"outputqueue global timeout");end
endmodule


