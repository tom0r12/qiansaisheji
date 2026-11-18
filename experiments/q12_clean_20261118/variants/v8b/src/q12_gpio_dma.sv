// Original GPIOA/B register interfaces, synchronizers and APB stay intact.
// REQ = GPIOB[1] (toggle), COUNT = GPIOB[9:2] announce 1..MAX_BURST words;
// the external source then sends one 32-bit word every 26.664 ns (4 cycles
// at 150 MHz), first after 0.5..3 ns. No pad tap: every word is read through
// the original GPIOA input register over the original APB.
// v2 changes: bursts up to MAX_BURST words; the next REQ is issued right after
// the last read of the current burst (no wait for shared-memory drain); the
// 16-entry FIFO absorbs shared-memory stalls and flags overflow as an error.
module q12_gpio_dma #(parameter integer MAX_BURST=64)(
 input wire clk,rst_n,
 input wire c_valid,c_read,input wire[3:0]c_addr,c_mask,input wire[31:0]c_data,
 output wire c_ready,output reg r_valid,r_error,output reg[31:0]r_data,input wire r_ready,
 output wire p_cmd_valid,p_cmd_read,output wire[31:0]p_cmd_addr,p_cmd_wdata,output wire[3:0]p_cmd_wmask,
 input wire p_cmd_ready,p_rsp_valid,p_rsp_err,input wire[31:0]p_rsp_rdata,output wire p_rsp_ready,
 output wire m_cmd_valid,m_cmd_read,output wire[31:0]m_cmd_addr,m_cmd_wdata,output wire[3:0]m_cmd_wmask,
 input wire m_cmd_ready,m_rsp_valid,m_rsp_err,input wire[31:0]m_rsp_rdata,output wire m_rsp_ready,
 output wire ppi_lock,
 output wire [13:0] acked_words
);
 localparam [1:0] SELECT=0,REQUEST=1,WAIT_REQ=2,READ=3;
 reg busy,error_q,req_level;
 reg[1:0]phase;
 reg[1:0]cooldown;
 reg[7:0]burst_count,burst_issued;
 reg[31:0]destination;
 reg[13:0]length,issued,received,mem_issued,mem_responses;
 reg[31:0]fifo[0:7];
 wire[13:0]remaining=length-issued;
 wire[7:0]next_count=remaining>=14'(MAX_BURST)?8'(MAX_BURST):remaining[7:0];
 assign ppi_lock=busy;
 assign acked_words=mem_responses;
 // Never withdraw an offered command: an announced burst always completes.
 assign p_cmd_valid=busy&&(phase==REQUEST||(phase==READ&&cooldown==0));
 assign p_cmd_read=phase!=REQUEST;
 assign p_cmd_addr=p_cmd_read?32'h10012004:32'h10040008;
 assign p_cmd_wdata=p_cmd_read?32'b0:{22'b0,burst_count,~req_level,1'b0};
 assign p_cmd_wmask=4'hf;
 assign p_rsp_ready=1'b1;
 assign m_cmd_valid=busy&&mem_issued!=received;
 assign m_cmd_read=1'b0;
 assign m_cmd_addr=destination+{16'b0,mem_issued,2'b0};
 assign m_cmd_wdata=fifo[mem_issued[2:0]];
 assign m_cmd_wmask=4'hf;
 assign m_rsp_ready=1'b1;
 assign c_ready=!r_valid&&!(c_read&&c_addr==8&&busy);
 wire[32:0]end_address={1'b0,destination}+({1'b0,c_data}<<2);
 wire valid_length=c_data>0&&c_data<=8873&&destination>=32'ha0040000&&
                   destination[1:0]==0&&end_address<=33'h0a0080000;
 // In-order responses: a read response is pending whenever received!=issued.
 // The REQ write is only issued after the burst's last read and no read is
 // issued before its response, so the write ACK is the response that arrives
 // in WAIT_REQ with received==issued.
 wire rsp_is_read=received!=issued;
 wire fifo_full=(received-mem_issued)>=14'd8;
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
   if(busy)begin
    case(phase)
     SELECT:if(!error_q&&issued!=length)begin burst_count<=next_count;burst_issued<=0;phase<=REQUEST;end
     REQUEST:if(p_cmd_ready)phase<=WAIT_REQ;
     WAIT_REQ:if(p_rsp_valid&&!rsp_is_read)begin req_level<=~req_level;phase<=READ;cooldown<=0;end
     READ:begin
      if(p_cmd_ready&&cooldown==0)begin
       issued<=issued+1'b1;burst_issued<=burst_issued+1'b1;cooldown<=2'd3;
       if(burst_issued+8'd1==burst_count)begin
        if(issued+14'd1!=length&&!error_q)begin burst_count<=(length-issued-14'd1)>=14'(MAX_BURST)?8'(MAX_BURST):8'(length-issued-14'd1);
                                      burst_issued<=0;phase<=REQUEST;end
        else phase<=SELECT;
       end
      end else if(cooldown!=0)cooldown<=cooldown-1'b1;
      // A fixed-rate source cannot pause inside an announced burst.
      if(cooldown==0&&!p_cmd_ready)error_q<=1;
     end
     default:phase<=SELECT;
    endcase
    if(p_rsp_valid)begin
     if(p_rsp_err)error_q<=1;
     if(rsp_is_read)begin
      if(fifo_full)error_q<=1;
      fifo[received[2:0]]<=p_rsp_rdata;received<=received+1'b1;
     end
    end
    if(m_cmd_valid&&m_cmd_ready)mem_issued<=mem_issued+1'b1;
    if(m_rsp_valid)begin mem_responses<=mem_responses+1'b1;if(m_rsp_err)error_q<=1;end
    if((error_q||issued==length)&&phase==SELECT&&received==issued&&mem_responses==issued&&
       !(m_rsp_valid))busy<=0;
   end
  end
 end
endmodule

// The peripheral DMA owns the PPI for the whole configured copy (ppi_lock);
// CPU peripheral accesses wait until the copy completes and its responses
// drain. Original peripheral and bus modules unchanged.
module q12_gpio_ppi_arbiter(
 input wire clk,rst_n,
 input wire dma_lock,
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
 reg[3:0]outstanding;
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
 wire cmd_fire=m_cmd_valid&&m_cmd_ready;
 wire rsp_fire=m_rsp_valid&&m_rsp_ready;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=IDLE;outstanding<=0;end
  else case(state)
   IDLE:if(s_cmd_valid[0])state<=CPU_CMD;else if(dma_lock)begin state<=DMA;outstanding<=0;end
   CPU_CMD:if(cmd_fire)state<=CPU_RSP;
   CPU_RSP:if(rsp_fire)state<=IDLE;
   DMA:begin
    outstanding<=outstanding+(cmd_fire?4'd1:4'd0)-(rsp_fire?4'd1:4'd0);
    if(!dma_lock&&outstanding==0&&!cmd_fire)state<=IDLE;
   end
  endcase
 end
endmodule
