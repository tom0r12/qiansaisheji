`timescale 1ns/1ps
`default_nettype none
// CPU-published source-prefix guard. This block never accesses shared memory.
// A commit means the producer has received all write responses through that
// prefix. CPU software must obtain that fact through actual platform traffic.
module q11_commit_gate #(
    parameter [31:0] SHARED_FIRST = 32'ha0000000,
    parameter [31:0] SHARED_LIMIT = 32'ha0080000
) (
    input wire clk, rst_n,
    input wire start_valid, output wire start_ready,
    input wire [31:0] start_source_base, start_total_words,
    input wire [31:0] start_available_words, start_epoch,
    input wire commit_valid, output wire commit_ready,
    input wire [31:0] commit_available_words, commit_epoch,
    // Caller may close only AFTER all accepted bus work has drained. The gate
    // can observe its descriptor register, not downstream bus responses.
    input wire close_valid, output wire close_ready,
    output reg active,
    output reg [31:0] source_base, total_words, available_words, epoch,
    output reg control_error, output reg [3:0] control_error_code,
    output reg descriptor_error,
    input wire s_valid, output wire s_ready,
    input wire [31:0] s_addr, s_words,
    output wire m_valid, input wire m_ready,
    output wire [31:0] m_addr, m_words
);
    reg offer_valid;
    reg [31:0] offer_addr, offer_words;
    reg epoch_seen;
    reg [31:0] last_epoch;
    wire [34:0] start_end = {3'b0,start_source_base}+{1'b0,start_total_words,2'b0};
    wire [34:0] source_end = {3'b0,source_base}+{1'b0,total_words,2'b0};
    wire [34:0] available_end = {3'b0,source_base}+{1'b0,available_words,2'b0};
    wire [34:0] descriptor_end = {3'b0,s_addr}+{1'b0,s_words,2'b0};
    wire config_range_ok = start_source_base[1:0]==0 && start_total_words!=0 &&
        start_source_base>=SHARED_FIRST && start_end<={3'b0,SHARED_LIMIT} &&
        start_available_words<=start_total_words;
    wire descriptor_range_ok = s_addr[1:0]==0 && s_words!=0 &&
        s_addr>=source_base && descriptor_end<=source_end;
    wire descriptor_committed = descriptor_end<=available_end;
    assign start_ready = rst_n && !active && !offer_valid;
    assign commit_ready = rst_n && active && !close_valid;
    assign close_ready = rst_n && active && !offer_valid;
    assign m_valid = rst_n && offer_valid;
    assign m_addr = offer_addr;
    assign m_words = offer_words;
    assign s_ready = rst_n && active && !close_valid && !descriptor_error &&
        (!offer_valid || m_ready) && descriptor_range_ok && descriptor_committed;
    wire start_fire = start_valid && start_ready;
    wire commit_fire = commit_valid && commit_ready;
    wire close_fire = close_valid && close_ready;
    wire s_fire = s_valid && s_ready;
    wire m_fire = m_valid && m_ready;
    always @(posedge clk) begin
        if(!rst_n) begin
            active<=0;source_base<=0;total_words<=0;available_words<=0;epoch<=0;
            control_error<=0;control_error_code<=0;descriptor_error<=0;
            offer_valid<=0;offer_addr<=0;offer_words<=0;epoch_seen<=0;last_epoch<=0;
        end else begin
            control_error<=0;
            if(m_fire)offer_valid<=0;
            if(s_fire)begin offer_valid<=1;offer_addr<=s_addr;offer_words<=s_words;end
            if(active && !close_valid && s_valid && !descriptor_range_ok)
                descriptor_error<=1;
            if(close_fire)begin active<=0;descriptor_error<=0;end
            if(start_fire)begin
                if(!config_range_ok)begin control_error<=1;control_error_code<=1;end
                else if(epoch_seen && start_epoch<=last_epoch)begin control_error<=1;control_error_code<=2;end
                else begin
                    active<=1;source_base<=start_source_base;total_words<=start_total_words;
                    available_words<=start_available_words;epoch<=start_epoch;
                    last_epoch<=start_epoch;epoch_seen<=1;descriptor_error<=0;control_error_code<=0;
                end
            end
            if(commit_fire)begin
                if(commit_epoch!=epoch)begin control_error<=1;control_error_code<=3;end
                else if(commit_available_words<available_words)begin control_error<=1;control_error_code<=4;end
                else if(commit_available_words>total_words)begin control_error<=1;control_error_code<=5;end
                else available_words<=commit_available_words;
            end
        end
    end
endmodule
`default_nettype wire
