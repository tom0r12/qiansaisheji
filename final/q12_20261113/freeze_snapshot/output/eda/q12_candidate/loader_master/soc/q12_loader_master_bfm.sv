`timescale 1ns/1ps
`default_nettype none
// External transaction source only. Uses public request handshake and its own
// master interface. No CPU-wire observation or hierarchical memory writes.
module q12_loader_master_bfm(
 input wire clk,rst_n,
 input wire request_valid,output wire request_ready,
 input wire [31:0] request_epoch,input wire [3:0] request_chunk,
 output reg active,
 output wire cmd_valid,output wire cmd_read,
 output wire [31:0] cmd_addr,cmd_wdata,output wire [3:0] cmd_wmask,
 input wire cmd_ready,rsp_valid,rsp_err,
 output wire rsp_ready
);
 localparam [31:0] SOURCE=32'ha0040000, CONTROL=32'ha0030100;
 localparam integer IDLE=0,SEND=1,WAIT_ACK=2,SOURCE_RUN=3;
 reg [31:0] image[0:16383];
 integer input_words,boundaries[0:8],state=IDLE;
 integer loaded_words=0,source_acks=0,control_acks=0,chunks=0;
 integer pending_seq=0,next_seq=1,chunk_seq=0,phase=0,word_index=0;
 integer first_source_cycle=-1,last_source_ack_cycle=-1,cycle=0;
 reg [31:0] chunk_epoch=0;
 reg [1023:0] input_path;
 integer j,sum,bits;
 initial begin
  if(!$value$plusargs("INPUT=%s",input_path)||!$value$plusargs("INPUT_WORDS=%d",input_words))$fatal(1,"loader missing fixture");
  if(input_words<330||input_words>8873)$fatal(1,"loader input bound");
  $readmemh(input_path,image,0,input_words-1);
  if(image[0]!=32'h31513151||image[1]==0||image[1]>76230)$fatal(1,"loader invalid Q12 header");
  sum=330+int'((image[1]+31)>>5);boundaries[0]=sum;
  for(j=0;j<8;j=j+1)begin
   bits=int'(image[2+j]);if(bits<=0||bits>24640)$fatal(1,"loader W length");
   sum=sum+((bits+31)>>5);boundaries[j+1]=sum;
  end
  if(sum!=input_words)$fatal(1,"loader packet length mismatch");
  active=0;
 end
 reg [31:0] address,data;
 always @* begin
  address=SOURCE+32'(word_index*4);data=image[word_index];
  if(phase!=0)begin
   case(phase)
    1:begin address=CONTROL+16;data=32'(input_words);end
    2:begin address=CONTROL+24;data=chunk_epoch;end
    3:begin address=CONTROL+8;data=32'(boundaries[chunk_seq-1]);end
    4:begin address=CONTROL+20;data=0;end
    5:begin address=CONTROL+4;data=32'(chunk_seq);end
    default:begin address=0;data=0;end
   endcase
  end
 end
 assign request_ready=rst_n&&state==IDLE&&!active;
 // Keep the next source word offered while the old ACK returns. The
 // independent master2 uses the bounded three-owner FIFO; every
 // accepted source write still receives a real ordered shared-SRAM ACK.
 assign cmd_valid=active&&(state==SEND ||
                    (state==SOURCE_RUN && word_index<boundaries[chunk_seq-1]));
 assign cmd_read=1'b0;
 assign cmd_addr=address;assign cmd_wdata=data;assign cmd_wmask=4'hf;
 assign rsp_ready=active&&(state==WAIT_ACK||state==SOURCE_RUN);
 always @(posedge clk)begin
  cycle=cycle+1;
  if(!rst_n)begin
   active<=0;state<=IDLE;loaded_words<=0;source_acks<=0;
   control_acks<=0;chunks<=0;pending_seq<=0;next_seq<=1;chunk_seq<=0;
   phase<=0;word_index<=0;chunk_epoch<=0;
   first_source_cycle<=-1;last_source_ack_cycle<=-1;
  end else begin
   if(request_valid&&request_ready)begin
    if(request_epoch==0||request_chunk!=4'(next_seq)||request_chunk<1||request_chunk>9||
       (chunks!=0&&request_epoch!=chunk_epoch))$fatal(1,"invalid public loader request");
    active<=1;chunk_seq<=int'(request_chunk);chunk_epoch<=request_epoch;
    word_index<=loaded_words;phase<=0;state<=SOURCE_RUN;
   end
   if(cmd_valid&&cmd_ready)begin
    if(phase==0&&first_source_cycle<0)first_source_cycle<=cycle;
    if(state==SOURCE_RUN)word_index<=word_index+1;
    else state<=WAIT_ACK;
   end
   if(rsp_valid&&rsp_ready)begin
    if(rsp_err)$fatal(1,"platform loader write response error");
    if(phase==0)begin
     loaded_words<=loaded_words+1;source_acks<=source_acks+1;last_source_ack_cycle<=cycle;
     if(loaded_words+1==boundaries[chunk_seq-1])begin
      // No control commit is even offered before the entire source prefix
      // has its final physical shared-SRAM response ACK.
      phase<=1;state<=SEND;
     end
    end else begin
     control_acks<=control_acks+1;
     if(phase==5)begin
      // READY_SEQ has now reached shared SRAM and its response drained.
      chunks<=chunks+1;next_seq<=next_seq+1;active<=0;state<=IDLE;
      $display("Q12_LOADER_CHUNK_ACK seq=%0d words=%0d cycle=%0d",chunk_seq,loaded_words,cycle);
     end else begin phase<=phase+1;state<=SEND;end
    end
   end
  end
 end
endmodule
`default_nettype wire
