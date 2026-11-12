`timescale 1ns/1ps
`default_nettype none
module tb_private_x_compact;
    reg clk=0;
    always #5 clk=~clk;
    reg en=0,we=0;
    reg [9:0] addr=0;
    reg [15:0] wdata=0;
    wire [15:0] q352,q416,q128;
    qingyu_sram16 #(.DEPTH(1024),.ADDR_W(10),.X_VALID_WORDS(352)) d352(.clk,.en,.we,.addr,.wdata,.rdata(q352));
    qingyu_sram16 #(.DEPTH(1024),.ADDR_W(10),.X_VALID_WORDS(416)) d416(.clk,.en,.we,.addr,.wdata,.rdata(q416));
    qingyu_sram16 #(.DEPTH(128),.ADDR_W(7)) d128(.clk,.en,.we,.addr(addr[6:0]),.wdata,.rdata(q128));
    reg [15:0] ref352[0:351],ref416[0:415],ref128[0:127];
    reg [15:0] expected352,expected416,expected128;
    integer checks=0,illegal352=0,illegal416=0,seed=2371,junk;
    integer page_reads352[0:2],page_reads416[0:3];
    integer page_writes352[0:2],page_writes416[0:3];
    task automatic access(input bit enabled,input bit writing,input integer address,input [15:0] data);
        begin
            @(negedge clk);en=enabled;we=writing;addr=10'(address);wdata=data;
            @(posedge clk);
            if(enabled) begin
                if(address<352)begin
                    if(writing)begin ref352[address]=data;expected352=16'hxxxx;end
                    else expected352=ref352[address];
                end else begin expected352=0;illegal352++;end
                if(address<416)begin
                    if(writing)begin ref416[address]=data;expected416=16'hxxxx;end
                    else expected416=ref416[address];
                end else begin expected416=0;illegal416++;end
                if(writing)begin ref128[address%128]=data;expected128=16'hxxxx;end
                else expected128=ref128[address%128];
            end
            #2;
            if(q352!==expected352||q416!==expected416||q128!==expected128)
                $fatal(1,"compact memory mismatch addr=%0d en=%0b we=%0b q352=%h/%h q416=%h/%h q128=%h/%h",address,enabled,writing,q352,expected352,q416,expected416,q128,expected128);
            checks++;
        end
    endtask
    // Inspect the actual macro enables, not an assumed bit-capacity reduction.
    generate
        for(genvar p=0;p<3;p=p+1)begin: m352
            always @(posedge clk)begin
                if(d352.g_compact.pages[p].macro_ram.CEN !== !(en&&addr<352&&addr[9:7]==p))
                    $fatal(1,"352 macro enable/alias page%0d",p);
                if(!d352.g_compact.pages[p].macro_ram.CEN)begin
                    if(we)page_writes352[p]++;else page_reads352[p]++;
                end
            end
        end
        for(genvar p=0;p<4;p=p+1)begin: m416
            always @(posedge clk)begin
                if(d416.g_compact.pages[p].macro_ram.CEN !== !(en&&addr<416&&addr[9:7]==p))
                    $fatal(1,"416 macro enable/alias page%0d",p);
                if(!d416.g_compact.pages[p].macro_ram.CEN)begin
                    if(we)page_writes416[p]++;else page_reads416[p]++;
                end
            end
        end
    endgenerate
    initial begin
        if($value$plusargs("SEED=%d",seed))begin end
        junk=$urandom(seed);
        for(integer p=0;p<3;p++)begin page_reads352[p]=0;page_writes352[p]=0;end
        for(integer p=0;p<4;p++)begin page_reads416[p]=0;page_writes416[p]=0;end
        // Before first operation Q is deliberately not constrained.
        for(integer a=0;a<416;a++) access(1,1,a,16'(a*37+11));
        for(integer a=0;a<416;a++) access(1,0,a,0);
        // Probe every unused address, then prove valid memory did not alias.
        for(integer a=416;a<1024;a++)begin access(1,1,a,16'hdead);access(1,0,a,0);end
        for(integer a=0;a<416;a++)access(1,0,a,0);
        for(integer n=0;n<2500;n++)access($urandom%5!=0,$urandom%2!=0,int'($urandom%1024),16'($urandom));
        for(integer a=415;a>=0;a--)access(1,0,a,0);
        for(integer p=0;p<3;p++)if(!page_reads352[p]||!page_writes352[p])$fatal(1,"352 missed page%0d",p);
        for(integer p=0;p<4;p++)if(!page_reads416[p]||!page_writes416[p])$fatal(1,"416 missed page%0d",p);
        $display("PASS private_x_compact checks=%0d illegal352=%0d illegal416=%0d",checks,illegal352,illegal416);
        $finish;
    end
endmodule
`default_nettype wire
