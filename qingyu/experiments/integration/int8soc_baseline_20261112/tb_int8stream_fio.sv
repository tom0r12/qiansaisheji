`timescale 1ns/1ps
module tb_int8stream_fio;
 parameter integer TIMEOUT_CYCLES=96;
 reg clk=0,rst_n=0;
 always #5 clk=~clk;
 reg icb_cmd_valid=0,icb_cmd_read=1,icb_rsp_ready=0;
 reg [31:0] icb_cmd_addr=0,icb_cmd_wdata=0;
 reg [3:0] icb_cmd_wmask=15;
 wire icb_cmd_ready,icb_rsp_valid,icb_rsp_err;
 wire [31:0] icb_rsp_rdata;
 wire dma_cmd_valid,dma_cmd_ready,dma_cmd_read,dma_rsp_valid,dma_rsp_ready,dma_rsp_err;
 wire [31:0] dma_cmd_addr,dma_cmd_wdata,dma_rsp_rdata;
 wire [3:0] dma_cmd_wmask;
 wire shared_cache_clear,host_valid;
 wire [31:0] host_code;
 qingyu_int8stream_fio #(.ENGINE_TIMEOUT_CYCLES(TIMEOUT_CYCLES)) dut(.*);
 localparam [31:0] SOURCE=32'ha0040000,OUTPUT=32'ha0000000,POISON=32'hcccccccc;
 reg [31:0] memory[0:131071],image[0:8191],expected[0:6384];
 reg [31:0] response_fifo[0:15];
 reg error_fifo[0:15];
 integer qcount=0,qhead=0,qtail=0;
 reg allow_command=1,allow_response=1,inject_bus_error=0;
 integer ticks=0,commands=0,responses=0,reads=0,writes=0,invalidates=0,markers=0,clears=0;
 integer host_count=0,held_checks=0,mmio_checks=0,scenario_count=0;
 integer input_words=0,written_words=0,short_mode=1,seed=17,random_state;
 reg held_control=0,held_dma=0;
 reg [32:0] old_control;
 reg [68:0] old_dma;
 string input_path,expected_path;
 reg [31:0] value;
 assign dma_cmd_ready=rst_n&&allow_command&&qcount<16;
 assign dma_rsp_valid=rst_n&&allow_response&&qcount>0;
 assign dma_rsp_rdata=response_fifo[qhead];
 assign dma_rsp_err=error_fifo[qhead];
 wire command_fire=dma_cmd_valid&&dma_cmd_ready;
 wire response_fire=dma_rsp_valid&&dma_rsp_ready;
 integer lane;
 always @(posedge clk)begin
  ticks=ticks+1;
  if(!rst_n)begin
   qcount<=0;qhead<=0;qtail<=0;held_control=0;held_dma=0;
  end else begin
   if(held_control)begin
    held_checks++;
    if(!icb_rsp_valid||{icb_rsp_err,icb_rsp_rdata}!==old_control)$fatal(1,"MMIO held response changed");
   end
   held_control=icb_rsp_valid&&!icb_rsp_ready;old_control={icb_rsp_err,icb_rsp_rdata};
   if(held_dma&&(!dma_cmd_valid||{dma_cmd_read,dma_cmd_addr,dma_cmd_wdata,dma_cmd_wmask}!==old_dma))
    $fatal(1,"held originating DMA command changed on error");
   held_dma=dma_cmd_valid&&!dma_cmd_ready;old_dma={dma_cmd_read,dma_cmd_addr,dma_cmd_wdata,dma_cmd_wmask};
   if(shared_cache_clear)clears++;
   if(host_valid)begin host_count++;if(host_code!==32'h1234abcd)$fatal(1,"host payload mismatch");end
   if(command_fire)begin
    if(dma_cmd_addr[1:0]!=0||dma_cmd_addr<32'ha0000000||dma_cmd_addr>=32'ha0080000||dma_cmd_wmask!=15)
     $fatal(1,"invalid DMA address/mask");
    response_fifo[qtail]<=dma_cmd_read?memory[dma_cmd_addr[18:2]]:0;
    error_fifo[qtail]<=inject_bus_error&&commands==0;
    qtail<=(qtail+1)%16;commands++;
    if(dma_cmd_read)reads++;
    else begin
     if(dma_cmd_addr>=SOURCE)$fatal(1,"source packet was modified");
     for(lane=0;lane<4;lane++)if(dma_cmd_wmask[lane])memory[dma_cmd_addr[18:2]][8*lane+:8]<=dma_cmd_wdata[8*lane+:8];
     writes++;
     if(dma_cmd_addr==OUTPUT)begin
      if(dma_cmd_wdata==0)invalidates++;
      else if(dma_cmd_wdata==32'h31593851)markers++;
      else $fatal(1,"unknown marker write");
     end
    end
   end
   if(response_fire)begin qhead<=(qhead+1)%16;responses++;end
   case({command_fire,response_fire})
    2'b10:qcount<=qcount+1;
    2'b01:qcount<=qcount-1;
    default:begin end
   endcase
  end
 end
 task automatic access(input reg read_op,input reg[31:0] address,data,input reg[3:0] mask,
                       input integer hold_cycles,input reg want_error,input reg release_dma,
                       output reg[31:0] result);
  integer n;reg accepted;
  begin
   @(negedge clk);icb_cmd_valid=1;icb_cmd_read=read_op;icb_cmd_addr=address;icb_cmd_wdata=data;
   icb_cmd_wmask=mask;icb_rsp_ready=0;accepted=0;n=0;
   while(!accepted&&n<100)begin @(posedge clk);accepted=icb_cmd_ready;#1;n++;end
   if(!accepted)$fatal(1,"MMIO command timeout addr=%h",address);
   @(negedge clk);icb_cmd_valid=0;n=0;
   while(!icb_rsp_valid&&n<TIMEOUT_CYCLES+200)begin @(negedge clk);n++;end
   if(!icb_rsp_valid||icb_rsp_err!==want_error)$fatal(1,"MMIO response mismatch addr=%h valid=%0d error=%0d want=%0d",address,icb_rsp_valid,icb_rsp_err,want_error);
   result=icb_rsp_rdata;
   if(release_dma)begin allow_command=1;allow_response=1;end
   repeat(hold_cycles)begin
    @(negedge clk);
    if(icb_cmd_ready||!icb_rsp_valid||icb_rsp_rdata!==result||icb_rsp_err!==want_error)$fatal(1,"MMIO response not captured");
   end
   icb_rsp_ready=1;@(posedge clk);#1;
   @(negedge clk);icb_rsp_ready=0;mmio_checks++;
  end
 endtask
 task automatic write_reg(input reg[7:0] offset,input reg[31:0] data,input reg err);
  reg[31:0] ignored;
  begin access(0,32'hf0000000+{24'b0,offset},data,15,0,err,0,ignored);end
 endtask
 task automatic read_reg(input reg[7:0] offset,output reg[31:0] result);
  begin access(1,32'hf0000000+{24'b0,offset},0,15,0,0,0,result);end
 endtask
 task automatic reset_control;
  begin
   @(negedge clk);rst_n=0;icb_cmd_valid=0;icb_rsp_ready=0;allow_command=1;allow_response=1;inject_bus_error=0;
   repeat(3)@(posedge clk);
   @(negedge clk);rst_n=1;
   @(posedge clk);#1;
   commands=0;responses=0;reads=0;writes=0;invalidates=0;markers=0;clears=0;
  end
 endtask
 task automatic setup_pointers(input reg[31:0] src,dst);
  begin write_reg(8,src,0);write_reg(12,dst,0);end
 endtask
 task automatic wait_idle_error(input integer code);
  integer n;reg[31:0] status;
  begin
   n=0;status=1;
   while(status[0]&&n<100)begin read_reg(16,status);n++;end
   if(status[3:0]!=14||status[15:8]!=8'(code)||commands!=responses||qcount!=0)
    $fatal(1,"drain/error status mismatch code=%0d status=%h cmds=%0d rsp=%0d",code,status,commands,responses);
  end
 endtask
 task automatic start_invalid(input reg[31:0] src,dst,input integer code);
  integer before_commands;
  begin
   setup_pointers(src,dst);before_commands=commands;write_reg(4,1,0);
   access(1,32'hf0000014,0,15,7,0,0,value);
   wait_idle_error(code);
   if(code==1&&commands!=before_commands)$fatal(1,"invalid pointer issued DMA");
   write_reg(4,2,0);read_reg(16,value);if(value!=8)$fatal(1,"clear failed %h",value);
   scenario_count++;
  end
 endtask
 task automatic timeout_case(input reg block_command);
  integer begin_tick;
  reg[31:0] status;
  begin
   reset_control();setup_pointers(SOURCE,OUTPUT);
   allow_command=!block_command;allow_response=0;begin_tick=ticks;write_reg(4,1,0);
   write_reg(8,SOURCE+4,1);write_reg(12,OUTPUT+4,1);write_reg(4,1,1);write_reg(4,2,1);
   read_reg(8,status);if(status!=SOURCE)$fatal(1,"busy config changed");
   // WAIT returns the active timeout without falsely completing the DMA.
   // Once its response exists, release DMA while that old status is held.
   access(1,32'hf0000014,0,15,40,0,1,status);
   if(status[3:0]!=5||status[15:8]!=8'h11||ticks-begin_tick>TIMEOUT_CYCLES+120)
    $fatal(1,"WAIT failed bounded busy/error return status=%h latency=%0d",status,ticks-begin_tick);
   wait_idle_error(17);
   if(clears!=1)$fatal(1,"cold cache clear count");
   scenario_count++;
   // Restart without resetting: reject an invalid source, then return ready.
   start_invalid(SOURCE+1,OUTPUT,1);
  end
 endtask
 task automatic normal_packet;
  integer before_read,before_write,before_clear,n;
  reg[31:0] status;
  begin
   before_read=reads;before_write=writes;before_clear=clears;
   setup_pointers(SOURCE,OUTPUT);write_reg(4,1,0);
   access(1,32'hf0000014,0,15,23,0,0,status);
   if(status[3:0]!=10)$fatal(1,"normal WAIT failure %h",status);
   if(reads-before_read!=input_words||writes-before_write!=written_words+1||clears-before_clear!=1||commands!=responses)
    $fatal(1,"normal transaction count mismatch read=%0d write=%0d",reads-before_read,writes-before_write);
   for(n=0;n<6385;n++)if(memory[n]!==expected[n])$fatal(1,"normal output mismatch word=%0d",n);
   for(n=0;n<input_words;n++)if(memory[65536+n]!==image[n])$fatal(1,"source changed word=%0d",n);
   $display("MMIO_NORMAL cycles=%0d reads=%0d writes=%0d",dut.task_cycles,reads-before_read,writes-before_write);
   scenario_count++;
  end
 endtask
 integer n,discard_random;
 initial begin
  if($value$plusargs("SHORT=%d",short_mode))begin end
  if($value$plusargs("SEED=%d",seed))begin end
  random_state=seed;discard_random=$urandom(random_state);
  if(!$value$plusargs("INPUT=%s",input_path)||!$value$plusargs("EXPECTED=%s",expected_path)||
     !$value$plusargs("INPUT_WORDS=%d",input_words)||!$value$plusargs("WRITTEN_WORDS=%d",written_words))$fatal(1,"missing packet arguments");
  for(n=0;n<131072;n++)memory[n]=POISON;
  $readmemh(input_path,image,0,input_words-1);$readmemh(expected_path,expected);
  for(n=0;n<input_words;n++)memory[65536+n]=image[n];
  reset_control();
  access(1,32'hf0000000,0,15,19,0,0,value);if(value!=32'h51385231)$fatal(1,"ID mismatch");
  access(1,32'hf0000001,0,15,3,1,0,value);
  access(1,32'hf0000034,0,15,3,1,0,value);
  access(1,32'hf0010000,0,15,3,1,0,value);
  access(1,32'hf0000004,0,15,3,1,0,value);
  access(0,32'hf0000000,0,15,3,1,0,value);
  for(n=0;n<15;n++)access(0,32'hf0000008,32'hbad00000,4'(n),$urandom_range(0,5),1,0,value);
  read_reg(8,value);if(value!=0)$fatal(1,"partial write mutated source");
  write_reg(4,3,1);write_reg(20,0,1);
  access(0,32'hf0010000,32'h1234abcd,15,8,0,0,value);
  if(host_count!=1)$fatal(1,"host pulse not exactly once");
  scenario_count++;
  start_invalid(SOURCE+1,OUTPUT,1);start_invalid(SOURCE,32'ha007ffff,1);
  start_invalid(32'hfffffff0,OUTPUT,1);
  if(short_mode!=0)begin timeout_case(0);timeout_case(1);end
  else begin
   // Real header error and exact full-task reload, never a fake engine.
   memory[65536]=image[0]^1;
   setup_pointers(SOURCE,OUTPUT);write_reg(4,1,0);
   access(1,32'hf0000014,0,15,13,0,0,value);wait_idle_error(2);scenario_count++;
   memory[65536]=image[0];normal_packet();normal_packet();
   // A real bus error drains before the next successful complete task.
   reset_control();inject_bus_error=1;setup_pointers(SOURCE,OUTPUT);write_reg(4,1,0);
   access(1,32'hf0000014,0,15,11,0,0,value);wait_idle_error(16);scenario_count++;
   inject_bus_error=0;normal_packet();
  end
  $display("PASS int8stream_fio short=%0d scenarios=%0d mmio=%0d held=%0d seed=%0d",short_mode,scenario_count,mmio_checks,held_checks,seed);
  $finish;
 end
 initial begin #100000000;$fatal(1,"global timeout");end
endmodule
