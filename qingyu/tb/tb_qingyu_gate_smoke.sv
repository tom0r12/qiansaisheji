`timescale 1ns/1ps
// Bounded synthesis-before/after functional check, not a timing/signoff test.
module tb_qingyu_gate_smoke;
    reg clk=0, rst_n=0;
    always #1000 clk=~clk; // intentionally slow 2000ns; no timing inference
    reg cmd_valid=0, cmd_read=0;
    reg [15:0] cmd_addr=0;
    reg [31:0] cmd_wdata=0;
    reg [3:0] cmd_wmask=4'hf;
    reg rsp_ready=1;
    wire r_ready, g_ready, r_valid, g_valid, r_error, g_error;
    wire [31:0] r_data,g_data;
    integer bus_checks=0, output_checks=0, comparison_cycles=0;
    integer trace_cycles=0;
    qingyu_accel_ref reference_dut(
        .clk(clk),.rst_n(rst_n),.icb_cmd_valid(cmd_valid),.icb_cmd_ready(r_ready),
        .icb_cmd_read(cmd_read),.icb_cmd_addr(cmd_addr),.icb_cmd_wdata(cmd_wdata),
        .icb_cmd_wmask(cmd_wmask),.icb_rsp_valid(r_valid),.icb_rsp_ready(rsp_ready),
        .icb_rsp_rdata(r_data),.icb_rsp_err(r_error));
    qingyu_accel mapped_dut(
        .clk(clk),.rst_n(rst_n),.icb_cmd_valid(cmd_valid),.icb_cmd_ready(g_ready),
        .icb_cmd_read(cmd_read),.icb_cmd_addr(cmd_addr),.icb_cmd_wdata(cmd_wdata),
        .icb_cmd_wmask(cmd_wmask),.icb_rsp_valid(g_valid),.icb_rsp_ready(rsp_ready),
        .icb_rsp_rdata(g_data),.icb_rsp_err(g_error));

    // Check every cycle at a settled phase, including stalled responses.
    always @(negedge clk) begin
        #100;
        if(rst_n) begin
            if(reference_dut.busy && trace_cycles<50) begin
                $display("TRACE t=%t re=%h ge=%h rma=%h gma=%h rmen=%b gmen=%b rmd=%h gmd=%h rb0=%h gb0=%h",$time,reference_dut.engine_state,mapped_dut.engine_state,reference_dut.m_addr,mapped_dut.m_addr,reference_dut.m_en,mapped_dut.m_en,reference_dut.m_rdata,mapped_dut.m_rdata,reference_dut.bias[0],mapped_dut.\bias[0] );
                trace_cycles=trace_cycles+1;
            end
            comparison_cycles=comparison_cycles+1;
            if(r_ready!==g_ready || r_valid!==g_valid)
                $fatal(1,"RTL/mapped handshake mismatch t=%t ready=%b/%b valid=%b/%b",$time,r_ready,g_ready,r_valid,g_valid);
            if(r_valid && (r_data!==g_data || r_error!==g_error)) begin
                $display("DEBUG rbusy=%b gbusy=%b restate=%h gestate=%h rmeta=%0d/%0d gmeta=%0d/%0d rmd=%h gmd=%h",reference_dut.busy,mapped_dut.busy,reference_dut.engine_state,mapped_dut.engine_state,reference_dut.meta_lane,reference_dut.meta_segment,mapped_dut.meta_lane,mapped_dut.meta_segment,reference_dut.m_rdata,mapped_dut.m_rdata);
                $display("DEBUG rx=%h gx=%h rw0=%h gw0=%h racc0=%h gacc0=%h",reference_dut.x_rdata[0],mapped_dut.\x_rdata[0] ,reference_dut.w_rdata[0],mapped_dut.\w_rdata[0] ,reference_dut.acc[0],mapped_dut.\acc[0] );
                $fatal(1,"RTL/mapped response mismatch t=%t data=%h/%h error=%b/%b",$time,r_data,g_data,r_error,g_error);
            end
        end
    end

    task automatic transfer;
        input is_read;
        input [15:0] address;
        input [31:0] value;
        input [3:0] mask;
        input expected_error;
        output reg [31:0] result;
        integer ticks;
        begin
            @(negedge clk); #2;
            cmd_valid=1; cmd_read=is_read; cmd_addr=address; cmd_wdata=value; cmd_wmask=mask;
            ticks=0;
            @(posedge clk);
            while(!(r_ready&&g_ready)) begin
                ticks=ticks+1; if(ticks>100) $fatal(1,"Request timeout");
                @(posedge clk);
            end
            @(negedge clk); #2; cmd_valid=0;
            ticks=0;
            while(!(r_valid&&g_valid)) begin
                ticks=ticks+1; if(ticks>100) $fatal(1,"Response timeout");
                @(negedge clk); #2;
            end
            if(r_data!==g_data || r_error!==g_error || r_error!==expected_error)
                $fatal(1,"Transaction mismatch address=%h",address);
            result=r_data;
            bus_checks=bus_checks+1;
            @(posedge clk);
        end
    endtask
    task automatic wr;
        input [15:0] address;
        input [31:0] value;
        reg [31:0] ignored;
        begin transfer(0,address,value,4'hf,0,ignored); end
    endtask
    task automatic rd;
        input [15:0] address;
        output reg [31:0] result;
        begin transfer(1,address,0,4'hf,0,result); end
    endtask
    function automatic integer x_value;
        input integer row;
        begin x_value=(row==0) ? 0:((row%2) ? -2:3); end
    endfunction
    function automatic integer w_value;
        input integer lane;
        begin case(lane) 0:w_value=1; 1:w_value=-2; 2:w_value=3; default:w_value=-4; endcase end
    endfunction
    function automatic signed [63:0] bias_value;
        input integer lane;
        begin case(lane) 0:bias_value=-5; 1:bias_value=7; 2:bias_value=64'sd2147483649; default:bias_value=-64'sd2147483650; endcase end
    endfunction
    function automatic [31:0] expected_result;
        input integer row,lane;
        reg signed [63:0] value, rounded;
        reg [63:0] magnitude, quotient;
        integer amount;
        begin
            value=bias_value(lane)+64*x_value(row)*w_value(lane);
            amount=(lane<2) ? 1:0;
            magnitude=value<0 ? -value:value;
            quotient=magnitude>>amount;
            if(amount!=0 && magnitude[0] && quotient[0]) quotient=quotient+1;
            rounded=value<0 ? -$signed(quotient):$signed(quotient);
            if(rounded>64'sd2147483647) expected_result=32'h7fffffff;
            else if(rounded< -64'sd2147483648) expected_result=32'h80000000;
            else expected_result=rounded[31:0];
        end
    endfunction
    integer row,k,lane,index,polls;
    reg [31:0] value,word_value;
    reg [63:0] metadata;
    reg signed [63:0] bias_bits;
    initial begin
        repeat(8) @(posedge clk);
        @(negedge clk); #2; rst_n=1;
        rd(0,value); if(value!==32'h51590001) $fatal(1,"ID mismatch");
        // Both DUTs must preserve a response under host backpressure.
        @(negedge clk); #2; rsp_ready=0;
        rd(0,value);
        repeat(3) @(posedge clk);
        @(negedge clk); #2; rsp_ready=1;
        @(posedge clk);
        transfer(1,16'h1001,0,4'hf,1,value);
        wr(4,2);
        for(row=0;row<99;row=row+1) begin
            word_value=(x_value(row)&32'hffff)|((x_value(row)&32'hffff)<<16);
            for(k=0;k<64;k=k+2) wr(16'h1000+(row*64+k)*2,word_value);
        end
        rd(16'h417c,value); // final input packed word (crosses second SRAM bank)
        if(value!==32'h00030003) $fatal(1,"Input bank readback mismatch");
        for(k=0;k<64;k=k+1) for(lane=0;lane<4;lane=lane+2) begin
            word_value=(w_value(lane)&32'hffff)|((w_value(lane+1)&32'hffff)<<16);
            wr(16'h5000+(k*4+lane)*2,word_value);
        end
        for(lane=0;lane<4;lane=lane+1) begin
            bias_bits=bias_value(lane);
            metadata={8'b0,8'((lane<2)?1:0),bias_bits[47:0]};
            wr(16'h6000+lane*8,metadata[31:0]);
            wr(16'h6004+lane*8,metadata[63:32]);
        end
        // Explicitly read initialized input/weight data before starting. This
        // gives synchronous SRAM outputs known values in four-state simulation.
        rd(16'h1000,value); if(value!==0) $fatal(1,"Input zero-row readback mismatch");
        rd(16'h5000,value); if(value!==32'hfffe0001) $fatal(1,"Weight lanes01 readback mismatch");
        rd(16'h5004,value); if(value!==32'hfffc0003) $fatal(1,"Weight lanes23 readback mismatch");
        wr(4,3);
        value=1; polls=0;
        while(value[0]) begin
            rd(8,value); polls=polls+1;
            if(polls>10000) $fatal(1,"Completion timeout");
        end
        if(value!==2) $fatal(1,"Unexpected status %h",value);
        rd(16'h1c,value); if(value!=396) $fatal(1,"Output count mismatch");
        for(row=0;row<99;row=row+1) for(lane=0;lane<4;lane=lane+1) begin
            index=row*4+lane;
            rd(16'h7000+index*4,value);
            if(value!==expected_result(row,lane))
                $fatal(1,"Numerical mismatch row=%0d lane=%0d value=%h expected=%h",row,lane,value,expected_result(row,lane));
            output_checks=output_checks+1;
        end
        $display("PASS mapped gate smoke: outputs=%0d bus_checks=%0d compared_cycles=%0d",output_checks,bus_checks,comparison_cycles);
        $finish;
    end
    initial begin #2000000000; $fatal(1,"Gate smoke simulation-time watchdog"); end
endmodule
