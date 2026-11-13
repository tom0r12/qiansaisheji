`timescale 1ns/1ps
`default_nettype none
module q13_rice_encoder #(
    parameter integer LANES = 4,
    parameter integer HISTORY_SYMBOLS = 16
) (
    input wire clk, rst_n,
    input wire start_valid, output wire start_ready,
    input wire [15:0] start_symbols,
    input wire [3:0] start_k,
    input wire start_delta,
    input wire [8:0] start_row_symbols,
    input wire in_valid, output wire in_ready,
    input wire [51:0] in_data,
    input wire [2:0] in_count,
    input wire in_last,
    output reg out_valid, input wire out_ready,
    output reg [31:0] out_data,
    output reg [5:0] out_valid_bits,
    output reg out_last,
    output reg busy, done, error,
    output reg [31:0] total_cycles, encoded_bits,
    output reg [9:0] output_words
);
    // Signed13 output tile codec: canonical Rice32 k7, optional delta16.
    // Four low-symbol-first symbols in; little-endian32bit bus words out.
    // Each tile has at most1584 symbols: at most20642 meaningful bits/646words.
    // Build the next group's canonical bits first. Admit it only when its
    // actual length fits the unchanged384bit reservoir after any head emit.
    // This preserves every wire bit while avoiding a worst-case fixed gate.
    // output_words counts accepted bus beats, including the final padded word.
    localparam integer HISTORY_ADDR_W = $clog2(HISTORY_SYMBOLS);
    reg [15:0] symbol_total_q, received_q;
    
    reg delta_q;
    reg [8:0] row_symbols_q;
    reg [12:0] history [0:HISTORY_SYMBOLS-1];
    reg [12:0] blocks [0:1][0:31];
    reg [1:0] ready_q, raw_q, last_q;
    reg [5:0] lengths [0:1];
    reg fill_q, encode_q;
    reg [5:0] fill_count_q, encode_pos_q;
    reg [11:0] rice_cost_q;
    reg input_ended_q, coding_complete_q;
    reg [383:0] reservoir_q;
    reg [8:0] reservoir_bits_q;
    reg [383:0] work_bits;
    // A canonical Rice block with n<=32 symbols has cost <=13*n-1.
    // Outside a g<=4-symbol group each code costs at least8 bits, hence
    // this group costs <=5*n+8*g-1 <=191, plus at most one block flag.
    // Raw groups cost <=4*13+1=53. No accepted group exceeds192 bits.
    reg [191:0] append_bits;
    reg [71:0] code_bits;
    reg [31:0] head_word;
    reg [12:0] symbol_value, transformed, unsigned_value;
    reg [8:0] work_count;
    reg [6:0] code_length;
    reg [5:0] emit_count;
    reg [2:0] group_count;
    reg [7:0] append_count;
    reg [HISTORY_ADDR_W-1:0] column;
    integer j;
    reg [11:0] sum_cost;
    reg [5:0] new_count, q;
    reg [6:0] remainder;
    reg [2:0] expected_count;
    reg bad_beat;

    assign start_ready = rst_n && !busy && !out_valid;
    assign in_ready = rst_n && busy && !input_ended_q && (error || !ready_q[fill_q]);

    function automatic [12:0] zigzag(input reg [12:0] symbol_in);
        integer signed value;
        begin
            value = symbol_in < 4096 ? int'(symbol_in) : int'(symbol_in)-8192;
            zigzag = 13'(value < 0 ? -2*value-1 : 2*value);
        end
    endfunction


    initial begin
        if(HISTORY_SYMBOLS!=16)$fatal(1,"fixed encoder requires HISTORY_SYMBOLS=16");
        if (LANES != 4) $fatal(1,"fixed encoder requires LANES=4");
    end
    // Blocking assignments below are local combinational workspaces; every
    // retained protocol/datapath register uses a nonblocking assignment.
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin
        if (!rst_n) begin
            busy<=0;done<=0;error<=0;out_valid<=0;out_data<=0;out_valid_bits<=0;out_last<=0;
            total_cycles<=0;encoded_bits<=0;output_words<=0;symbol_total_q<=0;received_q<=0;delta_q<=0;row_symbols_q<=0;
            ready_q<=0;raw_q<=0;last_q<=0;fill_q<=0;encode_q<=0;fill_count_q<=0;encode_pos_q<=0;rice_cost_q<=0;
            lengths[0]<=0;lengths[1]<=0;input_ended_q<=0;coding_complete_q<=0;reservoir_q<=0;reservoir_bits_q<=0;
        end else begin
            done<=0;
            if (out_valid && out_ready) begin
                output_words<=output_words+1;out_valid<=0;
                if (out_last && !error) begin busy<=0;done<=1;end
            end
            if (start_valid && start_ready) begin
                busy<=1;error<=start_symbols==0 || start_symbols>1584 || start_k!=7 || (start_delta && start_row_symbols!=16);
                total_cycles<=1;encoded_bits<=0;output_words<=0;symbol_total_q<=start_symbols;received_q<=0;
                delta_q<=start_delta;row_symbols_q<=start_row_symbols;
                ready_q<=0;raw_q<=0;last_q<=0;fill_q<=0;encode_q<=0;fill_count_q<=0;encode_pos_q<=0;rice_cost_q<=0;
                input_ended_q<=start_symbols==0 || start_symbols>1584 || start_k!=7 || (start_delta && start_row_symbols!=16);
                coding_complete_q<=0;reservoir_q<=0;reservoir_bits_q<=0;
            end else if (busy) begin
                total_cycles<=total_cycles+1;
                if (error) begin
                    ready_q<=0;reservoir_q<=0;reservoir_bits_q<=0;
                    if (in_valid && in_ready && in_last) input_ended_q<=1;
                    if ((input_ended_q || (in_valid && in_ready && in_last)) && (!out_valid || out_ready)) begin busy<=0;done<=1;end
                end else begin
                    bad_beat=0;
                    if (in_valid && in_ready) begin
                        expected_count = (int'(symbol_total_q)-int'(received_q)>LANES) ? LANES : int'(symbol_total_q)-int'(received_q);
                        bad_beat = int'(in_count)!=expected_count || in_count==0 ||
                                   in_last!=(int'(received_q)+int'(in_count)==int'(symbol_total_q));
                        if (bad_beat) begin error<=1;input_ended_q<=in_last;end
                        else begin
                            sum_cost=int'(rice_cost_q);
                            for(j=0;j<LANES;j=j+1) if(j<int'(in_count)) begin
                                symbol_value=in_data[j*13+:13];
                                column=HISTORY_ADDR_W'((int'(received_q)+j)&(int'(row_symbols_q)-1));
                                transformed=symbol_value;
                                if(delta_q) begin
                                    if(int'(received_q)+j>=int'(row_symbols_q)) transformed=symbol_value-history[column];
                                    history[column]<=symbol_value;
                                end
                                blocks[fill_q][int'(fill_count_q)+j]<=transformed;
                                unsigned_value=zigzag(transformed);
                                sum_cost=sum_cost+(int'(unsigned_value)>>7)+1+7;
                            end
                            new_count=int'(fill_count_q)+int'(in_count);
                            received_q<=received_q+16'(in_count);
                            if(new_count==32 || in_last) begin
                                ready_q[fill_q]<=1;raw_q[fill_q]<=sum_cost>=13*new_count;last_q[fill_q]<=in_last;
                                lengths[fill_q]<=6'(new_count);fill_q<=!fill_q;fill_count_q<=0;rice_cost_q<=0;
                            end else begin fill_count_q<=6'(new_count);rice_cost_q<=12'(sum_cost);end
                            if(in_last) input_ended_q<=1;
                        end
                    end
                    if(bad_beat) begin ready_q<=0;reservoir_q<=0;reservoir_bits_q<=0;end
                    else begin
                        work_bits=reservoir_q;work_count=int'(reservoir_bits_q);
                        if((!out_valid || out_ready) && (work_count>32 || (coding_complete_q && work_count>0))) begin
                            emit_count=work_count<32?work_count:32;
                            head_word=work_bits[383:352];
                            out_data<={head_word[7:0],head_word[15:8],head_word[23:16],head_word[31:24]};
                            out_valid_bits<=6'(emit_count);out_last<=coding_complete_q && work_count<=32;out_valid<=1;
                            // Fixed32-bit drain; a final partial word consumes all valid bits.
                            // The existing zero-padding reservoir invariant makes clear exact.
                            work_bits=work_count<32 ? 384'b0 : {work_bits[351:0],32'b0};
                            work_count=work_count-emit_count;
                        end
                        if(ready_q[encode_q]) begin
                            append_bits=0;append_count=0;
                            if(encode_pos_q==0) begin
                                append_bits[191]=raw_q[encode_q];append_count=1;
                            end
                            group_count=(int'(lengths[encode_q])-int'(encode_pos_q)>LANES) ? LANES : int'(lengths[encode_q])-int'(encode_pos_q);
                            for(j=0;j<LANES;j=j+1) if(j<group_count) begin
                                symbol_value=blocks[encode_q][int'(encode_pos_q)+j];code_bits=0;
                                if(raw_q[encode_q]) begin code_bits[71:59]=symbol_value;code_length=13;end
                                else begin
                                    unsigned_value=zigzag(symbol_value);q=int'(unsigned_value)>>7;
                                    remainder=int'(unsigned_value)&127;code_length=q+1+7;
                                    code_bits=(~72'b0 << (72-q)) | (72'(remainder) << (72-code_length));
                                end
                                append_bits=append_bits | ({code_bits,120'b0} >> append_count);
                                append_count=append_count+code_length;
                            end
                            if(10'(work_count)+10'(append_count)<=10'd384) begin
                                work_bits=work_bits | ({append_bits,192'b0} >> work_count);
                                work_count=work_count+append_count;
                                encoded_bits<=encoded_bits+32'(append_count);
                                if(int'(encode_pos_q)+group_count==int'(lengths[encode_q])) begin
                                    ready_q[encode_q]<=0;encode_q<=!encode_q;encode_pos_q<=0;
                                    if(last_q[encode_q])coding_complete_q<=1;
                                end else encode_pos_q<=encode_pos_q+6'(group_count);
                            end
                        end
                        reservoir_q<=work_bits;reservoir_bits_q<=9'(work_count);
                    end
                end
            end
        end
    end
    /* verilator lint_on BLKSEQ */
endmodule
`default_nettype wire
