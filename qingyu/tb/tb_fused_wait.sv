`timescale 1ns/1ps
// Inject transport faults through the public DMA interfaces. START must return
// an error without starting arithmetic; a later hardware reset must recover.
module tb_fused_wait;
 localparam WAIT_LIMIT=256;
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
 qingyu_fio #(.FUSED_WAIT_TIMEOUT_CYCLES(WAIT_LIMIT)) dut(
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
 qingyu_icb_merge #(.NP(6)) merge(
  .clk(clk),.rst_n(rst_n),.s_cmd_valid(dv),.s_cmd_ready(dq),.s_cmd_read(dr),
  .s_cmd_addr(da),.s_cmd_wdata(dd),.s_cmd_wmask(dm),.s_rsp_valid(sv),.s_rsp_ready(sr),
  .s_rsp_err(se),.s_rsp_rdata(sd),.m_cmd_valid(mv),.m_cmd_ready(mq),.m_cmd_read(mread),
  .m_cmd_addr(ma),.m_cmd_wdata(md),.m_cmd_wmask(mm),.m_rsp_valid(mrv),.m_rsp_ready(mrr),
  .m_rsp_err(merr),.m_rsp_rdata(mdata));

 integer cycle=0,delay_left=0,inject_port=-1,p,matched;
 integer reads=0,writes=0,responses=0,private_x=0,private_w=0;
 integer stalls,before_reads,before_writes,mode,n,timeout_cycles;
 reg pending=0,response_valid=0,response_error=0,injected=0;
 reg stall_command=0,stall_response=0,long_delay=0;
 reg [31:0] response_data=0,value,held;
 assign mq=rst_n&&!pending&&!stall_command&&(cycle%5!=0);
 assign mrv=response_valid;assign merr=response_error;assign mdata=response_data;
 always @(posedge clk) begin
  cycle<=cycle+1;
  if(!rst_n) begin
   pending<=0;response_valid<=0;response_error<=0;injected<=0;delay_left<=0;
   reads<=0;writes<=0;responses<=0;private_x<=0;private_w<=0;
  end else begin
   if(dut.u_accel.input_write)private_x<=private_x+1;
   if(dut.u_accel.weight_write)private_w<=private_w+1;
   if(mv&&mq)begin
    pending<=1;delay_left<=long_delay?48:2+(cycle%5);response_valid<=0;response_error<=0;
    response_data<=ma ^ 32'h51a729c3;
    if(mread)reads<=reads+1;else writes<=writes+1;
    matched=0;
    for(p=0;p<6;p=p+1)if(dv[p]&&dq[p])begin
     matched=matched+1;
     if(p==inject_port&&!injected)begin response_error<=1;injected<=1;end
    end
    if(matched!=1)$fatal(1,"WAIT test missing DMA request owner");
   end
   if(pending&&!response_valid&&!stall_response)begin
    if(delay_left==0)response_valid<=1;else delay_left<=delay_left-1;
   end
   if(response_valid&&mrr)begin response_valid<=0;pending<=0;responses<=responses+1;end
  end
 end
 task automatic reset_dut;
  begin
   @(negedge clk);rst_n=0;cv=0;rr=0;stall_command=0;stall_response=0;long_delay=0;inject_port=-1;
   repeat(4)@(negedge clk);rst_n=1;repeat(3)@(negedge clk);
  end
 endtask
 task automatic csr_write(input [31:0] address,input [31:0] data);
  integer guard;
  begin
   @(negedge clk);cv=1;cr=0;ca=address;cd=data;rr=0;guard=0;
   @(posedge clk);while(!cq)begin @(posedge clk);guard++;if(guard>5000)$fatal(1,"write stalled");end
   @(negedge clk);cv=0;guard=0;
   while(!rv)begin @(negedge clk);guard++;if(guard>5000)$fatal(1,"write response stalled");end
   if(re)$fatal(1,"unexpected write ICB error addr=%h",address);
   rr=1;@(negedge clk);rr=0;
  end
 endtask
 task automatic csr_read(input [31:0] address,input integer backpressure,
                          output [31:0] data,output integer wait_cycles);
  integer guard;reg [31:0] snapshot;
  begin
   @(negedge clk);cv=1;cr=1;ca=address;cd=0;rr=0;wait_cycles=0;
   @(posedge clk);
   while(!cq)begin
    if(rv)$fatal(1,"response appeared before blocked WAIT command accepted");
    @(posedge clk);wait_cycles++;
    if(wait_cycles>WAIT_LIMIT+10)$fatal(1,"control WAIT failed its watchdog bound");
   end
   @(negedge clk);cv=0;guard=0;
   while(!rv)begin @(negedge clk);guard++;if(guard>20)$fatal(1,"WAIT response did not follow acceptance");end
   snapshot=rd;
   if(re)$fatal(1,"status error escaped as CPU ICB exception");
   repeat(backpressure)begin
    @(negedge clk);
    if(!rv||rd!==snapshot||re)$fatal(1,"WAIT response changed under backpressure");
   end
   data=snapshot;rr=1;@(negedge clk);rr=0;
  end
 endtask
 task automatic await_private(input bit weight_kind,input integer count);
  integer guard;
  begin
   guard=0;
   while((weight_kind?private_w:private_x)<count)begin
    @(negedge clk);guard++;
    if(guard>120000)$fatal(1,"data path failed to progress");
   end
  end
 endtask
 initial begin
  reset_dut();
  csr_read(32'hf00000d0,3,value,stalls);
  if(value!==32'h51462202)$fatal(1,"WAIT capability version mismatch");
  csr_read(32'hf00000dc,3,value,stalls);
  if(value[2:0]!==0||stalls!=0)$fatal(1,"legacy status read changed");
  // Normal full X and W transfers. Start WAIT near the end because this test
  // deliberately uses a 256-cycle watchdog, far below a complete matrix load.
  for(mode=0;mode<2;mode++)begin
   reset_dut();
   csr_write(mode?32'hf00000d8:32'hf00000d4,mode?32'ha0004000:32'ha0000000);
   await_private(mode!=0,mode?508:3164);
   before_reads=reads;before_writes=writes;
   csr_read(32'hf00000e0,7,value,stalls);
   if(stalls<1||value[2:0]!==3'b100)$fatal(1,"WAIT did not stall then report success");
   if(reads<=before_reads||writes<=before_writes)$fatal(1,"blocked control stopped DMA progress");
   if((mode?private_w:private_x)!=(mode?512:3168)||pending||(|dv))$fatal(1,"WAIT completed before data drain");
   $display("PASS WAIT success kind=%0d blocked_cycles=%0d",mode,stalls);
  end
  // Errors from both transfer phases return status data after drain, with no
  // successful private commit and no CPU ICB exception.
  for(mode=0;mode<4;mode++)begin
   reset_dut();inject_port=(mode%2)?0:4;
   csr_write(mode>=2?32'hf00000d8:32'hf00000d4,mode>=2?32'ha0004000:32'ha0000000);
   csr_read(32'hf00000e0,5,value,stalls);
   if(value[1:0]!==2'b10||value[15:8]!==((mode%2)?8'd2:8'd1))$fatal(1,"WAIT fault status wrong %h",value);
   if(private_x||private_w||pending||(|dv))$fatal(1,"WAIT error failed to drain");
   $display("PASS WAIT fault mode=%0d code=%0d",mode,value[15:8]);
  end
  // Snapshot stability even if another already-running loader changes the
  // aggregate fault status while this WAIT response is backpressured.
  reset_dut();inject_port=3;long_delay=1;
  csr_write(32'hf0000080,32'ha0004000);
  csr_read(32'hf00000e0,100,value,stalls);
  if(value[1]||!injected)$fatal(1,"snapshot timing scenario did not exercise status change");
  csr_read(32'hf00000dc,2,value,stalls);
  if(!value[1]||value[15:8]!=8'h12)$fatal(1,"legacy status did not expose subsequent error");
  $display("PASS WAIT snapshot stable across later fault");
  // Exercise a permanently blocked command and an accepted read whose response
  // never arrives. WAIT's watchdog must return, preserving DMA for later drain.
  for(mode=0;mode<2;mode++)begin
   reset_dut();stall_command=(mode==0);stall_response=(mode==1);
   csr_write(32'hf00000d4,32'ha0000000);
   before_reads=reads;
   csr_read(32'hf00000e0,9,value,timeout_cycles);
   if(value[1:0]!==2'b11||value[15:8]!==8'h80||timeout_cycles<WAIT_LIMIT-2||timeout_cycles>WAIT_LIMIT)
    $fatal(1,"WAIT timeout bound/status wrong mode=%0d cycles=%0d status=%h",mode,timeout_cycles,value);
   if(private_x)$fatal(1,"timed-out data was committed");
   if(mode==0&&!dv[4])$fatal(1,"timeout withdrew blocked request");
   if(mode==1&&!pending)$fatal(1,"timeout discarded accepted request");
   csr_write(32'hf0000004,4);
   stall_command=0;stall_response=0;
   csr_read(32'hf00000e0,4,value,stalls);
   if(value[1:0]!==2'b10||value[15:8]!==8'd3||pending||(|dv)||private_x)$fatal(1,"timeout abort failed drain");
   csr_write(32'hf0000004,4);
   csr_write(32'hf00000d8,32'ha0004000);
   await_private(1,508);
   csr_read(32'hf00000e0,4,value,stalls);
   if(value[2:0]!==3'b100||private_w!=512)$fatal(1,"timeout recovery reload failed");
   $display("PASS WAIT watchdog mode=%0d timeout_cycles=%0d reload_words=512",mode,timeout_cycles);
  end
  $display("PASS bounded WAIT_FUSED, independent DMA progress and stable status responses");
  $finish;
 end
 initial begin #20000000;$fatal(1,"WAIT test global timeout");end
endmodule

