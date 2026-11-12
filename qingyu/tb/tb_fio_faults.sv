`timescale 1ns/1ps
// Inject transport faults through the public DMA interfaces. START must return
// an error without starting arithmetic; a later hardware reset must recover.
module tb_fio_faults;
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
 qingyu_icb_merge #(.NP(6)) merge(
  .clk(clk),.rst_n(rst_n),.s_cmd_valid(dv),.s_cmd_ready(dq),.s_cmd_read(dr),
  .s_cmd_addr(da),.s_cmd_wdata(dd),.s_cmd_wmask(dm),.s_rsp_valid(sv),.s_rsp_ready(sr),
  .s_rsp_err(se),.s_rsp_rdata(sd),.m_cmd_valid(mv),.m_cmd_ready(mq),.m_cmd_read(mread),
  .m_cmd_addr(ma),.m_cmd_wdata(md),.m_cmd_wmask(mm),.m_rsp_valid(mrv),.m_rsp_ready(mrr),
  .m_rsp_err(merr),.m_rsp_rdata(mdata));

 integer cycle=0,delay_left=0,inject_port=-1,scenario=0,matched=0,p,fused=0;
 integer private_x=0,private_w=0,abort_mode,watchdog,after_abort;
 reg pending=0,response_valid=0,response_error=0,injected=0;
 reg pending_read=0;
 reg [31:0] response_data=0;
 assign mq=rst_n&&!pending&&(cycle%5!=0);
 assign mrv=response_valid;assign merr=response_error;assign mdata=response_data;
 always @(posedge clk) begin
  cycle<=cycle+1;
  if(!rst_n)begin pending<=0;response_valid<=0;response_error<=0;injected<=0;delay_left<=0;private_x<=0;private_w<=0;end
  else begin
   if(dut.u_accel.input_write)private_x<=private_x+1;
   if(dut.u_accel.weight_write)private_w<=private_w+1;
   if(scenario>=7&&(dut.u_accel.input_write||dut.u_accel.weight_write)&&
      !(sv[0]&&sr[0]&&!se[0]))$fatal(1,"fused private commit without successful live write response");
   if(mv&&mq)begin
    pending<=1;pending_read<=mread;delay_left<=2+(cycle%5);response_valid<=0;response_error<=0;
    response_data<=(ma>=32'ha000c800&&ma<32'ha000c900)?32'h10101010:32'b0;
    matched=0;
    for(p=0;p<6;p=p+1)if(dv[p]&&dq[p])begin
     matched=matched+1;
     if(p==inject_port&&!injected)begin response_error<=1;injected<=1;end
    end
    if(matched!=1)$fatal(1,"missing fault-injection owner");
   end
   if(pending&&!response_valid)begin
    if(delay_left==0)response_valid<=1;
    else delay_left<=delay_left-1;
   end
   if(response_valid&&mrr)begin response_valid<=0;pending<=0;end
  end
 end

 task automatic reset_dut;
  begin
   @(negedge clk);rst_n=0;cv=0;rr=0;
   repeat(4)@(negedge clk);rst_n=1;
   repeat(3)@(negedge clk);
  end
 endtask
 task automatic write_csr(input [31:0] address,input [31:0] value,input bit expected_error);
  integer watchdog;reg [31:0] held;reg held_error;
  begin
   @(negedge clk);cv=1;cr=0;ca=address;cd=value;rr=0;
   watchdog=0;
   @(posedge clk);
   while(!cq)begin @(posedge clk);watchdog++;if(watchdog>5000)$fatal(1,"command timeout scenario=%0d addr=%h",scenario,address);end
   @(negedge clk);cv=0;
   watchdog=0;
   while(!rv)begin @(negedge clk);watchdog++;if(watchdog>5000)$fatal(1,"response timeout scenario=%0d addr=%h",scenario,address);end
   held=rd;held_error=re;
   repeat(3)begin @(negedge clk);if(!rv||rd!==held||re!==held_error)$fatal(1,"unstable control response");end
   if(held_error!==expected_error)$fatal(1,"wrong response scenario=%0d addr=%h err=%b",scenario,address,held_error);
   rr=1;@(negedge clk);rr=0;
  end
 endtask
 task automatic await_fault;
  integer watchdog;
  begin
   watchdog=0;
   while(!injected||pending)begin @(negedge clk);watchdog++;if(watchdog>5000)$fatal(1,"fault not drained");end
   repeat(20)@(negedge clk);
  end
 endtask
 initial begin
  if($value$plusargs("FUSED=%d",fused))begin end
  // Both staging ports, weight read, input read, metadata read, async copy read/write.
  for(scenario=0;scenario<(fused ? 11 : 7);scenario++)begin
   case(scenario)
    0:inject_port=5;1:inject_port=1;2:inject_port=3;3:inject_port=4;
    4:inject_port=3;5:inject_port=2;6:inject_port=0;
    7,9:inject_port=4;8,10:inject_port=0;
   endcase
   reset_dut();
   case(scenario)
    0,1:begin write_csr(32'hf00000b4,32'ha000c001,0);write_csr(32'hf00000b0,32'ha0004000,0);end
    2:write_csr(32'hf0000080,32'ha0004000,0);
    3:write_csr(32'hf0000090,32'ha0000000,0);
    4:begin write_csr(32'hf00000a4,32'ha000c800,0);write_csr(32'hf00000a8,32'ha000c000,0);write_csr(32'hf00000a0,0,0);end
    5,6:begin write_csr(32'hf00000bc,16,0);write_csr(32'hf00000c8,32'ha0000000,0);end
    7,8:write_csr(32'hf00000d4,32'ha0000000,0);
    9,10:write_csr(32'hf00000d8,32'ha0004000,0);
   endcase
   await_fault();
   write_csr(32'hf0000004,3,1);
   repeat(12)@(negedge clk);
   if(dut.accel_busy)$fatal(1,"failed START initiated arithmetic scenario=%0d",scenario);
   if(scenario>=7&&(private_x!=0||private_w!=0))$fatal(1,"fault committed a private operand");
   $display("PASS FIO fault scenario=%0d",scenario);
  end
  if(fused)begin
   inject_port=-1;
   for(abort_mode=0;abort_mode<2;abort_mode++)begin
    scenario=11+abort_mode;reset_dut();
    write_csr(32'hf00000d4,32'ha0000000,0);
    watchdog=0;
    while(!pending||pending_read!=(abort_mode==0))begin
     @(negedge clk);watchdog++;if(watchdog>5000)$fatal(1,"abort target not reached");
    end
    write_csr(32'hf0000004,4,0);
    after_abort=private_x;
    repeat(30)@(negedge clk);
    if(pending||(|dv)||private_x!=after_abort||dut.accel_busy)$fatal(1,"soft abort failed to drain/stop");
    // Clear the completed abort, then reload a full X matrix through the same
    // public command. The shared write and private commit must stay paired.
    write_csr(32'hf0000004,4,0);
    after_abort=private_x;
    write_csr(32'hf00000d4,32'ha0000000,0);
    watchdog=0;
    while(private_x-after_abort<3168)begin
     @(negedge clk);watchdog++;if(watchdog>100000)$fatal(1,"post-abort reload timeout");
    end
    repeat(20)@(negedge clk);
    if(private_x-after_abort!=3168||pending||(|dv))$fatal(1,"post-abort reload duplicate/unfinished");
    $display("PASS FIO soft abort mode=%0d reload_words=3168",abort_mode);
   end
  end
  inject_port=-1;reset_dut();write_csr(32'hf0000004,4,0);
  $display("PASS FIO transport faults and hardware-reset recovery");$finish;
 end
 initial begin #10000000;$fatal(1,"fault regression timeout");end
endmodule
