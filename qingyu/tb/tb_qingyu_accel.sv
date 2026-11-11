`timescale 1ns/1ps
module tb_qingyu_accel;
    parameter integer ROWS=99, K=64, LANES=4;
    localparam integer TILES=256/LANES;
    reg clk=0, rst_n=0;
    always #5 clk=~clk;
    reg cmd_valid=0, cmd_read=0;
    reg [15:0] cmd_addr=0;
    reg [31:0] cmd_wdata=0;
    reg [3:0] cmd_wmask=4'hf;
    wire cmd_ready, rsp_valid, rsp_err;
    wire [31:0] rsp_rdata;
    reg rsp_ready=1;
    integer checks=0, output_checks=0;
    qingyu_accel #(.ROWS(ROWS),.K(K),.LANES(LANES)) dut (
        .clk(clk),.rst_n(rst_n),.icb_cmd_valid(cmd_valid),.icb_cmd_ready(cmd_ready),
        .icb_cmd_read(cmd_read),.icb_cmd_addr(cmd_addr),.icb_cmd_wdata(cmd_wdata),
        .icb_cmd_wmask(cmd_wmask),.icb_rsp_valid(rsp_valid),.icb_rsp_ready(rsp_ready),
        .icb_rsp_rdata(rsp_rdata),.icb_rsp_err(rsp_err));

    task automatic access;
        input is_read;
        input [15:0] address;
        input [31:0] value;
        input [3:0] mask;
        output reg [31:0] result;
        output reg failed;
        integer ticks;
        begin
            @(negedge clk);
            cmd_valid=1; cmd_read=is_read; cmd_addr=address;
            cmd_wdata=value; cmd_wmask=mask;
            ticks=0;
            @(posedge clk);
            while (!cmd_ready) begin
                ticks=ticks+1;
                if(ticks>1000) $fatal(1,"ICB command timeout addr=%h",address);
                @(posedge clk);
            end
            @(negedge clk); cmd_valid=0;
            ticks=0;
            while(!rsp_valid) begin
                ticks=ticks+1;
                if(ticks>1000) $fatal(1,"ICB response timeout addr=%h",address);
                @(negedge clk);
            end
            result=rsp_rdata; failed=rsp_err;
            @(posedge clk);
        end
    endtask
    task automatic wr;
        input [15:0] address;
        input [31:0] value;
        reg [31:0] result;
        reg failed;
        begin
            access(0,address,value,4'hf,result,failed);
            if(failed) $fatal(1,"Unexpected write error addr=%h value=%h",address,value);
            checks=checks+1;
        end
    endtask
    task automatic rd;
        input [15:0] address;
        output reg [31:0] result;
        reg failed;
        begin
            access(1,address,0,4'hf,result,failed);
            if(failed) $fatal(1,"Unexpected read error addr=%h",address);
            checks=checks+1;
        end
    endtask
    task automatic expect_error;
        input is_read;
        input [15:0] address;
        input [31:0] value;
        input [3:0] mask;
        reg [31:0] result;
        reg failed;
        begin
            access(is_read,address,value,mask,result,failed);
            if(!failed) $fatal(1,"Expected bus error addr=%h",address);
            checks=checks+1;
        end
    endtask
    task automatic wait_complete;
        input expect_failure;
        reg [31:0] status;
        integer tries;
        begin
            status=1; tries=0;
            while(status[0]) begin
                rd(16'h0008,status);
                tries=tries+1;
                if(tries>ROWS*K*4+1000) $fatal(1,"Engine completion timeout");
            end
            if(expect_failure) begin
                if(!status[2]) $fatal(1,"Expected engine error status=%h",status);
            end else if(status[2] || !status[1]) $fatal(1,"Engine failed status=%h",status);
        end
    endtask

    function automatic [31:0] reference_round;
        input signed [63:0] value;
        input integer amount;
        reg [63:0] mag, div, remn, half;
        reg signed [63:0] rounded;
        begin
            mag=value<0 ? -value:value;
            div=mag>>amount;
            if(amount>0) begin
                remn=mag-((mag>>amount)<<amount);
                half=64'd1<<(amount-1);
                if(remn>half || (remn==half && div[0])) div=div+1;
            end
            rounded=value<0 ? -$signed(div):$signed(div);
            if(rounded>64'sd2147483647) reference_round=32'h7fffffff;
            else if(rounded< -64'sd2147483648) reference_round=32'h80000000;
            else reference_round=rounded[31:0];
        end
    endfunction

    integer x [0:ROWS*K-1];
    integer w [0:K*LANES-1];
    reg signed [63:0] b [0:LANES-1];
    integer sh [0:LANES-1];
    reg [31:0] expected [0:ROWS*LANES-1];
    task automatic load_directed;
        integer i,t,p,k;
        reg [31:0] packed_word;
        reg [63:0] metadata;
        reg signed [63:0] sum;
        begin
            for(i=0;i<ROWS*K;i=i+2) begin
                packed_word=(x[i]&32'hffff)|((x[i+1]&32'hffff)<<16);
                wr(16'h1000+i*2,packed_word);
            end
            for(i=0;i<K*LANES;i=i+2) begin
                packed_word=(w[i]&32'hffff)|((w[i+1]&32'hffff)<<16);
                wr(16'h5000+i*2,packed_word);
            end
            for(p=0;p<LANES;p=p+1) begin
                metadata={8'b0,8'(sh[p]),b[p][47:0]};
                wr(16'h6000+p*8,metadata[31:0]);
                wr(16'h6004+p*8,metadata[63:32]);
            end
            for(t=0;t<ROWS;t=t+1) for(p=0;p<LANES;p=p+1) begin
                sum=b[p];
                for(k=0;k<K;k=k+1) sum=sum+x[t*K+k]*w[k*LANES+p];
                expected[t*LANES+p]=reference_round(sum,sh[p]);
            end
        end
    endtask
    task automatic compare_directed;
        integer i;
        reg [31:0] value;
        begin
            rd(16'h001c,value);
            if(value!=ROWS*LANES) $fatal(1,"Wrong output count %d",value);
            for(i=0;i<ROWS*LANES;i=i+1) begin
                rd(16'h7000+i*4,value);
                if(value!==expected[i])
                    $fatal(1,"Output %d got=%h expected=%h",i,value,expected[i]);
                output_checks=output_checks+1;
            end
        end
    endtask

    reg [31:0] xv [0:ROWS*K/2-1];
    reg [31:0] wv [0:TILES*K*LANES/2-1];
    reg [31:0] mv [0:256*2-1];
    reg [31:0] yv [0:ROWS*256-1];
    string vector_dir;
    task automatic external_vectors;
        integer tile,i;
        reg [31:0] value;
        begin
            $readmemh({vector_dir,"/x_words.hex"},xv);
            $readmemh({vector_dir,"/w_tile_words.hex"},wv);
            $readmemh({vector_dir,"/meta_words.hex"},mv);
            $readmemh({vector_dir,"/y_tile_words.hex"},yv);
            wr(16'h0004,4);
            for(i=0;i<ROWS*K/2;i=i+1) wr(16'h1000+i*4,xv[i]);
            for(tile=0;tile<TILES;tile=tile+1) begin
                wr(16'h0010,tile*LANES);
                for(i=0;i<K*LANES/2;i=i+1)
                    wr(16'h5000+i*4,wv[tile*K*LANES/2+i]);
                for(i=0;i<LANES*2;i=i+1) wr(16'h6000+i*4,mv[tile*LANES*2+i]);
                wr(16'h0004,3);
                wait_complete(0);
                for(i=0;i<ROWS*LANES;i=i+1) begin
                    rd(16'h7000+i*4,value);
                    if(value!==yv[tile*ROWS*LANES+i])
                        $fatal(1,"Vector mismatch tile=%d index=%d got=%h expected=%h",tile,i,value,yv[tile*ROWS*LANES+i]);
                    output_checks=output_checks+1;
                end
            end
            $display("PASS external full matrix %s: %0d outputs",vector_dir,ROWS*256);
        end
    endtask

    integer i,p;
    reg [31:0] value, held_value;
    reg failed;
    initial begin
        if($test$plusargs("VCD")) begin $dumpfile("reports/qingyu_accel.vcd"); $dumpvars(0,tb_qingyu_accel); end
        repeat(4) @(posedge clk);
        @(negedge clk); rst_n=1;
        rd(0,value); if(value!==32'h51590001) $fatal(1,"ID mismatch");
        // Response backpressure: response and ready must stay stable.
        @(negedge clk); rsp_ready=0;
        access(1,0,0,4'hf,held_value,failed);
        repeat(6) begin
            @(negedge clk);
            if(!rsp_valid || rsp_rdata!==held_value || rsp_err || cmd_ready)
                $fatal(1,"Response changed under backpressure");
        end
        rsp_ready=1; @(posedge clk); @(negedge clk);
        checks=checks+1;
        expect_error(1,16'h1001,0,4'hf);
        expect_error(0,16'h1000,0,4'h3);
        expect_error(1,16'h8000,0,4'hf);
        expect_error(0,16'h0010,3,4'hf);
        wr(16'h0004,2);
        // Signed products, arbitrary nonzero biases, multiple output shifts.
        for(i=0;i<ROWS*K;i=i+1) x[i]=(i%19)-9;
        for(i=0;i<K*LANES;i=i+1) w[i]=(i*5%23)-11;
        for(p=0;p<LANES;p=p+1) begin b[p]=p*83-101; sh[p]=p*2; end
        load_directed();
        // Memory readback also checks little-endian packed input layout.
        rd(16'h1000,value);
        if(value!==((x[0]&32'hffff)|((x[1]&32'hffff)<<16))) $fatal(1,"Input readback mismatch");
        wr(16'h0004,3);
        expect_error(1,16'h1000,0,4'hf);
        expect_error(0,16'h0004,1,4'hf);
        wait_complete(1); wr(16'h0004,2);
        // CLEAR_DONE clears DONE too; result SRAM remains available.
        for(i=0;i<ROWS*LANES;i=i+1) begin
            rd(16'h7000+i*4,value);
            if(value!==expected[i]) $fatal(1,"Busy-error disturbed compute at %0d",i);
            output_checks=output_checks+1;
        end
        wr(16'h0004,3); wait_complete(0); compare_directed();
        // Exact ties to even, including negative ties.
        for(i=0;i<ROWS*K;i=i+1) x[i]=0;
        for(i=0;i<K*LANES;i=i+1) w[i]=0;
        for(p=0;p<LANES;p=p+1) begin
            case(p%4) 0:b[p]=5; 1:b[p]=7; 2:b[p]=-5; 3:b[p]=-7; endcase
            sh[p]=1;
        end
        load_directed(); wr(16'h0004,3); wait_complete(0); compare_directed();
        // Dot products exceeding int32 saturate both signs.
        for(i=0;i<ROWS*K;i=i+1) x[i]=32767;
        for(i=0;i<K*LANES;i=i+1) w[i]=(i%2) ? -32767:32767;
        for(p=0;p<LANES;p=p+1) begin b[p]=0; sh[p]=0; end
        load_directed(); wr(16'h0004,3); wait_complete(0); compare_directed();
        // Invalid metadata must report an error, not silently execute.
        wr(16'h6004,32'h00300000); // shift 48
        wr(16'h0004,3); wait_complete(1);
        rd(16'h0014,value); if(value!=7) $fatal(1,"Wrong metadata error code");
        // Positive 48-bit overflow.
        for(i=0;i<ROWS*K;i=i+1) x[i]=1;
        for(i=0;i<K*LANES;i=i+1) w[i]=1;
        for(p=0;p<LANES;p=p+1) begin b[p]=64'sh00007fffffffffff; sh[p]=0; end
        load_directed(); wr(16'h0004,3); wait_complete(1);
        rd(16'h0014,value); if(value!=6) $fatal(1,"Wrong overflow error code");
        // Negative 48-bit overflow.
        for(i=0;i<ROWS*K;i=i+1) x[i]=-1;
        for(p=0;p<LANES;p=p+1) b[p]=-64'sh0000800000000000;
        load_directed(); wr(16'h0004,3); wait_complete(1);
        // Abort an active operation with synchronous software reset.
        for(p=0;p<LANES;p=p+1) b[p]=0;
        load_directed(); wr(16'h0004,3);
        repeat(8) @(posedge clk);
        wr(16'h0004,4); rd(16'h0008,value);
        if(value!=0) $fatal(1,"Soft reset did not abort task");
        // Reload and complete after reset, proving recovery.
        load_directed(); wr(16'h0004,3); wait_complete(0); compare_directed();
        if($value$plusargs("VECTORS=%s",vector_dir)) external_vectors();
        $display("PASS qingyu_accel directed tests: %0d bus checks, %0d output checks",checks,output_checks);
        $finish;
    end
    initial begin #500000000; $fatal(1,"Global simulation timeout"); end
endmodule

