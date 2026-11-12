`timescale 1ns/1ps
`default_nettype none
module tb_winograd_array8;
    logic clk=0, rst_n=0;
    always #5 clk=~clk;
    logic start_valid=0, start_ready, load_valid=0, load_ready;
    logic [31:0] load_data=0, out_data;
    logic out_valid, out_ready=0, busy, done, error;
    logic [8:0] out_word_index;
    logic [31:0] total_cycles, load_cycles, factor_cycles, compute_cycles, store_cycles;
    logic [31:0] input_mem [0:1867], output_mem [0:395], acc_mem [0:1583];
    string vectors_root;
    integer seed=2039, junk, case_count=214, case_id=0, variant=0;
    integer cycle=0, start_tick=0, final_output_tick=0, final_load_tick=0;
    integer accepted=0, returned=0, completed=0, aborted=0, checked_accumulators=0;
    integer successful=0, expected_errors=0, error_expected=0, active=0;
    integer random_stalls=0, force_output_stall=0, stalled_cycles=0;
    integer first_expected_cycles=-1, stage_sum, observed_acc, reset_count=0;
    logic old_stall=0;
    logic [31:0] held_data=0;
    logic [8:0] held_index=0;
    logic signed [23:0] held_acc [0:3];

    winograd_array8 dut(.*);

    always @(negedge clk) out_ready = !force_output_stall && (!random_stalls || $urandom%4!=0);
    always @(posedge clk) begin
        cycle=cycle+1;
        if (!rst_n) begin
            if (active) aborted=aborted+1;
            active=0; accepted=0; returned=0; old_stall=0;
        end else begin
            if (busy && start_ready) $fatal(1,"start accepted while task busy");
            if (start_valid && start_ready) begin
                active=1; accepted=0; returned=0; start_tick=cycle;
            end
            if (load_valid && load_ready) begin
                if (!active || accepted>=1868) $fatal(1,"Unexpected input acceptance");
                if (load_data !== input_mem[accepted]) $fatal(1,"Loader source changed");
                accepted=accepted+1; final_load_tick=cycle;
            end
            if (old_stall) begin
                stalled_cycles=stalled_cycles+1;
                if (!out_valid || out_data!==held_data || out_word_index!==held_index)
                    $fatal(1,"Packed output changed under backpressure");
                for (integer b=0;b<4;b=b+1)
                    if (dut.corrected[b] !== held_acc[b]) $fatal(1,"Corrected accumulator changed while held");
            end
            old_stall=out_valid && !out_ready;
            held_data=out_data; held_index=out_word_index;
            for (integer b=0;b<4;b=b+1) held_acc[b]=dut.corrected[b];
            if (out_valid && out_ready) begin
                if (!active || accepted!=1868 || returned>=396 || error_expected) $fatal(1,"Unexpected output");
                if (out_word_index !== 9'(returned) || out_data !== output_mem[returned])
                    $fatal(1,"Output mismatch case=%0d word=%0d index=%0d got=%h expected=%h",case_id,returned,out_word_index,out_data,output_mem[returned]);
                for (integer b=0;b<4;b=b+1) begin
                    observed_acc=$signed(dut.corrected[b]);
                    if (observed_acc !== $signed(acc_mem[returned*4+b]))
                        $fatal(1,"Pre-RNE accumulator mismatch case=%0d element=%0d got=%0d expected=%0d",case_id,returned*4+b,observed_acc,$signed(acc_mem[returned*4+b]));
                    checked_accumulators=checked_accumulators+1;
                end
                returned=returned+1; final_output_tick=cycle;
            end
            if (done) begin
                if (!active || busy || error!==1'(error_expected) || accepted!=1868) $fatal(1,"Completion contract violated");
                stage_sum=int'(load_cycles)+int'(factor_cycles)+int'(compute_cycles)+int'(store_cycles);
                if (stage_sum!=int'(total_cycles)) $fatal(1,"Phase counters do not cover complete block window");
                if (error_expected) begin
                    if (returned!=0 || int'(total_cycles)!=final_load_tick-start_tick) $fatal(1,"Bad metadata escaped to compute");
                    expected_errors=expected_errors+1;
                end else begin
                    if (returned!=396 || int'(total_cycles)!=final_output_tick-start_tick) $fatal(1,"Incomplete output/final-ACK timing");
                    if (!random_stalls) begin
                        if (first_expected_cycles==-1) first_expected_cycles=int'(total_cycles);
                        if (int'(total_cycles)!=first_expected_cycles) $fatal(1,"Data-dependent fast compute cycles");
                    end
                    successful=successful+1;
                end
                $display("TASK case=%0d variant=%0d error=%0d cycles=%0d load=%0d factor=%0d compute=%0d store=%0d outputs=%0d",
                         case_id,variant,error_expected,total_cycles,load_cycles,factor_cycles,compute_cycles,store_cycles,returned);
                completed=completed+1; active=0;
            end
        end
        if (cycle>3000000) $fatal(1,"Global timeout");
    end

    task automatic load_case(input integer number);
        string filename;
        begin
            case_id=number;
            filename=$sformatf("%s/case%04d_input.hex",vectors_root,number); $readmemh(filename,input_mem,0,1867);
            filename=$sformatf("%s/case%04d_output.hex",vectors_root,number); $readmemh(filename,output_mem,0,395);
            filename=$sformatf("%s/case%04d_acc.hex",vectors_root,number); $readmemh(filename,acc_mem,0,1583);
        end
    endtask
    task automatic reset_block;
        begin
            @(negedge clk); rst_n=0; start_valid=0; load_valid=0;
            repeat(3) @(posedge clk);
            @(negedge clk); rst_n=1; reset_count=reset_count+1;
        end
    endtask
    task automatic start_task;
        begin
            @(negedge clk); start_valid=1;
            do @(posedge clk); while(!start_ready);
            @(negedge clk); start_valid=0;
        end
    endtask
    task automatic send_words(input integer count);
        begin
            for(integer i=0;i<count;i=i+1) begin
                if(random_stalls && $urandom%4==0) begin @(negedge clk); load_valid=0; end
                @(negedge clk); load_valid=1; load_data=input_mem[i];
                do @(posedge clk); while(!load_ready);
            end
            @(negedge clk); load_valid=0;
        end
    endtask
    task automatic run_case(input integer number);
        integer target;
        begin
            load_case(number); target=completed+1;
            start_task(); send_words(1868); wait(completed==target);
            @(negedge clk);
        end
    endtask

    integer n,target;
    initial begin
        if(!$value$plusargs("VECTORS=%s",vectors_root)) $fatal(1,"Missing vector directory");
        junk=$value$plusargs("SEED=%d",seed);
        junk=$value$plusargs("CASES=%d",case_count);
        junk=$urandom(seed);
        reset_block();
        for(n=0;n<case_count;n=n+1) run_case(n);
        variant=1; random_stalls=1;
        run_case(0); run_case(case_count-1); run_case(0);
        random_stalls=0;
        variant=2; load_case(0); start_task(); send_words(17); reset_block(); run_case(0);
        variant=3; load_case(0); start_task(); send_words(1868);
        wait(dut.state_q==dut.CF_READ && dut.pair_q==10); reset_block(); run_case(0);
        variant=4; load_case(0); start_task(); send_words(1868);
        wait(dut.state_q==dut.DOT_READ && dut.pair_q==10); reset_block(); run_case(0);
        variant=5; force_output_stall=1; load_case(0); start_task(); send_words(1868);
        wait(out_valid); repeat(12) @(posedge clk); reset_block(); force_output_stall=0; run_case(0);
        variant=6; load_case(0); start_task(); send_words(1868);
        wait(returned==10); reset_block(); run_case(0);
        for(n=0;n<2;n=n+1) begin
            variant=7+n; load_case(0); error_expected=1;
            input_mem[n==0?1864:1867]=32'h00000030;
            target=completed+1; start_task(); send_words(1868); wait(completed==target);
            @(negedge clk); error_expected=0; run_case(0);
        end
        if(stalled_cycles==0 || aborted!=5 || expected_errors!=2 || reset_count!=6) $fatal(1,"Required scenario missing");
        $display("PASS array8 real_or_synthetic_cases=%0d successful=%0d accumulator_checks=%0d resets=%0d aborted=%0d errors=%0d stalled=%0d fast_cycles=%0d total_cycles=%0d",
                 case_count,successful,checked_accumulators,reset_count,aborted,expected_errors,stalled_cycles,first_expected_cycles,cycle);
        $finish;
    end
endmodule
`default_nettype wire
