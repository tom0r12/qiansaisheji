`timescale 1ns/1ps
module tb_dma;
 reg clk=0;always #5 clk=~clk;
 reg rst=0,cv=0,cread=0,rr=1;reg[3:0]ca=0,cm=15;reg[31:0]cd=0;
 wire cr,rv,re;wire[31:0]rd;
 wire pv,pr,pread,psv,pse,psr;wire[31:0]pa,pd,psd;wire[3:0]pm;
 wire mv,mr,mread,msv,mse,msr;wire[31:0]ma,md;wire[3:0]mm;
 integer cycle=0,pt=0,ph=0,mt=0,mh=0,read_count=0,ack_count=0;
 integer announced=0,burst_reads=0; integer due[0:2047];
 integer mode=0,stall_until=0,start_mem=0,expected_count=0;
 reg[31:0]expected_base=0;reg[31:0]pq[0:2047];reg p_error[0:2047];
 reg pheld=0,mheld=0;reg[68:0]p_saved,m_saved;
 reg error_injected=0;
 wire pblock=cycle<stall_until;
 assign pr=!pblock&&(pread||cycle%5!=1);
 assign mr=(cycle%29>=13);
 assign psv=ph<pt&&cycle>=due[ph];
 assign psd=pq[ph];assign pse=psv&&p_error[ph];
 // In mode1, deliver a memory error exactly while the next GPIO request stalls.
 assign msv=mh<mt&&(cycle%31>=24);
 assign mse=msv&&(mode==1&&!error_injected);
 q12_gpio_dma dut(.clk(clk),.rst_n(rst),.c_valid(cv),.c_ready(cr),.c_read(cread),.c_addr(ca),.c_data(cd),.c_mask(cm),
 .r_valid(rv),.r_ready(rr),.r_error(re),.r_data(rd),
 .p_cmd_valid(pv),.p_cmd_ready(pr),.p_cmd_read(pread),.p_cmd_addr(pa),.p_cmd_wdata(pd),.p_cmd_wmask(pm),
 .p_rsp_valid(psv),.p_rsp_ready(psr),.p_rsp_err(pse),.p_rsp_rdata(psd),
 .m_cmd_valid(mv),.m_cmd_ready(mr),.m_cmd_read(mread),.m_cmd_addr(ma),.m_cmd_wdata(md),.m_cmd_wmask(mm),
 .m_rsp_valid(msv),.m_rsp_ready(msr),.m_rsp_err(mse),.m_rsp_rdata(32'b0),.ppi_lock(),.acked_words());
 function automatic[31:0]pattern(input integer n);pattern=(32'h13579bdf+32'(n)*32'h9e3779b9)^32'(n<<17);endfunction
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(!rst)begin pt<=0;ph<=0;mt<=0;mh<=0;read_count<=0;ack_count<=0;pheld<=0;mheld<=0;error_injected<=0;stall_until<=0;announced<=0;burst_reads<=0;end
  else begin
   if(pheld&&(!pv||{pread,pa,pd,pm}!==p_saved))$fatal(1,"GPIO request changed under backpressure/error");
   if(mheld&&(!mv||{mread,ma,md,mm}!==m_saved))$fatal(1,"memory request changed under backpressure");
   pheld<=pv&&!pr;p_saved<={pread,pa,pd,pm};mheld<=mv&&!mr;m_saved<={mread,ma,md,mm};
   if(pv&&pr)begin
    if(pm!=15||pa!==(pread?32'h10012004:32'h10040008))$fatal(1,"peripheral address/mask");
    if(pread)begin
     if(burst_reads>=announced)$fatal(1,"read without announced burst");
     pq[pt]<=pattern(read_count);read_count<=read_count+1;burst_reads<=burst_reads+1;
    end else begin
     if(burst_reads!=announced||pd[9:2]<1||pd[9:2]>64||pd[1]!==1'((ack_count+1)&1)||pd[31:10]!=0||pd[0]!=0)$fatal(1,"REQ/count mismatch");
     pq[pt]<=0;ack_count<=ack_count+1;announced<=pd[9:2];burst_reads<=0;
     if(mode==3&&ack_count==0)stall_until<=cycle+20;
    end
    due[pt]<=cycle+2;
    p_error[pt]<=mode==2&&pt==1;pt<=pt+1;
   end
   if(psv&&psr)ph<=ph+1;
   if(mv&&mr)begin
    if(mread||mm!=15||ma!==expected_base+32'((mt-start_mem)*4)||md!==pattern(mt))$fatal(1,"DMA memory data/address mismatch");
    mt<=mt+1;
   end
   if(msv&&msr)begin mh<=mh+1;if(mse)error_injected<=1;end
   if(pt-ph>4||mt-mh>48||dut.issued-dut.mem_responses>48)$fatal(1,"unbounded outstanding");
  end
  if(cycle>40000)$fatal(1,"timeout");
 end
 task automatic csr(input bit read,input[3:0]a,input[31:0]d,input bit want_error,output[31:0]value);
  begin
   @(negedge clk);rr=0;cv=1;cread=read;ca=a;cd=d;
   do @(posedge clk);while(!cr);
   @(negedge clk);cv=0;
   wait(rv);value=rd;if(re!==want_error)$fatal(1,"CSR response error mismatch a=%h got=%b",a,re);
   repeat(3)begin @(negedge clk);if(!rv||rd!==value||re!==want_error)$fatal(1,"CSR response changed under backpressure");end
   rr=1;
   @(posedge clk);@(negedge clk);
  end
 endtask
 reg[31:0]value;
 task automatic chunk(input[31:0]base,input integer n);
  begin
   expected_base=base;start_mem=mt;
   csr(0,0,base,0,value);csr(0,4,32'(n),0,value);
   if(n>=13)csr(0,0,32'hdeadbeef,1,value); // reject configuration mutation while busy
   csr(1,8,0,0,value);
   if(value!==(mode==0?32'd0:32'd2))$fatal(1,"completion/error status %h",value);
   if(ph!=pt||mh!=mt||dut.busy)$fatal(1,"completion before response drain");
   if(mode==0&&mt-start_mem!=n)$fatal(1,"chunk missing words");
  end
 endtask
 initial begin
  if($value$plusargs("MODE=%d",mode))begin end
  repeat(5)@(negedge clk);rst=1;
  csr(0,0,32'ha0040001,0,value);csr(0,4,13,1,value);
  csr(0,0,32'ha007fffc,0,value);csr(0,4,2,1,value);
  csr(0,0,32'ha0040000,0,value);csr(0,4,0,1,value);csr(0,4,8874,1,value);
  chunk(32'ha0040000,13);
  if(mode==0)begin
   chunk(32'ha0040034,19);
   chunk(32'ha0040080,1);chunk(32'ha0040084,15);chunk(32'ha00400c0,16);
   chunk(32'ha0040100,17);chunk(32'ha0040144,31);chunk(32'ha00401c0,32);
   chunk(32'ha0040400,64);chunk(32'ha0040800,65);chunk(32'ha0041000,200);chunk(32'ha0042000,129);
   // Cancel a partially active task using the shared bus reset, then restart.
   expected_base=32'ha0040080;start_mem=mt;
   csr(0,0,expected_base,0,value);csr(0,4,17,0,value);
   repeat(10)@(negedge clk);rst=0;repeat(4)@(negedge clk);rst=1;
   chunk(32'ha0040000,7);
  end
  if(mode==1&&!error_injected)$fatal(1,"missing stalled-request error injection");
  $display("PASS GPIO_DMA_PROTOCOL mode=%0d bounds busy_config backpressure ordered_response bursts_le64_overlapped_req tails drain reset_restart cadence_error",mode);
  $finish;
 end
endmodule


