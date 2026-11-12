`timescale 1ns/1ps
module tb_rowpair_pack;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,start_valid=0,start_mode_w=0,in_valid=0,in_last=0,upstream_error=0,out_ready=0;
    reg [31:0] in_data=0;
    reg [2:0] in_count=4;
    wire start_ready,in_ready,out_valid,out_last,busy,done,error;
    wire [31:0] out_data,total_cycles;
    wire [10:0] out_word_index;
    wire [2:0] error_code;
    rowpair_pack dut(.*);
    reg [31:0] source[0:1583],expected[0:1599];
    integer cycle=0,received=0,first_output=0,last_output=0,max_gap=0;
    integer normal_checks=0,error_checks=0,reset_checks=0,held_checks=0;
    integer seed=17,random_state,discard_random,fd,rc,case_id,mode,inputs,outputs;
    integer previous_output=0;
    reg checking=0,held=0;
    reg [31:0] held_data;
    reg held_last;
    reg [10:0] held_index;
    string manifest,raw_path,gold_path;
    always @(posedge clk) begin
        cycle=cycle+1;
        if (!rst_n) held=0;
        else begin
            if (held) begin
                held_checks=held_checks+1;
                if (!out_valid || out_data!==held_data || out_last!==held_last || out_word_index!==held_index)
                    $fatal(1,"held output changed cycle=%0d",cycle);
            end
            if (checking && out_valid) begin
                if (received>=outputs || out_data!==expected[received] || out_word_index!==11'(received) || out_last!==(received==outputs-1))
                    $fatal(1,"output mismatch case=%0d at=%0d got=%h want=%h index=%0d",case_id,received,out_data,expected[received],out_word_index);
            end
            if (checking && out_valid && out_ready) begin
                if (received==0) first_output=cycle;
                else if (cycle-previous_output>max_gap) max_gap=cycle-previous_output;
                previous_output=cycle;last_output=cycle;received=received+1;
            end
            held=out_valid&&!out_ready;held_data=out_data;held_last=out_last;held_index=out_word_index;
        end
    end
    task automatic reset_all;
        begin
            @(negedge clk);rst_n=0;start_valid=0;in_valid=0;upstream_error=0;out_ready=0;checking=0;
            repeat(2)@(posedge clk);
            @(negedge clk);rst_n=1;
            @(posedge clk);#1;
            if (!start_ready || busy || out_valid || error) $fatal(1,"reset not idle");
        end
    endtask
    task automatic start_frame;
        begin
            @(negedge clk);start_valid=1;start_mode_w=1'(mode);in_valid=0;upstream_error=0;out_ready=0;
            received=0;first_output=0;last_output=0;previous_output=0;max_gap=0;checking=1;
            if(!start_ready)$fatal(1,"START unavailable");
            @(posedge clk);#1;
            if(!busy || error || total_cycles!=1 || start_ready)$fatal(1,"START epoch failed");
            @(negedge clk);start_valid=0;
        end
    endtask
    task automatic normal_frame(input integer stalls);
        integer sent,limit,start_cycle,held_cycles;
        reg fire;
        begin
            start_frame();start_cycle=cycle;sent=0;limit=0;held_cycles=0;
            // start_frame ends at the first input-driving negedge.
            while(!done && limit<60000)begin
                if(!in_valid || fire) begin
                    in_valid=(sent<inputs) && (stalls==0 || $urandom_range(0,4)!=0);
                    in_data=sent<inputs?source[sent]:32'hbad0bad0;
                    in_count=4;in_last=sent==inputs-1;
                end
                out_ready=stalls==0 || $urandom_range(0,3)!=0;
                // Sustained stalls exercise both full slots and held output.
                if(stalls!=0 && limit>=50 && limit<74)out_ready=0;
                if(out_valid&&!out_ready)held_cycles=held_cycles+1;
                @(posedge clk);fire=in_valid&&in_ready;#1;
                if(fire)sent=sent+1;
                if(error)$fatal(1,"normal frame error %0d",error_code);
                if(busy && start_ready)$fatal(1,"active START accepted");
                limit=limit+1;
                if(!done)@(negedge clk);
            end
            if(!done || busy || received!=outputs || sent!=inputs || last_output!=cycle || total_cycles!=32'(cycle-start_cycle+1))
                $fatal(1,"completion mismatch case=%0d sent=%0d got=%0d cycles=%0d total=%0d",case_id,sent,received,cycle-start_cycle+1,total_cycles);
            if(stalls==0 && (max_gap!=1 || total_cycles!=32'(mode==0?1633:529)))
                $fatal(1,"steady bandwidth mismatch gap=%0d cycles=%0d",max_gap,total_cycles);
            if(stalls!=0 && held_cycles==0)$fatal(1,"stalls not reached");
            $display("CASE id=%0d mode=%0d stalls=%0d cycles=%0d inputs=%0d outputs=%0d first_offset=%0d max_output_gap=%0d",case_id,mode,stalls,total_cycles,inputs,outputs,first_output-start_cycle,max_gap);
            normal_checks=normal_checks+1;
            @(negedge clk);in_valid=0;out_ready=0;checking=0;
        end
    endtask
    task automatic send_word(input integer index,input integer count,input reg last_bit);
        reg sent;
        integer timeout;
        begin
            sent=0;timeout=0;
            @(negedge clk);in_valid=1;in_data=source[index];in_count=3'(count);in_last=last_bit;
            while(!sent && timeout<20000)begin
                @(posedge clk);sent=in_ready;#1;timeout=timeout+1;
                if(!sent)@(negedge clk);
            end
            if(!sent)$fatal(1,"input timeout %0d",index);
            @(negedge clk);in_valid=0;
        end
    endtask
    task automatic wait_error_done(input integer wanted);
        integer n;
        begin
            n=0;
            while(!done && n<40)begin @(posedge clk);#1;n=n+1;end
            if(!done || busy || !error || error_code!=3'(wanted))
                $fatal(1,"error completion mismatch expected=%0d error=%0b code=%0d busy=%0b",wanted,error,error_code,busy);
            error_checks=error_checks+1;
            @(negedge clk);upstream_error=0;in_valid=0;out_ready=0;checking=0;
        end
    endtask
    task automatic malformed(input integer kind);
        integer j,fullpair;
        begin
            start_frame();out_ready=1;fullpair=mode==0?32:16;
            case(kind)
                0:begin send_word(0,3,1);wait_error_done(1);end
                1:begin send_word(0,4,1);wait_error_done(2);end
                2:begin
                    for(j=0;j<inputs;j=j+1)send_word(j,4,0);
                    if(!error || error_code!=3)$fatal(1,"missing last not detected");
                    repeat(8)begin @(posedge clk);#1;if(!busy || done)$fatal(1,"missing stream falsely drained");end
                    send_word(0,4,1);wait_error_done(3);
                end
                3:begin
                    // Capture a complete pair, hold an output, then error with
                    // a producer-held prefix beat; both held beats must drain.
                    out_ready=0;
                    for(j=0;j<fullpair;j=j+1)send_word(j,4,0);
                    if(!out_valid)$fatal(1,"no held output");
                    @(negedge clk);upstream_error=1;in_valid=1;in_data=source[fullpair];in_count=4;in_last=0;
                    @(posedge clk);if(!in_ready)$fatal(1,"failed producer prefix not consumed");#1;
                    @(negedge clk);in_valid=0;
                    repeat(8)begin @(posedge clk);#1;if(!busy || done || !out_valid)$fatal(1,"error revoked held word");end
                    @(negedge clk);out_ready=1;wait_error_done(4);
                    if(received!=1)$fatal(1,"new output after upstream error");
                end
                4:begin
                    out_ready=0;
                    for(j=0;j<fullpair;j=j+1)send_word(j,4,0);
                    send_word(fullpair,0,1);
                    repeat(8)begin @(posedge clk);#1;if(!busy || done || !out_valid)$fatal(1,"count error revoked held");end
                    @(negedge clk);out_ready=1;wait_error_done(1);
                    if(received!=1)$fatal(1,"new output after count error");
                end
                5:begin
                    @(negedge clk);upstream_error=1;wait_error_done(4);
                    if(received!=0)$fatal(1,"empty upstream failure produced data");
                end
                6:begin
                    out_ready=0;
                    for(j=0;j<2*fullpair;j=j+1)send_word(j,4,0);
                    if(in_ready)$fatal(1,"two full buffers failed to backpressure input");
                    @(negedge clk);upstream_error=1;in_valid=1;in_data=source[2*fullpair];in_last=0;
                    @(posedge clk);if(!in_ready)$fatal(1,"full buffers prevent producer error drain");#1;
                    @(negedge clk);in_valid=0;
                    repeat(8)begin @(posedge clk);#1;if(!busy || done || !out_valid)$fatal(1,"full buffer error revoked output");end
                    @(negedge clk);out_ready=1;wait_error_done(4);
                    if(received!=1)$fatal(1,"full buffer error generated extra output");
                end
                default:begin
                    // Every unsupported count value; a separate last beat
                    // proves bad count without last must still drain input.
                    send_word(0,kind-7,0);
                    repeat(4)begin @(posedge clk);#1;if(!busy || done)$fatal(1,"count failure falsely drained");end
                    send_word(1,4,1);wait_error_done(1);
                end
            endcase
        end
    endtask
    task automatic reset_final;
        integer sent,limit;
        reg fire;
        begin
            start_frame();sent=0;limit=0;
            while(!(out_valid && out_last) && limit<10000)begin
                in_valid=sent<inputs;in_data=sent<inputs?source[sent]:0;in_count=4;in_last=sent==inputs-1;
                out_ready=received<outputs-1;
                @(posedge clk);fire=in_valid&&in_ready;#1;
                if(fire)sent=sent+1;
                limit=limit+1;@(negedge clk);
            end
            out_ready=0;in_valid=0;
            if(!out_valid || !out_last || sent!=inputs || done)$fatal(1,"last output hold reset not reached");
            repeat(5)begin @(posedge clk);#1;if(done || !busy)$fatal(1,"last word completed without ACK");end
            reset_all();reset_checks=reset_checks+1;normal_frame(0);
        end
    endtask
    task automatic reset_phase(input integer phase);
        integer j,pair_words;
        begin
            start_frame();pair_words=mode==0?32:16;out_ready=phase==2;
            for(j=0;j<(phase==0?7:pair_words);j=j+1)send_word(j,4,0);
            if(phase==1 && !out_valid)$fatal(1,"reset held phase not reached");
            if(phase==2)repeat(4)@(posedge clk);
            reset_all();reset_checks=reset_checks+1;
            normal_frame(0);
        end
    endtask
    initial begin
        if($value$plusargs("SEED=%d",seed))begin end
        random_state=seed;discard_random=$urandom(random_state);
        if(!$value$plusargs("MANIFEST=%s",manifest))$fatal(1,"missing manifest");
        reset_all();fd=$fopen(manifest,"r");if(fd==0)$fatal(1,"manifest open failed");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d %d %d %d %s %s\n",case_id,mode,inputs,outputs,raw_path,gold_path);
            if(rc==6)begin
                $readmemh(raw_path,source,0,inputs-1);$readmemh(gold_path,expected,0,outputs-1);
                normal_frame(0);normal_frame(1);
            end
        end
        $fclose(fd);
        // The fixture set ends with X and W selected again explicitly.
        for(mode=0;mode<2;mode=mode+1)begin
            inputs=mode==0?1584:512;outputs=mode==0?1600:512;
            raw_path=mode==0?"direct_x.raw.hex":"direct_w.raw.hex";
            gold_path=mode==0?"direct_x.gold.hex":"direct_w.gold.hex";
            $readmemh(raw_path,source,0,inputs-1);$readmemh(gold_path,expected,0,outputs-1);
            for(integer kind=0;kind<15;kind=kind+1)if(kind!=11)begin malformed(kind);normal_frame(0);end
            for(integer phase=0;phase<3;phase=phase+1)reset_phase(phase);
            reset_final();
        end
        $display("PASS rowpair normal=%0d errors=%0d resets=%0d held=%0d seed=%0d",normal_checks,error_checks,reset_checks,held_checks,seed);
        $finish;
    end
    initial begin #100000000;$fatal(1,"global timeout");end
endmodule
