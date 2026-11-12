`timescale 1ns/1ps
`default_nettype none
module tb_read_ahead;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst_n = 0, cache_clear = 0;
    reg icb_cmd_valid = 0, icb_cmd_read = 1;
    wire icb_cmd_ready;
    reg [31:0] icb_cmd_addr = 0, icb_cmd_wdata = 0;
    reg [3:0] icb_cmd_wmask = 0;
    wire icb_rsp_valid, icb_rsp_err;
    reg icb_rsp_ready = 0;
    wire [31:0] icb_rsp_rdata;
    wire ram_cs, ram_we;
    wire [16:0] ram_addr;
    wire [31:0] ram_wdata;
    wire [3:0] ram_wmask;
    reg [31:0] ram_rdata = 32'hxxxxxxxx;

    qingyu_shared_read_ahead dut (.*);

    // Independent memories: physical model follows RAM pins; golden memory
    // follows accepted ICB commands only. No hierarchical DUT state is read.
    reg [31:0] memory [0:131071];
    reg [31:0] golden [0:131071];
    reg [31:0] expected_data [0:32767];
    reg expected_error [0:32767];
    integer head = 0, tail = 0;
    integer commands = 0, responses = 0, aborted = 0;
    integer reads = 0, writes = 0, invalids = 0;
    integer macro_reads = 0, macro_writes = 0;
    integer same_edge_reads = 0, same_edge_writes = 0;
    integer held_checks = 0, clear_edges = 0, reset_edges = 0;
    integer cycle_count = 0, phase = 0;
    integer sequence_gap_sum = 0, sequence_warm_max_gap = 0;
    integer sequence_macro_reads = 0;
    reg response_held = 0, command_held = 0;
    reg [32:0] held_response;
    reg [68:0] held_command;
    reg [31:0] rng_state;
    integer seed = 17;
    integer b;
    reg accepted, good, expected_write;

    function automatic [31:0] random32;
        reg [31:0] value;
        begin
            value = rng_state;
            value = value ^ (value << 13);
            value = value ^ (value >> 17);
            value = value ^ (value << 5);
            rng_state = value;
            random32 = value;
        end
    endfunction

    always @(posedge clk) begin
        cycle_count = cycle_count + 1;
        if (cycle_count > 200000) $fatal(1, "watchdog phase=%0d", phase);
        accepted = icb_cmd_valid && icb_cmd_ready;
        good = icb_cmd_addr >= 32'ha0000000 && icb_cmd_addr <= 32'ha007ffff
               && icb_cmd_addr[1:0] == 0;
        expected_write = rst_n && accepted && good && !icb_cmd_read;
        if (ram_cs && ram_we) begin
            if (!expected_write || ram_addr !== icb_cmd_addr[18:2]
                || ram_wdata !== icb_cmd_wdata || ram_wmask !== icb_cmd_wmask)
                $fatal(1, "unowned/mismatched RAM write phase=%0d", phase);
        end
        if (expected_write && !(ram_cs && ram_we))
            $fatal(1, "accepted write did not commit at its edge phase=%0d", phase);
        if (rst_n && accepted && !good && ram_cs)
            $fatal(1, "invalid/unaligned command accessed RAM phase=%0d", phase);
        if ((!rst_n || cache_clear) && ram_cs)
            $fatal(1, "RAM operation during reset/clear phase=%0d", phase);

        if (ram_cs) begin
            if (ram_we) begin
                for (b=0; b<4; b=b+1)
                    if (ram_wmask[b]) memory[ram_addr][8*b+:8] <= ram_wdata[8*b+:8];
                // A real single-port macro need not retain Q on any write,
                // including a zero-byte-enable command.
                ram_rdata <= 32'hxxxxxxxx;
                macro_writes = macro_writes + 1;
            end else begin
                ram_rdata <= memory[ram_addr];
                macro_reads = macro_reads + 1;
            end
        end

        if (!rst_n) begin
            if (icb_cmd_ready || icb_rsp_valid)
                $fatal(1, "handshake visible during reset");
            aborted = aborted + tail - head;
            head = tail;
            response_held = 0;
            command_held = 0;
            reset_edges = reset_edges + 1;
        end else begin
            if (!cache_clear && head == tail && icb_cmd_ready !== 1'b1)
                $fatal(1, "idle controller failed to offer command ready phase=%0d", phase);
            if (head != tail && icb_cmd_ready !== 1'b0)
                $fatal(1, "controller offered command ready while response pending phase=%0d", phase);
            if (cache_clear) begin
                clear_edges = clear_edges + 1;
                if (icb_cmd_ready) $fatal(1, "clear accepted a new command");
            end
            if (response_held) begin
                held_checks = held_checks + 1;
                if (!icb_rsp_valid || {icb_rsp_err,icb_rsp_rdata} !== held_response)
                    $fatal(1, "response changed while held phase=%0d cycle=%0d", phase, cycle_count);
            end
            if (command_held && (!icb_cmd_valid ||
                {icb_cmd_read,icb_cmd_addr,icb_cmd_wdata,icb_cmd_wmask} !== held_command))
                $fatal(1, "TB command changed before acceptance");
            if (accepted) begin
                if (tail != head) $fatal(1, "accepted command while old response pending phase=%0d", phase);
                if (tail >= 32768) $fatal(1, "scoreboard overflow");
                expected_error[tail] = !good;
                expected_data[tail] = good && icb_cmd_read ? golden[icb_cmd_addr[18:2]] : 32'b0;
                tail = tail + 1;
                commands = commands + 1;
                if (!good) invalids = invalids + 1;
                else if (icb_cmd_read) reads = reads + 1;
                else begin
                    writes = writes + 1;
                    for (b=0; b<4; b=b+1)
                        if (icb_cmd_wmask[b]) golden[icb_cmd_addr[18:2]][8*b+:8] = icb_cmd_wdata[8*b+:8];
                end
                if (icb_rsp_valid && icb_rsp_ready && good) begin
                    if (icb_cmd_read) same_edge_reads = same_edge_reads + 1;
                    else same_edge_writes = same_edge_writes + 1;
                end
            end
            if (icb_rsp_valid) begin
                if (head == tail) $fatal(1, "unsolicited response phase=%0d", phase);
                if (icb_rsp_err !== expected_error[head] || icb_rsp_rdata !== expected_data[head])
                    $fatal(1, "response mismatch phase=%0d cycle=%0d index=%0d got=%h/%b expected=%h/%b", phase,
                           cycle_count, head, icb_rsp_rdata, icb_rsp_err, expected_data[head], expected_error[head]);
                if (icb_rsp_ready) begin
                    responses = responses + 1;
                    head = head + 1;
                end
            end
            response_held = icb_rsp_valid && !icb_rsp_ready;
            held_response = {icb_rsp_err,icb_rsp_rdata};
            command_held = icb_cmd_valid && !icb_cmd_ready;
            held_command = {icb_cmd_read,icb_cmd_addr,icb_cmd_wdata,icb_cmd_wmask};
        end
    end

    task automatic clear_cache;
        begin
            @(negedge clk); cache_clear=1;
            @(negedge clk); cache_clear=0;
        end
    endtask

    // One transaction; command acceptance is allowed even when response ready
    // is low. clear_at is an index into the held-response cycles, or -1.
    task automatic transfer(input reg rd, input reg [31:0] address,
                            input reg [31:0] data, input reg [3:0] mask,
                            input integer stalls, input integer clear_at,
                            output integer zero_response);
        integer wanted, timeout, j;
        reg taken;
        begin
            wanted = responses + 1;
            @(negedge clk);
            icb_cmd_valid=1; icb_cmd_read=rd; icb_cmd_addr=address;
            icb_cmd_wdata=data; icb_cmd_wmask=mask;
            icb_rsp_ready=(stalls==0); cache_clear=0;
            taken=0; timeout=0; zero_response=0;
            while (!taken) begin
                @(posedge clk);
                taken=icb_cmd_ready;
                if(taken) zero_response=icb_rsp_valid;
                #1;
                timeout=timeout+1;
                if(timeout>16) $fatal(1,"command acceptance timeout phase=%0d",phase);
            end
            @(negedge clk); icb_cmd_valid=0;
            for(j=0;j<stalls;j=j+1) begin
                icb_rsp_ready=0; cache_clear=(j==clear_at);
                @(posedge clk); #1;
                @(negedge clk);
            end
            cache_clear=0; icb_rsp_ready=1; timeout=0;
            while(responses<wanted) begin
                @(posedge clk); #1; timeout=timeout+1;
                if(timeout>16) $fatal(1,"response timeout phase=%0d",phase);
            end
            @(negedge clk);
        end
    endtask

    // No bubble is inserted between read A and the offered write. The write
    // therefore meets the just-returned prefetched Q at its next macro edge.
    task automatic prefetch_write(input reg alias_write, input reg [3:0] mask);
        integer done, wanted, timeout, fast;
        reg taken;
        reg [31:0] destination;
        begin
            clear_cache();
            destination=alias_write ? 32'ha0010004 : 32'ha0010100;
            wanted=responses+2; done=0; timeout=0;
            @(negedge clk);
            icb_cmd_valid=1;icb_cmd_read=1;icb_cmd_addr=32'ha0010000;
            icb_cmd_wdata=0;icb_cmd_wmask=0;icb_rsp_ready=1;
            while(done<2) begin
                @(posedge clk); taken=icb_cmd_ready; #1;
                if(taken) done=done+1;
                timeout=timeout+1;
                if(timeout>12) $fatal(1,"prefetch/write timeout");
                @(negedge clk);
                if(done==1) begin
                    icb_cmd_read=0;icb_cmd_addr=destination;
                    icb_cmd_wdata=32'hf0a5963c ^ mask;icb_cmd_wmask=mask;
                end else if(done==2) icb_cmd_valid=0;
            end
            while(responses<wanted) begin @(posedge clk); #1; end
            transfer(1,32'ha0010004,0,0,0,-1,fast);
            if(alias_write && fast) $fatal(1,"alias write did not invalidate prefetched entry");
            if(!alias_write && !fast) $fatal(1,"unrelated write lost prefetched data");
        end
    endtask

    task automatic sequential_reads;
        integer done, tick, last_tick, gap, before_reads, wanted;
        reg taken;
        begin
            clear_cache();
            done=0;tick=0;last_tick=-1;before_reads=macro_reads;
            wanted=responses+1024;
            @(negedge clk);
            icb_cmd_valid=1;icb_cmd_read=1;icb_cmd_addr=32'ha0020000;
            icb_cmd_wdata=0;icb_cmd_wmask=0;icb_rsp_ready=1;
            while(done<1024) begin
                @(posedge clk);taken=icb_cmd_ready;#1;tick=tick+1;
                if(taken) begin
                    if(last_tick>=0) begin
                        gap=tick-last_tick;
                        sequence_gap_sum=sequence_gap_sum+gap;
                        if(done>=2) begin
                            if(gap>sequence_warm_max_gap) sequence_warm_max_gap=gap;
                            if(gap!=1) $fatal(1,"sequential warm II not 1 at word=%0d gap=%0d",done,gap);
                        end
                    end
                    last_tick=tick;done=done+1;
                end
                if(tick>1100) $fatal(1,"sequential timeout");
                @(negedge clk);
                icb_cmd_addr=32'ha0020000+4*done;
                if(done==1024) icb_cmd_valid=0;
            end
            while(responses<wanted) begin @(posedge clk);#1;end
            repeat(3) @(negedge clk);
            sequence_macro_reads=macro_reads-before_reads;
            if(sequence_macro_reads!=1025)
                $fatal(1,"sequential macro reads expected 1024+1 speculative, got %0d",sequence_macro_reads);
        end
    endtask

    task automatic random_traffic;
        integer sent, tick, low_remaining;
        reg taken, need_command;
        reg [31:0] value;
        reg [16:0] stream_a, stream_b;
        begin
            sent=0;tick=0;low_remaining=0;need_command=1;
            stream_a=17'h0c000;stream_b=17'h0c400;
            while(sent<2400) begin
                @(negedge clk);
                if(need_command) begin
                    value=random32();
                    case(value[3:0])
                        0: icb_cmd_addr=32'h9ffffffc;
                        1: icb_cmd_addr=32'ha0080000;
                        2: icb_cmd_addr=32'ha0030001;
                        3,4,5,6: begin icb_cmd_addr=32'ha0000000+{13'b0,stream_a,2'b0};stream_a=stream_a+1;end
                        7,8,9: begin icb_cmd_addr=32'ha0000000+{13'b0,stream_b,2'b0};stream_b=stream_b+1;end
                        default: icb_cmd_addr=32'ha0030000+((value>>8)&32'h00000ffc);
                    endcase
                    icb_cmd_read=value[4] || value[5];
                    icb_cmd_wmask=value[11:8];icb_cmd_wdata=random32();
                    icb_cmd_valid=1;need_command=0;
                end
                value=random32();
                if(low_remaining>0) begin icb_rsp_ready=0;low_remaining=low_remaining-1;end
                else if(value[5:0]==0) begin low_remaining=6+value[10:6];icb_rsp_ready=0;end
                else icb_rsp_ready=value[2:0]!=0;
                cache_clear=value[15:11]==0;
                @(posedge clk);taken=icb_cmd_ready && icb_cmd_valid;#1;
                tick=tick+1;
                if(taken) begin sent=sent+1;need_command=1;end
                if(tick>40000) $fatal(1,"random timeout sent=%0d",sent);
            end
            @(negedge clk);icb_cmd_valid=0;cache_clear=0;icb_rsp_ready=1;
            repeat(5) @(negedge clk);
            if(head!=tail) $fatal(1,"random response did not drain");
        end
    endtask

    integer i, fast, before_reads, wanted;
    initial begin
        if (!$value$plusargs("SEED=%d",seed)) seed=17;
        rng_state=seed==0 ? 32'h1 : seed;
        for(i=0;i<131072;i=i+1) begin
            memory[i]=32'h7139ab42 ^ (i*32'h10204081);
            golden[i]=memory[i];
        end
        repeat(3) @(negedge clk);
        rst_n=1;icb_rsp_ready=1;

        phase=1;
        for(i=0;i<16;i=i+1) begin
            transfer(0,32'ha0000100,32'hf1e2d3c4 ^ i,i[3:0],6,-1,fast);
            transfer(1,32'ha0000100,0,0,6,-1,fast);
        end
        phase=2;
        transfer(1,32'h9ffffffc,0,0,6,2,fast);
        transfer(1,32'ha0080000,0,0,0,-1,fast);
        transfer(0,32'ha0080000,32'hbadbadba,15,6,-1,fast);
        transfer(1,32'ha0000001,0,0,6,-1,fast);
        transfer(0,32'ha0000002,32'hbadbadba,15,0,-1,fast);
        transfer(1,32'ha007ffff,0,0,0,-1,fast);

        phase=3;
        for(i=0;i<16;i=i+1) begin
            prefetch_write(1,i[3:0]);
            prefetch_write(0,i[3:0]);
        end

        phase=4;
        clear_cache();
        transfer(1,32'ha0004000,0,0,8,0,fast);
        if(fast) $fatal(1,"cold read unexpectedly hit");
        transfer(1,32'ha0004004,0,0,0,-1,fast);
        if(fast) $fatal(1,"clear of pending miss retained refill eligibility");
        transfer(1,32'ha0004008,0,0,8,2,fast);
        if(!fast) $fatal(1,"directed held-hit setup did not hit");
        transfer(1,32'ha000400c,0,0,0,-1,fast);
        if(fast) $fatal(1,"held-hit clear did not invalidate lookahead");
        transfer(0,32'ha0004100,32'h12345678,15,8,1,fast);
        transfer(1,32'ha0004100,0,0,0,-1,fast);

        phase=5;
        clear_cache();before_reads=macro_reads;
        transfer(1,32'ha007fffc,0,0,0,-1,fast);
        repeat(3) @(negedge clk);
        if(macro_reads-before_reads!=1) $fatal(1,"last-word prefetch crossed boundary");
        transfer(1,32'ha0000000,0,0,0,-1,fast);
        if(fast) $fatal(1,"last word wrapped prefetch to first word");
        transfer(1,32'ha0003ffc,0,0,0,-1,fast);
        transfer(1,32'ha0004000,0,0,0,-1,fast);

        phase=6;
        sequential_reads();

        phase=7;
        // Reset aborts an accepted read response, but never clears SRAM.
        clear_cache();
        @(negedge clk);icb_cmd_valid=1;icb_cmd_read=1;icb_cmd_addr=32'ha0000100;icb_rsp_ready=0;
        @(posedge clk);if(!icb_cmd_ready)$fatal(1,"reset test not accepted");#1;
        @(negedge clk);icb_cmd_valid=0;rst_n=0;
        repeat(2) @(negedge clk);
        rst_n=1;icb_rsp_ready=1;
        repeat(3) @(negedge clk);
        transfer(1,32'ha0000100,0,0,0,-1,fast);
        if(fast)$fatal(1,"reset did not clear cache");

        phase=8;
        random_traffic();
        repeat(8) @(negedge clk);
        if(head!=tail || commands!=responses+aborted) $fatal(1,"final accounting mismatch");
        for(i=0;i<131072;i=i+1)
            if(memory[i]!==golden[i]) $fatal(1,"physical memory mismatch index=%0d",i);
        $display("PASS read_ahead seed=%0d commands=%0d responses=%0d aborted=%0d reads=%0d writes=%0d invalid=%0d macro_reads=%0d macro_writes=%0d same_edge_reads=%0d same_edge_writes=%0d held_checks=%0d clear_edges=%0d sequential_gap_sum=%0d sequential_warm_max_gap=%0d sequential_macro_reads=%0d",seed,commands,responses,aborted,reads,writes,invalids,macro_reads,macro_writes,same_edge_reads,same_edge_writes,held_checks,clear_edges,sequence_gap_sum,sequence_warm_max_gap,sequence_macro_reads);
        $finish;
    end
endmodule
`default_nettype wire
