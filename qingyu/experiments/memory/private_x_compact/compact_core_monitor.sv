`timescale 1ns/1ps
`default_nettype none
// Verification-only top; observes the frozen TB without editing/binding its RTL.
module compact_core_monitor;
    localparam integer ROWS=`QINGYU_X_ROWS;
    localparam integer WORDS=`QINGYU_X_VALID_WORDS;
    localparam integer PAGES=(WORDS+127)/128;
    integer logical_reads=0,logical_writes=0;
    generate
        for(genvar r=0;r<ROWS;r=r+1)begin: row
            always @(posedge tb_winograd_task8.clk) begin
                if(tb_winograd_task8.dut.x_en[r])begin
                    if(tb_winograd_task8.dut.x_addr[r]>=WORDS)
                        $fatal(1,"Core X out of compact range row=%0d addr=%0d",r,tb_winograd_task8.dut.x_addr[r]);
                    if(tb_winograd_task8.dut.x_we[r])logical_writes++;
                    else logical_reads++;
                end
            end
            for(genvar p=0;p<PAGES;p=p+1)begin: page
                always @(posedge tb_winograd_task8.clk)begin
                    if(tb_winograd_task8.dut.x_bank[r].memory.g_compact.pages[p].macro_ram.CEN !==
                       !(tb_winograd_task8.dut.x_en[r] && tb_winograd_task8.dut.x_addr[r]<WORDS &&
                         tb_winograd_task8.dut.x_addr[r][9:7]==3'(p)))
                        $fatal(1,"Core macro access mismatch row=%0d page=%0d",r,p);
                end
            end
        end
    endgenerate
    final begin
        $display("COMPACT_CORE rows=%0d pages=%0d logical_reads=%0d logical_writes=%0d",ROWS,PAGES,logical_reads,logical_writes);
    end
endmodule
`default_nettype wire
