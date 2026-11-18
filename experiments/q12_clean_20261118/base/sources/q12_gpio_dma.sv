// Original GPIOA/B register interfaces, synchronizers and APB stay intact.
// REQ[1], COUNT[6:2] announce <=16 words; external source sends one 32-bit
// word every 26.664 ns (150 MHz), first after 0.5..3 ns. No pad tap.
// Reserve whole burst, drain CPU PPI first. Unexpected in-burst stalls
// flag an error. Shared-memory stalls are absorbed by the reserved FIFO.
module q12_gpio_dma(
 input wire clk,rst_n,
 input wire c_valid,c_read,input wire[3:0]c_addr,c_mask,input wire[31:0]c_data,
 output wire c_ready,output reg r_valid,r_error,output reg[31:0]r_data,input wire r_ready,
 output wire p_cmd_valid,p_cmd_read,output wire[31:0]p_cmd_addr,p_cmd_wdata,output wire[3:0]p_cmd_wmask,
 input wire p_cmd_ready,p_rsp_valid,p_rsp_err,input wire[31:0]p_rsp_rdata,output wire p_rsp_ready,
 output wire m_cmd_valid,m_cmd_read,output wire[31:0]m_cmd_addr,m_cmd_wdata,output wire[3:0]m_cmd_wmask,
 input wire m_cmd_ready,m_rsp_valid,m_rsp_err,input wire[31:0]m_rsp_rdata,output wire m_rsp_ready
);
 localparam SELECT=0,REQUEST=1,WAIT_REQ=2,READ=3,DRAIN=4;
 reg busy,error_q,req_level;
 reg[2:0]phase;
 reg[1:0]cooldown;
 reg[4:0]burst_count,burst_issued;
 reg[31:0]destination;
 reg[13:0]length,issued,received,mem_issued,mem_responses;
 reg[31:0]fifo[0:15];
 assign p_cmd_valid=busy&&(phase==REQUEST||(phase==READ&&cooldown==0));
 assign p_cmd_read=phase!=REQUEST;
 assign p_cmd_addr=p_cmd_read?32'h10012004:32'h10040008;
 assign p_cmd_wdata=p_cmd_read?0:{25'b0,burst_count,~req_level,1'b0};
 assign p_cmd_wmask=4'hf;
 assign p_rsp_ready=1;
 assign m_cmd_valid=busy&&mem_issued<received;
 assign m_cmd_read=0;
 assign m_cmd_addr=destination+{16'b0,mem_issued,2'b0};
 assign m_cmd_wdata=fifo[mem_issued[3:0]];
 assign m_cmd_wmask=4'hf;
 assign m_rsp_ready=1;
 assign c_ready=!r_valid&&!(c_read&&c_addr==8&&busy);
 wire[32:0]end_address={1'b0,destination}+({1'b0,c_data}<<2);
 wire valid_length=c_data>0&&c_data<=8873&&destination>=32'ha0040000&&
                   destination[1:0]==0&&end_address<=33'h0a0080000;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   busy<=0;error_q<=0;req_level<=0;phase<=SELECT;cooldown<=0;
   burst_count<=0;burst_issued<=0;destination<=0;length<=0;
   issued<=0;received<=0;mem_issued<=0;mem_responses<=0;
   r_valid<=0;r_error<=0;r_data<=0;
  end else begin
   if(r_valid&&r_ready)r_valid<=0;
   if(c_valid&&c_ready)begin
    r_valid<=1;r_error<=0;r_data<=0;
    if(c_read)case(c_addr)
     0:r_data<=destination;
     4:r_data<={18'b0,length};
     8:r_data<={30'b0,error_q,busy};
     12:r_data<={18'b0,mem_responses};
     default:r_error<=1;
    endcase
    else if(c_mask!=4'hf||busy)r_error<=1;
    else case(c_addr)
     0:destination<=c_data;
     4:if(!valid_length)r_error<=1;
       else begin
        busy<=1;error_q<=0;length<=c_data[13:0];phase<=SELECT;
        issued<=0;received<=0;mem_issued<=0;mem_responses<=0;
       end
     default:r_error<=1;
    endcase
   end
   if(busy&&phase==SELECT)begin
    if(error_q||issued==length)busy<=0;
    else if(mem_responses==issued)begin
     burst_count<=length-issued>=16?5'd16:5'(length-issued);
     burst_issued<=0;phase<=REQUEST;
    end
   end
   if(p_cmd_valid&&p_cmd_ready)begin
    if(phase==REQUEST)phase<=WAIT_REQ;
    else begin
     issued<=issued+1'b1;burst_issued<=burst_issued+1'b1;cooldown<=3;
     if(burst_issued+1==burst_count)phase<=DRAIN;
    end
   end else if(phase==READ&&cooldown!=0)cooldown<=cooldown-1'b1;
   // A fixed-rate source cannot pause inside an announced burst.
   if(phase==READ&&cooldown==0&&!p_cmd_ready)error_q<=1;
   if(p_rsp_valid)begin
    if(p_rsp_err)error_q<=1;
    if(phase==WAIT_REQ)begin req_level<=~req_level;phase<=READ;cooldown<=0;end
    else begin fifo[received[3:0]]<=p_rsp_rdata;received<=received+1'b1;end
   end
   if(m_cmd_valid&&m_cmd_ready)mem_issued<=mem_issued+1'b1;
   if(m_rsp_valid)begin mem_responses<=mem_responses+1'b1;if(m_rsp_err)error_q<=1;end
   if(phase==DRAIN&&received==issued&&mem_responses==issued)phase<=SELECT;
  end
 end
endmodule

// CPU work fully drains before granting ONE finite GPIO burst. A waiting
// CPU wins the next boundary. Original peripheral and bus modules unchanged.
module q12_gpio_ppi_arbiter(
 input wire clk,rst_n,
 input wire[1:0]s_cmd_valid,s_cmd_read,output wire[1:0]s_cmd_ready,
 input wire[63:0]s_cmd_addr,s_cmd_wdata,input wire[7:0]s_cmd_wmask,
 output wire[1:0]s_rsp_valid,s_rsp_err,input wire[1:0]s_rsp_ready,
 output wire[63:0]s_rsp_rdata,
 output wire m_cmd_valid,m_cmd_read,input wire m_cmd_ready,
 output wire[31:0]m_cmd_addr,m_cmd_wdata,output wire[3:0]m_cmd_wmask,
 input wire m_rsp_valid,m_rsp_err,output wire m_rsp_ready,input wire[31:0]m_rsp_rdata
);
 localparam IDLE=0,CPU_CMD=1,CPU_RSP=2,DMA=3;
 reg[1:0]state;
 reg[5:0]target,responses;
 wire dma=state==DMA;
 wire send_cmd=state==CPU_CMD||dma;
 wire receive_rsp=state==CPU_RSP||dma;
 assign m_cmd_valid=send_cmd&&s_cmd_valid[dma];
 assign s_cmd_ready={dma&&m_cmd_ready,state==CPU_CMD&&m_cmd_ready};
 assign m_cmd_read=dma?s_cmd_read[1]:s_cmd_read[0];
 assign m_cmd_addr=dma?s_cmd_addr[63:32]:s_cmd_addr[31:0];
 assign m_cmd_wdata=dma?s_cmd_wdata[63:32]:s_cmd_wdata[31:0];
 assign m_cmd_wmask=dma?s_cmd_wmask[7:4]:s_cmd_wmask[3:0];
 assign s_rsp_valid={dma&&m_rsp_valid,state==CPU_RSP&&m_rsp_valid};
 assign s_rsp_err={2{m_rsp_err}};
 assign s_rsp_rdata={2{m_rsp_rdata}};
 assign m_rsp_ready=receive_rsp&&s_rsp_ready[dma];
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=IDLE;target<=0;responses<=0;end
  else case(state)
   IDLE:if(s_cmd_valid[0])state<=CPU_CMD;else if(s_cmd_valid[1])begin state<=DMA;target<=0;responses<=0;end
   CPU_CMD:if(m_cmd_valid&&m_cmd_ready)state<=CPU_RSP;
   CPU_RSP:if(m_rsp_valid&&m_rsp_ready)state<=IDLE;
   DMA:begin
    if(m_cmd_valid&&m_cmd_ready&&!m_cmd_read)target<={1'b0,m_cmd_wdata[6:2]}+1'b1;
    if(m_rsp_valid&&m_rsp_ready)begin
     responses<=responses+1'b1;
     if(responses+1==target)state<=IDLE;
    end
   end
  endcase
 end
endmodule
