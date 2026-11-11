`timescale 1ns/1ps
module tb_weight_stream;
    reg clk=0, rst_n=0;
    always #5 clk=~clk;
    reg cmd_valid=0, cmd_read=0, rsp_ready=0;
    reg [31:0] cmd_addr, payload;
    reg [3:0] cmd_mask=15;
    wire cmd_ready, rsp_valid, rsp_err;
    wire [31:0] rsp_data;
    reg mem_ready=0, mem_valid=0, mem_err=0;
    reg [31:0] mem_data;
    wire mem_cmd, mem_read, mem_accept;
    wire [31:0] mem_addr;
    qingyu_fio dut(.clk(clk),.rst_n(rst_n),
        .icb_cmd_valid(cmd_valid),.icb_cmd_ready(cmd_ready),.icb_cmd_read(cmd_read),
        .icb_cmd_addr(cmd_addr),.icb_cmd_wdata(payload),.icb_cmd_wmask(cmd_mask),
        .icb_rsp_valid(rsp_valid),.icb_rsp_ready(rsp_ready),.icb_rsp_err(rsp_err),.icb_rsp_rdata(rsp_data),
        .cpu_cmd_valid(1'b0),.cpu_cmd_read(1'b0),.cpu_cmd_addr(32'b0),.cpu_cmd_wdata(32'b0),
        .cpu_cmd_wmask(4'b0),.cpu_rsp_ready(1'b1),.mem_cmd_valid(mem_cmd),.mem_cmd_ready(mem_ready),
        .mem_cmd_addr(mem_addr),.mem_cmd_read(mem_read),.mem_rsp_valid(mem_valid),
        .mem_rsp_ready(mem_accept),.mem_rsp_err(mem_err),.mem_rsp_rdata(mem_data));

    task automatic issue(input [31:0] a, input [31:0] p, input bit rd=0, input [3:0] mask=15);
        @(negedge clk); cmd_valid=1; cmd_addr=a; payload=p; cmd_read=rd; cmd_mask=mask;
        #1; while (!cmd_ready) @(negedge clk);
        @(negedge clk); cmd_valid=0;
    endtask
    task automatic reply(input bit error, input [31:0] expected=0, input bit check_data=0);
        wait(rsp_valid);
        repeat(2) begin
            @(negedge clk);
            if (!rsp_valid || rsp_err!==error || (check_data && rsp_data!==expected))
                $fatal(1,"FIO response err=%h data=%h expected=%h",rsp_err,rsp_data,expected);
        end
        rsp_ready=1; @(negedge clk); rsp_ready=0;
    endtask
    task automatic read_beat(input [31:0] a, input [31:0] w, input bit error=0);
        wait(mem_cmd);
        repeat(2) begin
            @(negedge clk);
            if (!mem_cmd || !mem_read || mem_addr!==a || rsp_valid) $fatal(1,"read addr=%h expected=%h",mem_addr,a);
        end
        mem_ready=1; @(negedge clk); mem_ready=0;
        repeat(2) @(negedge clk);
        mem_valid=1; mem_err=error; mem_data=w; #1;
        if (!mem_accept || dut.weight_write!==!error) $fatal(1,"bad read response handling");
        @(negedge clk); mem_valid=0; mem_err=0;
    endtask
    integer n;
    initial begin
        repeat(3) @(negedge clk); rst_n=1;
        issue('hf0000801,'ha0004000); reply(1);
        issue('hf0000800,'ha0004004); reply(1);
        issue('hf0000800,'ha003fe00); reply(1);
        issue('hf0000800,'ha0004000,1); reply(1);
        issue('hf0000800,'ha0004000,0,4'b0011); reply(1);
        // K=62/63 at the maximum admissible source, validate through the public MMIO readback.
        issue('hf000087c,'ha003fde0);
        for (n=0;n<16;n=n+1)
            read_beat('ha003fde0 + 512*(n/8) + 4*(n%8),32'hffff0011 + n*32'hff01);
        reply(0);
        for (n=0;n<16;n=n+1) begin
            issue('hf0005000 + 62*32 + n*4,0,1);
            reply(0,32'hffff0011 + n*32'hff01,1);
        end
        // Abort only the failed and subsequent writes. Retrying the same command
        // reconstructs the full pair. A different K pair must stay unchanged.
        issue('hf000087c,'ha0004000);
        read_beat('ha0004000,32'h0011bbcc); read_beat('ha0004004,32'h99990000,1);
        reply(1);
        issue('hf00057c4,0,1); reply(0,32'hffff0011 + 32'hff01,1);
        issue('hf0000800,'ha0004000);
        for (n=0;n<16;n=n+1)
            read_beat('ha0004000 + 512*(n/8) + (n%8)*4,32'hfe1e0000+n);
        reply(0);
        issue('hf0005000,0,1); reply(0,32'hfe1e0000,1);
        issue('hf00057c0,0,1); reply(0,32'h0011bbcc,1);
        issue('hf0000800,'ha0004000);
        read_beat('ha0004000,32'h0101abcd);
        rst_n=0; @(negedge clk); rst_n=1; #1;
        if (mem_cmd || rsp_valid || dut.weight_write) $fatal(1,"stale transaction after reset");
        issue('hf0000004,1); reply(0);
        issue('hf0000800,'ha0004000); reply(1);
        $display("PASS CPU weight gather: two-row stride, bank readback, response stalls, read error, invalid range/mask, reset, busy");
        $finish;
    end
    initial begin #30000; $fatal(1,"weight gather timeout"); end
endmodule
