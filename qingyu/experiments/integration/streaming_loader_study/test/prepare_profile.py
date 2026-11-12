"""Create independent instrumentation and optional queued-producer fixtures."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
def once(s,old,new):
 if s.count(old)!=1:raise ValueError('Anchor differs: '+old)
 return s.replace(old,new)
tb=(HERE/'tb_streaming_loader.sv').read_text()
tb=once(tb,'module tb_streaming_loader;','''`ifndef LOADER_ONE_PER_PORT
`define LOADER_ONE_PER_PORT 2'b01
`endif
module tb_streaming_loader;
 localparam bit PRODUCER_LIMIT_ONE=(`LOADER_ONE_PER_PORT==2'b01);
 integer profile_cycles=0,profile_accept_loader=0,profile_accept_read=0,profile_accept_write=0;
 integer profile_block_fabric=0,profile_idle_no_offer=0;
 integer profile_pre_start=0,profile_load_overlap=0,profile_tail=0;
 integer profile_idle_before_start=0,profile_idle_overlap=0,profile_idle_tail=0;
 integer profile_producer_pending_no_grant=0,profile_core_cycles=0;
''')
tb=once(tb,".ONE_PER_PORT(2'b01)",'.ONE_PER_PORT(`LOADER_ONE_PER_PORT)')
tb=once(tb,'if(lc-lr>1||mc-mr>4||ec-er>8)','if(lc-lr>(PRODUCER_LIMIT_ONE?1:4)||mc-mr>4||ec-er>8)')
tb=once(tb,'   if(mc!=lc+ec||mr!=lr+er)$fatal(1,"independent owner counts inconsistent");','''   if(mc!=lc+ec||mr!=lr+er)$fatal(1,"independent owner counts inconsistent");
   if(first_offer>=0&&(last_ack<0||last_ack==ticks))begin
    profile_cycles++;
    if(start_tick<0)profile_pre_start++;
    else if(committed<input_words)profile_load_overlap++;
    else profile_tail++;
    if(loader_valid&&loader_ready)profile_accept_loader++;
    else if(cv&&cq)begin if(cread)profile_accept_read++;else profile_accept_write++;end
    else begin
     if(fcv&&!fcq)profile_block_fabric++;else profile_idle_no_offer++;
     if(start_tick<0)profile_idle_before_start++;
     else if(committed<input_words)profile_idle_overlap++;
     else profile_idle_tail++;
     if(loader_valid&&lc>lr)profile_producer_pending_no_grant++;
    end
    profile_core_cycles=core_cycles;
   end''')
tb=once(tb,'   lc=0;lr=0;ec=0;er=0;mc=0;mr=0;sc=0;sr=0;committed=0;committed_previous=0;watermark=SOURCE;','''   lc=0;lr=0;ec=0;er=0;mc=0;mr=0;sc=0;sr=0;committed=0;committed_previous=0;watermark=SOURCE;
   profile_cycles=0;profile_accept_loader=0;profile_accept_read=0;profile_accept_write=0;
   profile_block_fabric=0;profile_idle_no_offer=0;profile_pre_start=0;profile_load_overlap=0;profile_tail=0;
   profile_idle_before_start=0;profile_idle_overlap=0;profile_idle_tail=0;profile_producer_pending_no_grant=0;profile_core_cycles=0;''')
tb=once(tb,'   active=0;loader_valid=0;start_valid=0;loader_fault=0;producer_stop=0;repeat(5)@(negedge clk);','''   if(mode<=2)begin
    if(profile_cycles!=last_ack-first_offer+1||profile_accept_loader!=lc||profile_accept_read!=engine_reads||profile_accept_write!=engine_writes||
       profile_cycles!=profile_accept_loader+profile_accept_read+profile_accept_write+profile_block_fabric+profile_idle_no_offer||
       profile_cycles!=profile_pre_start+profile_load_overlap+profile_tail)$fatal(1,"profile partition incomplete");
   end
   $display("LOADER_PROFILE id=%0d producer_limit_one=%0d cycles=%0d loader_accept=%0d read_accept=%0d write_accept=%0d blocked_fabric=%0d no_routed_offer=%0d pre_start=%0d load_overlap=%0d post_load_tail=%0d idle_before_start=%0d idle_overlap=%0d idle_tail=%0d producer_pending_without_grant=%0d core_cycles_at_final=%0d",id,PRODUCER_LIMIT_ONE,profile_cycles,profile_accept_loader,profile_accept_read,profile_accept_write,profile_block_fabric,profile_idle_no_offer,profile_pre_start,profile_load_overlap,profile_tail,profile_idle_before_start,profile_idle_overlap,profile_idle_tail,profile_producer_pending_no_grant,profile_core_cycles);
   active=0;loader_valid=0;start_valid=0;loader_fault=0;producer_stop=0;repeat(5)@(negedge clk);''')
(HERE/'tb_streaming_loader_profile.sv').write_text(tb,newline='\n')
runner=(HERE.parent/'run_checks.py').read_text()
runner=once(runner,"p.add_argument('--reuse-build',type=Path)","p.add_argument('--reuse-build',type=Path)\n p.add_argument('--queued-loader',action='store_true',help='Conditional platform source with up to four pending writes; not current E203 or official loader')")
runner=once(runner,"ROOT/'build/streaming_loader_study'","ROOT/'build/streaming_loader_profile'")
runner=once(runner,"tb=HERE/'test/tb_streaming_loader.sv'","tb=HERE/'test/tb_streaming_loader_profile.sv'")
runner=once(runner,"schema='qingyu-conditional-streaming-loader-checks-v1'","schema='qingyu-conditional-streaming-loader-profile-v1',producer_one_per_port=not a.queued_loader")
runner=once(runner,"'Official loader start remains unresolved'","'Official loader start remains unresolved','Queued mode is an unverified producer capability hypothesis; not actual CPU'")
runner=once(runner,"signature=dict(tool=version,options=options",'''options.append("-DLOADER_ONE_PER_PORT=2'b00" if a.queued_loader else "-DLOADER_ONE_PER_PORT=2'b01")
  signature=dict(tool=version,options=options''')
runner=once(runner,"   primary=cases[0];secondary=cases[1]","""   profiles=[{k:int(v) for k,v in re.findall(r'(\\w+)=(-?\\d+)',line)} for line in text.splitlines() if line.startswith('LOADER_PROFILE ')]
   if len(profiles)!=len(cases):raise ValueError('Incomplete profile partitions')
   primary=cases[0];secondary=cases[1]""")
runner=once(runner,"cases=cases,serial=cases[2],serial_back_to_back=cases[3],","cases=cases,profiles=profiles,primary_profile=profiles[0],serial=cases[2],serial_back_to_back=cases[3],")
(HERE.parent/'run_profile.py').write_text(runner,newline='\n')
print('Prepared independent profile fixture; frozen baseline files unchanged')
