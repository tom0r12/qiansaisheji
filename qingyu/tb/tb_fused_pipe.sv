`timescale 1ns/1ps
// Inject transport faults through the public DMA interfaces. START must return
// an error without starting arithmetic; a later hardware reset must recover.
module tb_fused_pipe;
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

 reg command_ready=0,response_valid=0,response_error=0;
 reg [31:0] response_data=0,random_state=1;
 reg q_is_read[0:7]; reg [31:0] q_addr[0:7];
 reg q_error[0:7];
 integer qr=0,qw=0,qc=0,reads=0,writes=0,commits=0,acks=0;
 integer cycles=0,mode=0,seed=0,testcase=0,expected_words=0,watchdog=0;
 integer overlap=0,full_fifo=0,read_index=0,write_index=0,p;
 reg weight_test=0,inject_read=0,inject_write=0,injected=0;
 reg [31:0] live_base=0;
 reg [5:0] was_blocked=0; reg [68:0] held_payload[0:5];
 function automatic [31:0] address_at(input integer word_index);
  address_at=live_base+(weight_test ? (word_index/8)*512+(word_index%8)*4 : word_index*4);
 endfunction
 function automatic [31:0] source_data(input [31:0] address);
  source_data=(address*32'h9e3779b9)^32'h3ad9c521^(address>>7);
 endfunction
 assign mq=command_ready;assign mrv=response_valid;
 assign merr=response_error;assign mdata=response_data;
 always @(negedge clk)begin
  if(!rst_n)begin command_ready=0;response_valid=0;response_error=0;end
  else begin
   random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
   command_ready=(random_state[3:0]!=0)&&qc<6;
   if(!response_valid||mrr)begin
    response_valid=qc!=0&&(random_state[6:4]!=0);
    response_error=qc!=0 ? q_error[qr] : 0;
    response_data=qc!=0&&q_is_read[qr] ? source_data(q_addr[qr]) : 0;
   end
  end
 end
 always @(posedge clk)begin
  if(!rst_n)begin
   qr<=0;qw<=0;qc<=0;reads<=0;writes<=0;commits<=0;acks<=0;
   cycles<=0;overlap<=0;full_fifo<=0;injected<=0;was_blocked<=0;
  end else begin
   cycles<=cycles+1;
   if(dut.dma_pending[4]&&dut.dma_pending[0])overlap<=overlap+1;
   if({1'b0,dut.fused_count}+{2'b0,dut.fused_read_wait}==3'd2)full_fifo<=full_fifo+1;
   if({1'b0,dut.fused_count}+{2'b0,dut.fused_read_wait}>3'd2)$fatal(1,"FIFO reservation overflow");
   for(p=0;p<6;p++)begin
    if(was_blocked[p]&&(!dv[p]||{dr[p],da[32*p+:32],dd[32*p+:32],dm[4*p+:4]}!==held_payload[p]))
     $fatal(1,"changed held payload port=%0d",p);
    was_blocked[p]<=dv[p]&&!dq[p];
    held_payload[p]<={dr[p],da[32*p+:32],dd[32*p+:32],dm[4*p+:4]};
   end
   if(mv&&mq)begin
    q_is_read[qw]<=mread;q_addr[qw]<=ma;
    q_error[qw]<=(mread&&inject_read&&reads==17)||(!mread&&inject_write&&writes==17);
    if((mread&&inject_read&&reads==17)||(!mread&&inject_write&&writes==17))injected<=1;
    qw<=(qw+1)%8;
    if(mread)begin
     if(!dv[4]||!dq[4]||ma!==address_at(reads)+32'h40000||reads>=expected_words)
      $fatal(1,"source read sequence mismatch index=%0d addr=%h",reads,ma);
     reads<=reads+1;
    end else begin
     if(!dv[0]||!dq[0]||ma!==address_at(writes)||md!==source_data(ma+32'h40000)||mm!==4'hf||writes>=expected_words)
      $fatal(1,"live write mismatch index=%0d addr=%h data=%h",writes,ma,md);
     writes<=writes+1;
    end
   end
   if(mrv&&mrr)begin
    if(qc==0)$fatal(1,"response with no request");
    qr<=(qr+1)%8;
   end
   case({mv&&mq,mrv&&mrr})2'b10:qc<=qc+1;2'b01:qc<=qc-1;default:begin end endcase
   if(sv[0]&&sr[0]&&!se[0])acks<=acks+1;
   if(dut.u_accel.input_write||dut.u_accel.weight_write)begin
    if(!(sv[0]&&sr[0]&&!se[0])||dut.dma_stop)$fatal(1,"private commit before successful live ACK");
    if(weight_test)begin
     if(!dut.u_accel.weight_write||dut.u_accel.input_write||dut.u_accel.weight_pair!==commits%8||
        dut.u_accel.weight_k!==commits/8||dut.u_accel.weight_word!==source_data(address_at(commits)+32'h40000))
      $fatal(1,"private W payload/index mismatch %0d",commits);
    end else begin
     if(!dut.u_accel.input_write||dut.u_accel.weight_write||dut.u_accel.input_elem!==commits*2||
        {dut.u_accel.input_data_hi,dut.u_accel.input_data}!==source_data(address_at(commits)+32'h40000))
      $fatal(1,"private X payload/index mismatch %0d",commits);
    end
    commits<=commits+1;
   end
  end
 end
 task automatic write_csr(input[31:0] address,input[31:0] value);
  integer w;
  begin
   @(negedge clk);cv=1;cr=0;ca=address;cd=value;rr=0;w=0;
   @(posedge clk);while(!cq)begin @(posedge clk);w++;if(w>2000)$fatal(1,"CSR accept timeout");end
   @(negedge clk);cv=0;w=0;
   while(!rv)begin @(negedge clk);w++;if(w>2000)$fatal(1,"CSR response timeout");end
   if(re)$fatal(1,"unexpected control error");
   rr=1;@(negedge clk);rr=0;
  end
 endtask
 initial begin
  for(seed=1;seed<=3;seed++)for(mode=0;mode<3;mode++)for(testcase=0;testcase<2;testcase++)begin
   @(negedge clk);rst_n=0;cv=0;rr=0;
   random_state=32'hc419d351^seed;
   weight_test=testcase!=0;inject_read=mode==1;inject_write=mode==2;
   live_base=weight_test ? 32'ha0004020 : 32'ha0000000;
   expected_words=weight_test ? 512 : 3168;
   repeat(4)@(negedge clk);rst_n=1;repeat(3)@(negedge clk);
   write_csr(weight_test ? 32'hf00000d8 : 32'hf00000d4,live_base);
   watchdog=0;
   while(dut.fused_busy||!dut.dma_quiet||qc!=0||(|dv))begin
    @(negedge clk);watchdog++;if(watchdog>100000)$fatal(1,"pipeline failed to drain");
   end
   repeat(4)@(negedge clk);
   if(mode==0)begin
    if(reads!=expected_words||writes!=expected_words||commits!=expected_words||acks!=expected_words||
       !dut.fused_done||dut.operation_error||overlap==0||full_fifo==0)
     $fatal(1,"incomplete pipeline read=%0d write=%0d commit=%0d ack=%0d overlap=%0d full=%0d",reads,writes,commits,acks,overlap,full_fifo);
   end else if(!injected||!dut.operation_error||dut.fused_done||commits>=expected_words)
    $fatal(1,"fault did not terminate pipeline safely");
   $display("PASS fused pipeline seed=%0d mode=%0d weight=%0d reads=%0d writes=%0d commits=%0d overlap=%0d",seed,mode,weight_test,reads,writes,commits,overlap);
  end
  $display("PASS fused pipeline ordering, full buffers, concurrent requests and mid-stream errors");$finish;
 end
 initial begin #50000000;$fatal(1,"pipeline regression timeout");end
endmodule


