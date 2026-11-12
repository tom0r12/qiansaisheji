`timescale 1ns/1ps
module tb_streaming_loader;
 localparam [31:0] SOURCE=32'ha0040000,OUTPUT=32'ha0000000,POISON=32'hcccccccc,MAGIC=32'h31593851;
 localparam integer QDEPTH=32768,WORDS=6385;
 reg clk=0,rst_n=0,active=0;
 always #5 clk=~clk;
 reg start_valid=0,loader_valid=0,loader_fault=0,producer_stop=0;
 reg [31:0] loader_addr=SOURCE,loader_data=0,watermark=SOURCE;
 wire start_ready,busy,done,error,cache_clear;wire[7:0]error_code;
 wire[31:0]task_cycles,core_cycles,core_load,core_factor,core_cache,core_compute,core_store;
 wire cv,cq,cread,rv,rr,rerr;wire[31:0]ca,cd,rd;wire[3:0]cm;
 wire[1:0] msq,msrv,mserr;wire[63:0] msdata;
 reg loader_rsp_allow=1,engine_rsp_allow=1;
 wire fcv,fcq,fread,frv,frr,fre;wire[31:0]fca,fcd,frd;wire[3:0]fcm;
 wire sv,sq,sread,srv,srr,se;wire[31:0]sa,sd,sdata;wire[3:0]sm;
 wire loader_ready=msq[0],loader_response=msrv[0]&&loader_rsp_allow;
 integer mode=0,serial_start=0,stalls=0,seed=3719,random_state=3719;
 integer ticks=0,id=0,successes=0,failures=0,resets=0;
 integer input_words,input_words0,input_words1,output_words,output_words0,output_words1;
 integer lc=0,lr=0,ec=0,er=0,mc=0,mr=0,sc=0,sr=0,committed=0;
 integer engine_reads=0,engine_writes=0,engine_read_acks=0,engine_write_acks=0;
 integer invalidations=0,invalidation_acks=0,magic_offers=0,magic_acks=0;
 integer first_offer=-1,first_accept=-1,first_ack=-1,last_loader_ack=-1,start_tick=-1,last_ack=-1,done_tick=-1;
 integer cold=0,begins=0,physical_reads=0,physical_writes=0,poison_prefetch=0;
 integer loader_wait=0,engine_wait=0,fabric_wait=0,loader_rsp_wait=0,engine_rsp_wait=0;
 integer gate_header=0,gate_x=0,gate_w=0,gate_meta=0,pack_wait=0,output_wait=0;
 integer read_hits=0,read_misses=0,peak=0,mixed_pending=0,fault_tick=-1,producer_fault_responses=0;
 integer committed_previous=0,loader_pause=0,offer_pause=0,x_end=0;
 integer boundaries[0:10];reg boundary_paused[0:10];reg source_pause_done=0;
 integer pause_checks=0,idle_checks=0;reg done_seen=0,start_fault_pulsed=0,late_fault_seen=0;
 reg [31:0] input_image[0:8191],expected[0:WORDS-1],reference_mem[0:131071];
 integer source_written[0:8191],source_acked[0:8191],source_read[0:8191],out_seen[0:WORDS-1],out_acked[0:WORDS-1];
 reg output_required[0:WORDS-1];
 reg [31:0] qa[0:QDEPTH-1],qd[0:QDEPTH-1],qrdata[0:QDEPTH-1];
 reg qo[0:QDEPTH-1],qread[0:QDEPTH-1],qinvalid[0:QDEPTH-1];
 integer lqid[0:QDEPTH-1],eqid[0:QDEPTH-1];
 reg held_l=0,held_e=0,held_f=0,held_rsp=0,held_desc=0;
 reg[63:0]old_l,old_desc;reg[68:0]old_e,old_f;reg[32:0]old_rsp;
 wire loader_error=mserr[0]||(mode==3&&lr==10)||(mode==4&&lr==250);
 assign cq=msq[1];assign rv=msrv[1]&&engine_rsp_allow;assign rd=msdata[63:32];assign rerr=mserr[1];

 qingyu_int8stream_engine dut(.clk(clk),.rst_n(rst_n),.start_valid(start_valid),.start_ready(start_ready),
  .start_source(SOURCE),.start_output(OUTPUT),.loader_committed_end(watermark),.loader_fault(loader_fault),
  .busy(busy),.done(done),.error(error),.error_code(error_code),.shared_cache_clear(cache_clear),.task_cycles(task_cycles),
  .core_cycles(core_cycles),.core_load_cycles(core_load),.core_factor_cycles(core_factor),.core_cache_cycles(core_cache),.core_compute_cycles(core_compute),.core_store_cycles(core_store),
  .icb_cmd_valid(cv),.icb_cmd_ready(cq),.icb_cmd_read(cread),.icb_cmd_addr(ca),.icb_cmd_wdata(cd),.icb_cmd_wmask(cm),
  .icb_rsp_valid(rv),.icb_rsp_ready(rr),.icb_rsp_rdata(rd),.icb_rsp_err(rerr));
 qingyu_icb_merge #(.NP(2),.OUTSTANDING(4),.ONE_PER_PORT(2'b01)) merge(
  .clk(clk),.rst_n(rst_n),.s_cmd_valid({cv,loader_valid}),.s_cmd_ready(msq),.s_cmd_read({cread,1'b0}),
  .s_cmd_addr({ca,loader_addr}),.s_cmd_wdata({cd,loader_data}),.s_cmd_wmask({cm,4'hf}),
  .s_rsp_valid(msrv),.s_rsp_ready({rr&&engine_rsp_allow,loader_rsp_allow}),.s_rsp_err(mserr),.s_rsp_rdata(msdata),
  .m_cmd_valid(fcv),.m_cmd_ready(fcq),.m_cmd_read(fread),.m_cmd_addr(fca),.m_cmd_wdata(fcd),.m_cmd_wmask(fcm),
  .m_rsp_valid(frv),.m_rsp_ready(frr),.m_rsp_err(fre),.m_rsp_rdata(frd));
 e203_subsys_mems fabric(.clk(clk),.rst_n(rst_n),.bus_rst_n(rst_n),
  .mem_icb_cmd_valid(fcv),.mem_icb_cmd_ready(fcq),.mem_icb_cmd_addr(fca),.mem_icb_cmd_read(fread),
  .mem_icb_cmd_wdata(fcd),.mem_icb_cmd_wmask(fcm),.mem_icb_rsp_valid(frv),.mem_icb_rsp_ready(frr),.mem_icb_rsp_err(fre),.mem_icb_rsp_rdata(frd),
  .sysmem_icb_cmd_valid(sv),.sysmem_icb_cmd_ready(sq),.sysmem_icb_cmd_addr(sa),.sysmem_icb_cmd_read(sread),.sysmem_icb_cmd_wdata(sd),.sysmem_icb_cmd_wmask(sm),
  .sysmem_icb_rsp_valid(srv),.sysmem_icb_rsp_ready(srr),.sysmem_icb_rsp_err(se),.sysmem_icb_rsp_rdata(sdata),
  .qspi0_ro_icb_cmd_valid(),.qspi0_ro_icb_cmd_ready(1'b1),.qspi0_ro_icb_cmd_addr(),.qspi0_ro_icb_cmd_read(),.qspi0_ro_icb_cmd_wdata(),
  .qspi0_ro_icb_rsp_valid(1'b0),.qspi0_ro_icb_rsp_ready(),.qspi0_ro_icb_rsp_err(1'b0),.qspi0_ro_icb_rsp_rdata(32'b0),
  .dm_icb_cmd_valid(),.dm_icb_cmd_ready(1'b1),.dm_icb_cmd_addr(),.dm_icb_cmd_read(),.dm_icb_cmd_wdata(),
  .dm_icb_rsp_valid(1'b0),.dm_icb_rsp_ready(),.dm_icb_rsp_rdata(32'b0));
 qingyu_shared_sram shared(.clk(clk),.rst_n(rst_n),.cache_clear(cache_clear),
  .icb_cmd_valid(sv),.icb_cmd_ready(sq),.icb_cmd_addr(sa),.icb_cmd_read(sread),.icb_cmd_wdata(sd),.icb_cmd_wmask(sm),
  .icb_rsp_valid(srv),.icb_rsp_ready(srr),.icb_rsp_err(se),.icb_rsp_rdata(sdata));

 function automatic integer random_percent;
  begin random_state=(random_state*1103515245+12345)&32'h7fffffff;random_percent=(random_state>>8)%100;end
 endfunction
 integer off,j,tag,port,old_mc;
 always @(posedge clk)begin
  ticks++;
  if(active&&rst_n)begin
   if(watermark!==SOURCE+32'(committed*4)||committed<committed_previous)$fatal(1,"watermark not successful contiguous ACK prefix");
   committed_previous=committed;
   if(loader_valid&&first_offer<0)first_offer=ticks;
   if(start_valid&&start_ready)begin
    if(start_tick>=0||committed<(serial_start?input_words:202))$fatal(1,"early/duplicate START");start_tick=ticks;
   end
   if(cache_clear)cold++;
   if(dut.compute.begin_fire)begins++;
   if(done)begin done_seen=1;done_tick=ticks;end
   if(held_l&&(!loader_valid||{loader_addr,loader_data}!==old_l))$fatal(1,"producer withdrew/changed held offer");
   if(held_e&&(!cv||{cread,ca,cd,cm}!==old_e))$fatal(1,"engine changed held offer");
   if(held_f&&(!fcv||{fread,fca,fcd,fcm}!==old_f))$fatal(1,"merge changed held offer");
   if(held_rsp&&(!frv||{fre,frd}!==old_rsp))$fatal(1,"fabric response changed under stall");
   if(held_desc&&!loader_fault&&!error&&dut.state!=dut.ABORT_DRAIN&&
      (!dut.rd_desc_valid||{dut.rd_desc_base,dut.rd_desc_count}!==old_desc))$fatal(1,"blocked descriptor changed");
   held_l=loader_valid&&!loader_ready;old_l={loader_addr,loader_data};
   held_e=cv&&!cq;old_e={cread,ca,cd,cm};held_f=fcv&&!fcq;old_f={fread,fca,fcd,fcm};
   held_rsp=frv&&!frr;old_rsp={fre,frd};
   held_desc=dut.rd_desc_valid&&!dut.rd_desc_ready;old_desc={dut.rd_desc_base,dut.rd_desc_count};
   if(dut.transport.rd_desc_valid&&dut.transport.rd_desc_ready&&
      ({3'b0,dut.rd_desc_base}+({3'b0,dut.rd_desc_count}<<2)>{3'b0,watermark}||dut.rd_desc_base<SOURCE))$fatal(1,"descriptor passed before real producer ACK");
   if(dut.rd_desc_valid&&!dut.descriptor_committed)begin
    if(dut.state==dut.HEADER_REQ)gate_header++;
    else if(dut.read_state==dut.DECODE_REQ)begin if(dut.decode_weights)gate_w++;else gate_x++;end
    else gate_meta++;
   end
   if(loader_valid&&!loader_ready)loader_wait++;
   if(cv&&!cq)engine_wait++;if(fcv&&!fcq)fabric_wait++;
   if(msrv[0]&&!loader_rsp_allow)loader_rsp_wait++;
   if(msrv[1]&&!(rr&&engine_rsp_allow))engine_rsp_wait++;
   if(dut.pack_out_valid&&!dut.pack_out_ready)pack_wait++;
   if(dut.core_out_valid&&!dut.core_out_ready)output_wait++;
   if(shared.ram_cs)begin
    if(shared.ram_we)begin physical_writes++;if(!(sv&&sq&&!sread))$fatal(1,"macro write bypassed shared command");end
    else begin
     physical_reads++;
     if(shared.ram_addr>=65536&&shared.ram_addr<65536+input_words&&source_written[shared.ram_addr-65536]==0)poison_prefetch++;
    end
   end
   old_mc=mc;
   if(loader_valid&&loader_ready)begin
    if(first_accept<0)first_accept=ticks;
    if(lc>=input_words||loader_addr!==SOURCE+32'(lc*4)||loader_data!==input_image[lc])$fatal(1,"producer address/data/sequence mismatch");
    qa[mc]=loader_addr;qd[mc]=loader_data;qo[mc]=0;qread[mc]=0;qinvalid[mc]=0;lqid[lc]=mc;lc++;mc++;
   end
   if(cv&&cq)begin
    if(start_tick<0||cold!=1||magic_offers!=0||cm!=4'hf||ca[1:0]!=0)$fatal(1,"engine offer outside cold task");
    qa[mc]=ca;qd[mc]=cd;qo[mc]=1;qread[mc]=cread;qinvalid[mc]=0;eqid[ec]=mc;ec++;
    if(cread)begin
     if(ca<SOURCE||ca>=SOURCE+32'(input_words*4)||{3'b0,ca}+35'd4>{3'b0,watermark})$fatal(1,"uncommitted/outside engine read");
     off=int'((ca-SOURCE)>>2);if(source_acked[off]!=1||source_read[off]!=0)$fatal(1,"read missing ACK or duplicate");
     if(off>=10&&invalidation_acks!=1)$fatal(1,"payload read before invalidation ACK");
     source_read[off]++;engine_reads++;
    end else begin
     if(ca<OUTPUT||ca>=OUTPUT+32'(WORDS*4))$fatal(1,"output outside allocation");off=int'((ca-OUTPUT)>>2);
     if(off==0&&cd==0)begin
      if(invalidations!=0||engine_writes!=0)$fatal(1,"bad invalidation order");invalidations++;qinvalid[mc]=1;
     end else begin
      if(invalidation_acks!=1||!output_required[off]||out_seen[off]!=0||cd!==expected[off])$fatal(1,"encoded output mismatch offset=%0d",off);
      if(off==0)begin
       if(committed!=input_words||engine_read_acks!=input_words)$fatal(1,"magic before complete source commit/read");
       for(j=1;j<WORDS;j++)if(output_required[j]&&out_acked[j]!=1)$fatal(1,"magic before payload/header ACK");magic_offers++;
      end
      if(off>0&&off<=16)for(j=0;j<int'((expected[off]+31)>>5);j++)if(out_acked[17+398*(off-1)+j]!=1)$fatal(1,"length precedes payload ACK");
      out_seen[off]++;
     end
     engine_writes++;
    end
    mc++;
   end
   if(mc>QDEPTH||mc-old_mc>1)$fatal(1,"invalid single merged acceptance");
   if((fcv&&fcq)!=(mc!=old_mc))$fatal(1,"source/merged acceptance differs");
   if(fcv&&fcq&&{fread,fca,fcd,fcm}!=={qread[old_mc],qa[old_mc],qd[old_mc],4'hf})$fatal(1,"merged identity differs");
   if(sv&&sq)begin
    if(sc>=mc||{sread,sa,sd,sm}!=={qread[sc],qa[sc],qd[sc],4'hf})$fatal(1,"official fabric route mismatch");
    qrdata[sc]=sread?reference_mem[sa[18:2]]:0;
    if(sread)begin if(srv)read_hits++;else read_misses++;end
    else begin reference_mem[sa[18:2]]=sd;if(!qo[sc])source_written[(sa-SOURCE)>>2]++;end
    sc++;
   end
   if(srv&&srr)begin if(sr>=sc||se||sdata!==qrdata[sr])$fatal(1,"shared response identity/data mismatch");sr++;end
   if(frv&&frr)begin
    if(mr>=sr||fre||frd!==qrdata[mr])$fatal(1,"fabric response identity/data mismatch");
    if(!msrv[qo[mr]]||msrv[!qo[mr]])$fatal(1,"response delivered to wrong merger owner");
    if(qo[mr]==0)begin
     if(!loader_response||lqid[lr]!=mr)$fatal(1,"producer response order mismatch");
     if(first_ack<0)first_ack=ticks;last_loader_ack=ticks;
     if(loader_error)begin producer_fault_responses++;loader_fault<=1;producer_stop=1;if(fault_tick<0)fault_tick=ticks;end
     else if(!loader_fault&&!producer_stop)begin
      if(qa[mr]!==SOURCE+32'(committed*4))$fatal(1,"noncontiguous successful producer ACK");
      source_acked[committed]++;committed++;watermark<=SOURCE+32'(committed*4);
     end
     lr++;
    end else begin
     if(!(rv&&rr)||eqid[er]!=mr||rerr)$fatal(1,"engine response owner mismatch");
     if(qread[mr])begin
      off=int'((qa[mr]-SOURCE)>>2);if(rd!==input_image[off])$fatal(1,"stale/incorrect engine source response");engine_read_acks++;
     end else begin
      engine_write_acks++;off=int'((qa[mr]-OUTPUT)>>2);
      if(qinvalid[mr])invalidation_acks++;
      else begin out_acked[off]++;if(off==0)begin magic_acks++;last_ack=ticks;end end
     end
     er++;
    end
    mr++;
   end
   if(lc-lr>1||mc-mr>4||ec-er>8)$fatal(1,"production outstanding contract exceeded");
   if(mc-mr>peak)peak=mc-mr;if(lc>lr&&ec>er)mixed_pending++;
   if(mc!=lc+ec||mr!=lr+er)$fatal(1,"independent owner counts inconsistent");
  end
 end

 string input0,expect0,input1,expect1;
 integer fault_checks=0,guard,case_guard;
 task automatic prepare(input bit next_packet,input integer fault_mode,input bit serial_mode,input bit random_stalls);
  integer n,need,cursor;reg[31:0]old_magic;
  begin
   @(negedge clk);active=0;start_valid=0;loader_valid=0;loader_fault=0;producer_stop=0;loader_rsp_allow=1;engine_rsp_allow=1;
   guard=0;while(!start_ready)begin @(negedge clk);guard++;if(guard>200)$fatal(1,"restart not ready after joint drain");end
   input_words=next_packet?input_words1:input_words0;output_words=next_packet?output_words1:output_words0;
   if(next_packet)begin $readmemh(input1,input_image,0,input_words-1);$readmemh(expect1,expected);end
   else begin $readmemh(input0,input_image,0,input_words-1);$readmemh(expect0,expected);end
   old_magic=shared.mem[0];
   for(n=0;n<131072;n++)begin shared.mem[n]=POISON;reference_mem[n]=POISON;end
   shared.mem[0]=old_magic;reference_mem[0]=old_magic;
   for(n=0;n<8192;n++)begin source_written[n]=0;source_acked[n]=0;source_read[n]=0;end
   for(n=0;n<WORDS;n++)begin out_seen[n]=0;out_acked[n]=0;output_required[n]=n<17;end
   need=17;for(n=0;n<16;n++)for(integer k=0;k<int'((expected[n+1]+31)>>5);k++)begin output_required[17+398*n+k]=1;need++;end
   if(need!=output_words)$fatal(1,"invalid independent output manifest");
   boundaries[0]=200;boundaries[1]=201;cursor=202+int'((input_image[1]+31)>>5);x_end=cursor;boundaries[2]=cursor-1;
   for(n=0;n<8;n++)begin cursor+=int'((input_image[n+2]+31)>>5);boundaries[n+3]=cursor-1;end
   if(cursor!=input_words)$fatal(1,"input packet length mismatch");
   for(n=0;n<11;n++)boundary_paused[n]=0;
   lc=0;lr=0;ec=0;er=0;mc=0;mr=0;sc=0;sr=0;committed=0;committed_previous=0;watermark=SOURCE;
   engine_reads=0;engine_writes=0;engine_read_acks=0;engine_write_acks=0;invalidations=0;invalidation_acks=0;magic_offers=0;magic_acks=0;
   first_offer=-1;first_accept=-1;first_ack=-1;last_loader_ack=-1;start_tick=-1;last_ack=-1;done_tick=-1;fault_tick=-1;
   cold=0;begins=0;physical_reads=0;physical_writes=0;poison_prefetch=0;loader_wait=0;engine_wait=0;fabric_wait=0;loader_rsp_wait=0;engine_rsp_wait=0;
   gate_header=0;gate_x=0;gate_w=0;gate_meta=0;pack_wait=0;output_wait=0;read_hits=0;read_misses=0;peak=0;mixed_pending=0;
   loader_pause=0;offer_pause=0;source_pause_done=0;pause_checks=0;producer_fault_responses=0;done_seen=0;start_fault_pulsed=0;late_fault_seen=0;
   held_l=0;held_e=0;held_f=0;held_rsp=0;held_desc=0;
   mode=fault_mode;serial_start=serial_mode;stalls=random_stalls;id++;active=1;
  end
 endtask
 task automatic execute(input bit next_packet,input integer fault_mode,input bit serial_mode,input bit random_stalls);
  integer n;bit finish_ok;
  begin: execute_body
   prepare(next_packet,fault_mode,serial_mode,random_stalls);case_guard=0;
   while(1)begin
    if(mode==5&&start_fault_pulsed)loader_fault=0;
    if(error&&busy)producer_stop=1;
    if(mode==6&&!late_fault_seen&&cv&&!cread&&!cq&&engine_writes>8)begin
     loader_fault=1;producer_stop=1;late_fault_seen=1;fault_tick=ticks;
    end
    loader_rsp_allow=!stalls||random_percent()>30;engine_rsp_allow=!stalls||random_percent()>30;
    if(mode==1&&!producer_stop)begin
     for(n=0;n<11;n++)if(msrv[0]&&lr==boundaries[n]&&!boundary_paused[n])begin boundary_paused[n]=1;loader_pause=24;pause_checks++;end
     if(loader_pause>0)begin loader_rsp_allow=0;loader_pause--;end
     if(lc==x_end&&!source_pause_done)begin source_pause_done=1;offer_pause=3000;end
    end
    if(producer_stop)begin loader_rsp_allow=1;engine_rsp_allow=1;end
    if(!held_l)begin
     loader_valid=!producer_stop&&lc<input_words&&offer_pause==0&&(!stalls||random_percent()>20);
     if(loader_valid)begin loader_addr=SOURCE+32'(lc*4);loader_data=input_image[lc];end
    end
    if(offer_pause>0)offer_pause--;
    start_valid=start_tick<0&&!producer_stop&&committed>=(serial_start?input_words:202);
    if(mode==5&&start_valid&&!start_fault_pulsed)begin loader_fault=1;producer_stop=1;if(!held_l)loader_valid=0;start_fault_pulsed=1;fault_tick=ticks;end
    @(negedge clk);case_guard++;
    if(mode==7&&lc>202&&ec>10&&mc>mr)begin
     active=0;rst_n=0;loader_valid=0;start_valid=0;repeat(4)@(negedge clk);rst_n=1;resets++;
     $display("LOADER_RESET id=%0d loader_pending=%0d engine_pending=%0d",id,lc-lr,ec-er);disable execute_body;
    end
    finish_ok=(done_seen||(producer_stop&&start_tick<0))&&!loader_valid&&!cv&&!busy&&mc==mr;
    if(finish_ok)break;
    if(case_guard>2100000)$fatal(1,"conditional loader timeout mode=%0d engine=%0d commit=%0d mc=%0d mr=%0d",mode,dut.state,committed,mc,mr);
   end
   if(mc!=mr||sc!=mc||sr!=mc||lc!=lr||ec!=er||physical_writes!=lc+engine_writes)$fatal(1,"task ended before complete path drain");
   for(n=0;n<131072;n++)if(shared.mem[n]!==reference_mem[n])$fatal(1,"shared/source/guard corruption word=%0d",n);
   if(mode<=2)begin
    if(error||magic_offers!=1||magic_acks!=1||invalidations!=1||invalidation_acks!=1||cold!=1||begins!=1)$fatal(1,"normal conditional task status mismatch");
    if(lc!=input_words||committed!=input_words||engine_reads!=input_words||engine_writes!=output_words+1||mc!=2*input_words+output_words+1)$fatal(1,"complete initial-load traffic mismatch");
    for(n=0;n<input_words;n++)if(source_written[n]!=1||source_acked[n]!=1||source_read[n]!=1||shared.mem[65536+n]!==input_image[n])$fatal(1,"missing/damaged source word");
    for(n=0;n<WORDS;n++)if(shared.mem[n]!==expected[n]||out_seen[n]!=(output_required[n]?1:0)||out_acked[n]!=(output_required[n]?1:0))$fatal(1,"full output/unused-slot mismatch word=%0d",n);
    if(mode==1&&(pause_checks!=11||poison_prefetch==0))$fatal(1,"boundary/future-poison directed coverage absent pauses=%0d future=%0d",pause_checks,poison_prefetch);
    $writememh($sformatf("case%0d_output.hex",id),shared.mem,0,WORDS-1);successes++;
   end else begin
    if(magic_offers!=0||magic_acks!=0)$fatal(1,"producer failure produced success marker");
    if(mode==3)begin if(start_tick>=0||done_seen||cold||begins)$fatal(1,"preSTART fault started engine");end
    else if(!error||!done_seen||error_code!=8'h1b||done_tick-fault_tick>200)$fatal(1,"producer error recovery not bounded code=%h delay=%0d",error_code,done_tick-fault_tick);
    if((mode==3||mode==4)&&producer_fault_responses!=1)$fatal(1,"missing originating producer fault");
    if(mode==6&&!late_fault_seen)$fatal(1,"held output fault not exercised");failures++;
   end
   $display("LOADER_CASE id=%0d next=%0d mode=%0d serial=%0d stalls=%0d first_offer=%0d first_accept=%0d first_source_ack=%0d last_source_ack=%0d start=%0d final_ack=%0d offer_to_final=%0d accept_to_final=%0d ack_to_final=%0d start_to_final=%0d producer_window=%0d source_writes=%0d source_reads=%0d output_writes=%0d commands=%0d responses=%0d physical_reads=%0d physical_writes=%0d poison_prefetch=%0d read_hits=%0d read_misses=%0d peak=%0d mixed_pending=%0d loader_wait=%0d engine_wait=%0d fabric_wait=%0d loader_rsp_wait=%0d engine_rsp_wait=%0d gate_header=%0d gate_x=%0d gate_w=%0d gate_meta=%0d pack_wait=%0d output_wait=%0d pauses=%0d error=%0d error_code=%0d error_to_done=%0d",id,next_packet,mode,serial_start,stalls,first_offer,first_accept,first_ack,last_loader_ack,start_tick,last_ack,last_ack<0?-1:last_ack-first_offer+1,last_ack<0?-1:last_ack-first_accept+1,last_ack<0?-1:last_ack-first_ack+1,last_ack<0?-1:last_ack-start_tick+1,last_loader_ack-first_offer+1,lc,engine_reads,engine_writes,mc,mr,physical_reads,physical_writes,poison_prefetch,read_hits,read_misses,peak,mixed_pending,loader_wait,engine_wait,fabric_wait,loader_rsp_wait,engine_rsp_wait,gate_header,gate_x,gate_w,gate_meta,pack_wait,output_wait,pause_checks,error,error_code,fault_tick<0?-1:done_tick-fault_tick);
   active=0;loader_valid=0;start_valid=0;loader_fault=0;producer_stop=0;repeat(5)@(negedge clk);
  end
 endtask
 initial begin
  if(!$value$plusargs("INPUT=%s",input0)||!$value$plusargs("EXPECTED=%s",expect0)||!$value$plusargs("NEXT_INPUT=%s",input1)||!$value$plusargs("NEXT_EXPECTED=%s",expect1)||
     !$value$plusargs("INPUT_WORDS=%d",input_words0)||!$value$plusargs("OUTPUT_WORDS=%d",output_words0)||!$value$plusargs("NEXT_INPUT_WORDS=%d",input_words1)||!$value$plusargs("NEXT_OUTPUT_WORDS=%d",output_words1))$fatal(1,"missing independent packet inputs");
  if($value$plusargs("FAULT_CHECKS=%d",fault_checks))begin end
  if($value$plusargs("SEED=%d",seed))begin end random_state=seed;
  shared.mem[0]=POISON;repeat(5)@(negedge clk);rst_n=1;
  loader_fault=1;repeat(5)begin @(negedge clk);if(busy||done)$fatal(1,"idle fault spontaneously started/completed task");end
  idle_checks++;loader_fault=0;
  execute(0,0,0,0);execute(1,0,0,0);execute(0,0,1,0);execute(1,0,1,0);
  if(fault_checks!=0)begin
   execute(0,1,0,0);execute(0,2,0,1);
   execute(0,3,0,1);execute(0,0,0,0);
   execute(0,4,0,1);execute(0,0,0,0);
   execute(0,5,0,0);execute(0,0,0,0);
   execute(0,6,0,1);execute(0,0,0,0);
   execute(0,7,0,1);execute(0,0,0,0);
  end
  if(successes!=(fault_checks?11:4)||failures!=(fault_checks?4:0)||resets!=(fault_checks?1:0)||idle_checks!=1)$fatal(1,"conditional suite incomplete");
  $display("PASS conditional_loader successes=%0d failures=%0d hard_resets=%0d idle_fault_checks=%0d seed=%0d",successes,failures,resets,idle_checks,seed);$finish;
 end
endmodule
