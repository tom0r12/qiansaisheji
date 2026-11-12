`timescale 1ns/1ps
`default_nettype none
module tb_winograd_task8;
    logic clk=0,rst_n=0;
    always #5 clk=~clk;
    logic begin_valid=0,begin_ready,x_valid=0,x_ready,w_valid=0,w_ready,meta_valid=0,meta_ready;
    logic [31:0] x_data=0,w_data=0,meta_data=0,out_data;
    logic [2:0] pair_group,pair_done_index;
    logic [1:0] pair_slot_base;
    logic x_done,pair_loaded,pair_done,out_valid,out_ready=0,busy,done,error;
    logic [3:0] out_tile;
    logic [8:0] out_word_index;
    logic [31:0] total_cycles,load_cycles,factor_cycles,cache_read_cycles,compute_cycles,store_cycles;
    logic [31:0] x_mem[0:1599],w_mem[0:4095],meta_mem[0:191],output_mem[0:6335],acc_mem[0:25343],r_mem[0:98],c_mem[0:255];
    string vectors_root;
    integer seed=2371,junk,case_count=22,case_id=0,variant=0,cycle=0,start_tick=0,final_output_tick=0,final_meta_tick=0;
    integer nx=0,nw=0,nm=0,ny=0,nxr=0,nwr=0,nr=0,nc=0,nxd=0,npl=0,npd=0;
    integer successful=0,completed=0,aborted=0,errors=0,reset_count=0,checked_accumulators=0,stalled_cycles=0;
    logic random_stalls=0,force_output_stall=0,active=0;
    integer error_group=-1,fast_cycles=-1;
    integer nr_reads=0,snapshots=0,overlap_outputs=0,replaced_snapshots=0,all_replacements=0;
    integer burst_writes=0,overlap_load_words=0,overlap_meta_writes=0,error_held_contexts=0;
    logic [3:0] reserved_slots=0;
    integer reserved_tile[0:3];
    logic [2:0] old_burst_hold=0;
    logic [255:0] held_burst_data[0:2];
    logic [6:0] held_burst_addr[0:2];
    logic x_ack=0,w_ack=0,meta_ack=0,old_stall=0;
    logic [31:0] held_data=0;
    logic [3:0] held_tile=0;
    logic [8:0] held_index=0;
    logic signed [23:0] held_acc[0:3];
    integer rp,kp,lp,g,col,expected_bank,expected_addr,observed_acc,stage_sum;
    logic [47:0] expected_metadata;
    winograd_int8_task8 dut(.*);

    // Independent producers may offer the next stream/group before its ready.
    // Payload is only replaced after a real acceptance recorded at posedge.
    always @(negedge clk) begin
        out_ready=!force_output_stall && (!random_stalls || $urandom%4!=0);
        if(!rst_n || !active) begin x_valid=0;w_valid=0;meta_valid=0;end
        else begin
            if(!x_valid || x_ack) begin
                x_valid=nx<1600 && (!random_stalls || $urandom%5!=0);
                if(nx<1600) x_data=x_mem[nx];
            end
            if(!w_valid || w_ack) begin
                w_valid=nw<4096 && (!random_stalls || $urandom%5!=0);
                if(nw<4096) w_data=w_mem[nw];
            end
            if(!meta_valid || meta_ack) begin
                meta_valid=nm<192 && (!random_stalls || $urandom%5!=0);
                if(nm<192) meta_data=meta_mem[nm];
            end
        end
    end
    always @(posedge clk) begin
        cycle=cycle+1; x_ack=0;w_ack=0;meta_ack=0;
        if(!rst_n) begin
            if(active) aborted=aborted+1;
            active=0;nx=0;nw=0;nm=0;ny=0;old_stall=0;old_burst_hold=0;
        end else begin
            if(busy && begin_ready) $fatal(1,"BEGIN while busy");
            if(begin_valid && begin_ready) begin
                active=1;start_tick=cycle;nx=0;nw=0;nm=0;ny=0;nxr=0;nwr=0;nr=0;nc=0;nxd=0;npl=0;npd=0;
                nr_reads=0;snapshots=0;overlap_outputs=0;replaced_snapshots=0;
                burst_writes=0;overlap_load_words=0;overlap_meta_writes=0;reserved_slots=0;
            end
            if(x_valid && x_ready) begin
                if(!active || nx>=1600 || x_data!==x_mem[nx]) $fatal(1,"Unexpected X acceptance");
                rp=nx/32;kp=nx%32;
                for(integer b=0;b<8;b=b+1) begin
                    if(dut.x_en[b] && dut.x_we[b]) begin
                        if(b!=((2*rp)%8) && !(2*rp+1<99 && b==((2*rp+1)%8))) $fatal(1,"Wrong X bank");
                        expected_addr=(2*rp/8)*32+kp;
                        if(int'(dut.x_addr[b])!=expected_addr || dut.x_wdata[b]!==x_data[(b%2)*16+:16]) $fatal(1,"Wrong X write address/data");
                        nxr=nxr+1;
                    end
                end
                nx=nx+1;x_ack=1;
            end else if(|dut.x_we) $fatal(1,"X write without accepted source word");
            if(w_valid && w_ready) begin
                if(!active || nw>=4096 || w_data!==w_mem[nw] || int'(pair_group)!=nw/512) $fatal(1,"Unexpected W acceptance");
                g=nw/512;
                if(nw%512==0) begin
                    if(reserved_slots[(g%2)*2] || reserved_slots[(g%2)*2+1]) $fatal(1,"Next group overwrites unreleased slot");
                    reserved_slots[(g%2)*2]=1;reserved_slots[(g%2)*2+1]=1;
                    reserved_tile[(g%2)*2]=g*2;reserved_tile[(g%2)*2+1]=g*2+1;
                end
                if(dut.state_q==dut.DOT_READ || dut.state_q==dut.DOT_WAIT) overlap_load_words=overlap_load_words+1;
                nw=nw+1;w_ack=1;
            end
            for(integer b=0;b<3;b=b+1) begin
                if(old_burst_hold[b] && (!dut.burst_ready_q[b] || dut.burst_data_q[b]!==held_burst_data[b] || dut.burst_addr_q[b]!==held_burst_addr[b])) $fatal(1,"Held W burst changed");
                old_burst_hold[b]=dut.burst_ready_q[b] && !(dut.burst_write && int'(dut.burst_drain_q)==b) && !error && !dut.metadata_fault;
                held_burst_data[b]=dut.burst_data_q[b];held_burst_addr[b]=dut.burst_addr_q[b];
            end
            if(dut.burst_write) begin
                if(dut.w_we!==16'hffff || dut.w_en!==16'hffff || dut.state_q==dut.DOT_READ || nwr+16>nw*2) $fatal(1,"Invalid wide private write grant");
                for(integer b=0;b<16;b=b+1) begin
                    g=nwr/1024;kp=(nwr/2%512)/16;lp=nwr/2%16;
                    expected_bank=2*(lp%8)+nwr%2;expected_addr=((g%2)*2+lp/8)*32+kp;
                    if(b!=expected_bank || int'(dut.w_addr[b])!=expected_addr || dut.w_wdata[b]!==w_mem[nwr/2][(nwr%2)*16+:16]) $fatal(1,"Delayed W macro commit mismatch word=%0d bank=%0d",nwr/2,b);
                    if(!reserved_slots[(g%2)*2+lp/8] || reserved_tile[(g%2)*2+lp/8]!=g*2+lp/8) $fatal(1,"W commit to stale epoch");
                    nwr=nwr+1;
                end
                burst_writes=burst_writes+1;
            end else if(|dut.w_we) $fatal(1,"W write without full burst grant");
            if(meta_valid && meta_ready) begin
                if(!active || nm>=192 || meta_data!==meta_mem[nm] || int'(pair_group)!=nm/24) $fatal(1,"Unexpected metadata acceptance");
                nm=nm+1;meta_ack=1;final_meta_tick=cycle;
            end
            if(dut.r_en && dut.r_we) begin
                if(nr>=99 || int'(dut.r_addr)!=nr || dut.r_wdata!==r_mem[nr]) $fatal(1,"R cache mismatch row=%0d got=%h expected=%h",nr,dut.r_wdata,r_mem[nr]);
                nr=nr+1;
            end
            if(dut.r_en && !dut.r_we) begin
                if(dut.state_q!=dut.DOT_READ || int'(dut.r_addr)!=nr_reads%99) $fatal(1,"Wrong overlapped R prefetch");
                nr_reads=nr_reads+1;
            end
            if(dut.snapshot_capture) begin
                if(int'(dut.row_group_q)!=snapshots%13 || int'(dut.compute_tile_q)!=snapshots/13) $fatal(1,"Wrong snapshot epoch");
                if(dut.snapshot_valid_q) begin
                    if(!dut.snapshot_last_ack) $fatal(1,"Overwriting occupied snapshot");
                    replaced_snapshots=replaced_snapshots+1;all_replacements=all_replacements+1;
                end
                snapshots=snapshots+1;
            end
            if(dut.m_en && dut.m_we) begin
                if(dut.state_q==dut.DOT_READ || dut.state_q==dut.DOT_WAIT) overlap_meta_writes=overlap_meta_writes+1;
                g=nc/32;col=nc%32;
                expected_metadata={3'b0,meta_mem[g*24+16+col/4][(col%4)*8+:8],meta_mem[g*24+col/2][(col%2)*16+:16],c_mem[nc][20:0]};
                if(nc>=256 || int'(dut.m_addr)!=(g%2)*32+col || dut.m_wdata!==expected_metadata)
                    $fatal(1,"C/bias/shift cache mismatch channel=%0d got=%h expected=%h",nc,dut.m_wdata,expected_metadata);
                nc=nc+1;
            end
            if(x_done) begin if(nx!=1600 || nr!=99 || nxd!=0) $fatal(1,"Early/repeated X factor completion");nxd=nxd+1;end
            if(pair_loaded) begin
                if(nc!=(npl+1)*32 || int'(pair_group)!=npl || nwr<(npl+1)*1024) $fatal(1,"Early/repeated group load completion");
                npl=npl+1;
            end
            if(pair_done) begin
                if(ny!=(npd+1)*792 || int'(pair_done_index)!=npd) $fatal(1,"Pair completion precedes Y ACK");
                npd=npd+1;
            end
            if(old_stall) begin
                stalled_cycles=stalled_cycles+1;
                if(!out_valid || out_data!==held_data || out_tile!==held_tile || out_word_index!==held_index) $fatal(1,"Output changed under stall");
                for(integer b=0;b<4;b=b+1) if(dut.corrected[b]!==held_acc[b]) $fatal(1,"Accumulator changed under stall");
            end
            old_stall=out_valid && !out_ready;held_data=out_data;held_tile=out_tile;held_index=out_word_index;
            for(integer b=0;b<4;b=b+1) held_acc[b]=dut.corrected[b];
            if(out_valid && out_ready) begin
                if(dut.state_q==dut.DOT_READ || dut.state_q==dut.DOT_WAIT) overlap_outputs=overlap_outputs+1;
                if(!active || nx!=1600 || ny>=6336 || (error_group>=0 && ny>=error_group*792)) $fatal(1,"Unexpected output");
                if(int'(out_tile)!=ny/396 || int'(out_word_index)!=ny%396 || out_data!==output_mem[ny])
                    $fatal(1,"Output mismatch case=%0d word=%0d tile=%0d index=%0d got=%h expected=%h",case_id,ny,out_tile,out_word_index,out_data,output_mem[ny]);
                for(integer b=0;b<4;b=b+1) begin
                    observed_acc=int'($signed(dut.corrected[b]));
                    if(observed_acc!==$signed(acc_mem[ny*4+b])) $fatal(1,"Direct accumulator mismatch case=%0d element=%0d got=%0d expected=%0d",case_id,ny*4+b,observed_acc,$signed(acc_mem[ny*4+b]));
                    checked_accumulators=checked_accumulators+1;
                end
                if(!reserved_slots[(ny/396)%4] || reserved_tile[(ny/396)%4]!=ny/396) $fatal(1,"Output uses released/stale slot");
                if(ny%396==395) reserved_slots[(ny/396)%4]=0;
                ny=ny+1;final_output_tick=cycle;
            end
            if(dut.metadata_fault && dut.snapshot_valid_q && !dut.snapshot_last_ack) error_held_contexts=error_held_contexts+1;
            if(done) begin
                if(!active || busy || error!==1'(error_group>=0) || nx!=1600 || nxr!=3168 || nr!=99 || nxd!=1) $fatal(1,"Bad task completion");
                stage_sum=int'(load_cycles)+int'(factor_cycles)+int'(cache_read_cycles)+int'(compute_cycles)+int'(store_cycles);
                if(stage_sum!=int'(total_cycles)) $fatal(1,"Phase counter gap");
                if(error_group>=0) begin
                    if(nw!=(error_group+1)*512 || nwr>nw*2 || nm!=(error_group+1)*24 || nc!=error_group*32 || ny>error_group*792 || npd>error_group || npl!=error_group || int'(total_cycles)!=(final_meta_tick>final_output_tick?final_meta_tick:final_output_tick)-start_tick) $fatal(1,"Metadata fault escaped/early completion");
                    errors=errors+1;
                end else begin
                    if(nw!=4096 || nwr!=8192 || nm!=192 || nc!=256 || ny!=6336 || npl!=8 || npd!=8 || int'(total_cycles)!=final_output_tick-start_tick) $fatal(1,"Incomplete full-task window");
                    if(nr_reads!=1584 || snapshots!=208 || overlap_outputs==0) $fatal(1,"Missing genuine R/output overlap");
                    if(burst_writes!=512 || overlap_load_words==0 || overlap_meta_writes==0 || reserved_slots!=0) $fatal(1,"Missing real loader/macro overlap bursts=%0d load=%0d meta=%0d reserved=%b",burst_writes,overlap_load_words,overlap_meta_writes,reserved_slots);
                    if(!random_stalls) begin
                        if(fast_cycles<0) fast_cycles=int'(total_cycles);
                        if(int'(total_cycles)!=fast_cycles) $fatal(1,"Data dependent fast cycles");
                    end
                    successful=successful+1;
                end
                $display("TASK case=%0d variant=%0d error=%0d cycles=%0d load=%0d factor=%0d cache=%0d compute=%0d store=%0d outputs=%0d r_reads=%0d snapshots=%0d overlap_outputs=%0d replaced=%0d burst_writes=%0d overlap_load=%0d overlap_meta=%0d",case_id,variant,error_group>=0,total_cycles,load_cycles,factor_cycles,cache_read_cycles,compute_cycles,store_cycles,ny,nr_reads,snapshots,overlap_outputs,replaced_snapshots,burst_writes,overlap_load_words,overlap_meta_writes);
                completed=completed+1;active=0;
            end
        end
        if(cycle>3000000) $fatal(1,"Global timeout state=%0d nx=%0d nw=%0d nm=%0d ny=%0d",dut.state_q,nx,nw,nm,ny);
    end
    task automatic load_case(input integer number);
        string f;
        begin
            case_id=number;
            f=$sformatf("%s/case%04d_x.hex",vectors_root,number);$readmemh(f,x_mem);
            f=$sformatf("%s/case%04d_w.hex",vectors_root,number);$readmemh(f,w_mem);
            f=$sformatf("%s/case%04d_meta.hex",vectors_root,number);$readmemh(f,meta_mem);
            f=$sformatf("%s/case%04d_output.hex",vectors_root,number);$readmemh(f,output_mem);
            f=$sformatf("%s/case%04d_acc.hex",vectors_root,number);$readmemh(f,acc_mem);
            f=$sformatf("%s/case%04d_r.hex",vectors_root,number);$readmemh(f,r_mem);
            f=$sformatf("%s/case%04d_c.hex",vectors_root,number);$readmemh(f,c_mem);
        end
    endtask
    task automatic reset_block;
        begin
            @(negedge clk);rst_n=0;begin_valid=0;
            repeat(3) @(posedge clk);
            @(negedge clk);rst_n=1;reset_count=reset_count+1;
        end
    endtask
    task automatic start_task;
        begin
            @(negedge clk);begin_valid=1;
            do @(posedge clk);while(!begin_ready);
            @(negedge clk);begin_valid=0;
        end
    endtask
    task automatic run_case(input integer number);
        integer target;
        begin load_case(number);target=completed+1;start_task();wait(completed==target);@(negedge clk);end
    endtask
    integer n,target;
    initial begin
        if(!$value$plusargs("VECTORS=%s",vectors_root)) $fatal(1,"Missing vectors");
        junk=$value$plusargs("SEED=%d",seed);junk=$value$plusargs("CASES=%d",case_count);junk=$urandom(seed);
        reset_block();
        for(n=0;n<case_count;n=n+1) run_case(n);
        variant=1;random_stalls=1;run_case(0);run_case(case_count-1);random_stalls=0;
        for(n=0;n<7;n=n+1) begin
            variant=2+n;load_case(0);start_task();
            case(n)
                0: wait(nx==31);
                1: wait(nw==513);
                2: wait(nm==10);
                3: wait(dut.loader_q==dut.L_COMMIT && dut.meta_write_q==12);
                4: wait(dut.state_q==dut.DOT_READ && dut.pair_q==4);
                5: wait(dut.state_q==dut.DOT_READ && dut.pair_q==10);
                6: begin
                    force_output_stall=1;wait(out_valid);repeat(64) @(posedge clk);
                    if(!dut.snapshot_valid_q || !dut.dot_all_valid || dut.state_q!=dut.DOT_WAIT) $fatal(1,"Bounded two-context stall not exercised");
                end
            endcase
            reset_block();force_output_stall=0;run_case(0);
        end
        for(n=0;n<2;n=n+1) begin
            variant=9+n;load_case(0);error_group=n==0?0:7;
            meta_mem[error_group*24+(n==0?16:23)]=32'h00000030;
            target=completed+1;start_task();wait(completed==target);@(negedge clk);error_group=-1;run_case(0);
        end
        if(stalled_cycles==0 || aborted!=7 || errors!=2 || reset_count!=8 || all_replacements==0) $fatal(1,"Required scenario missing");
        $display("PASS task8 real_or_synthetic_cases=%0d successful=%0d accumulator_checks=%0d resets=%0d aborted=%0d errors=%0d stalled=%0d fast_cycles=%0d total_cycles=%0d replacements=%0d error_held=%0d",case_count,successful,checked_accumulators,reset_count,aborted,errors,stalled_cycles,fast_cycles,cycle,all_replacements,error_held_contexts);
        $finish;
    end
endmodule
`default_nettype wire
