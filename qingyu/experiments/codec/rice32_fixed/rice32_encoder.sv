`timescale 1ns/1ps
`default_nettype none
module rice32_encoder #(
    parameter integer LANES = 4,
    parameter integer HISTORY_BYTES = 16
) (
    input wire clk, rst_n,
    input wire start_valid, output wire start_ready,
    input wire [15:0] start_symbols,
    input wire [2:0] start_k,
    input wire start_delta,
    input wire [8:0] start_row_bytes,
    input wire in_valid, output wire in_ready,
    input wire [31:0] in_data,
    input wire [2:0] in_count,
    input wire in_last,
    output reg out_valid, input wire out_ready,
    output reg [31:0] out_data,
    output reg [5:0] out_valid_bits,
    output reg out_last,
    output reg busy, done, error,
    output reg [31:0] total_cycles, encoded_bits
);
    localparam integer HISTORY_ADDR_W = $clog2(HISTORY_BYTES);
    reg [15:0] symbol_total_q, received_q;
    
    reg delta_q;
    reg [8:0] row_bytes_q;
    reg [7:0] history [0:HISTORY_BYTES-1];
    reg [7:0] blocks [0:1][0:31];
    reg [1:0] ready_q, raw_q, last_q;
    reg [5:0] lengths [0:1];
    reg fill_q, encode_q;
    reg [5:0] fill_count_q, encode_pos_q;
    reg [15:0] rice_cost_q;
    reg input_ended_q, coding_complete_q;
    reg [255:0] reservoir_q;
    reg [7:0] reservoir_bits_q;
    reg [255:0] work_bits;
    reg [63:0] code_bits;
    reg [31:0] head_word;
    reg [7:0] byte_value, transformed, unsigned_value;
    integer work_count, code_length, emit_count, group_count;
    reg [HISTORY_ADDR_W-1:0] column;
    integer j, sum_cost, new_count, q, remainder, expected_count;
    reg bad_beat;

    assign start_ready = rst_n && !busy && !out_valid;
    assign in_ready = rst_n && busy && !input_ended_q && (error || !ready_q[fill_q]);

    function automatic [7:0] zigzag(input reg [7:0] byte_in);
        integer signed value;
        begin
            value = byte_in < 128 ? int'(byte_in) : int'(byte_in)-256;
            zigzag = 8'(value < 0 ? -2*value-1 : 2*value);
        end
    endfunction


    initial begin
        if(HISTORY_BYTES!=16)$fatal(1,"fixed encoder requires HISTORY_BYTES=16");
        if (LANES != 4) $fatal(1,"fixed encoder requires LANES=4");
    end
    // Blocking assignments below are local combinational workspaces; every
    // retained protocol/datapath register uses a nonblocking assignment.
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin
        if (!rst_n) begin
            busy<=0;done<=0;error<=0;out_valid<=0;out_data<=0;out_valid_bits<=0;out_last<=0;
            total_cycles<=0;encoded_bits<=0;symbol_total_q<=0;received_q<=0;delta_q<=0;row_bytes_q<=0;
            ready_q<=0;raw_q<=0;last_q<=0;fill_q<=0;encode_q<=0;fill_count_q<=0;encode_pos_q<=0;rice_cost_q<=0;
            lengths[0]<=0;lengths[1]<=0;input_ended_q<=0;coding_complete_q<=0;reservoir_q<=0;reservoir_bits_q<=0;
        end else begin
            done<=0;
            if (out_valid && out_ready) begin
                out_valid<=0;
                if (out_last && !error) begin busy<=0;done<=1;end
            end
            if (start_valid && start_ready) begin
                busy<=1;error<=start_symbols==0 || start_k!=3 || (start_delta && start_row_bytes!=16);
                total_cycles<=1;encoded_bits<=0;symbol_total_q<=start_symbols;received_q<=0;
                delta_q<=start_delta;row_bytes_q<=start_row_bytes;
                ready_q<=0;raw_q<=0;last_q<=0;fill_q<=0;encode_q<=0;fill_count_q<=0;encode_pos_q<=0;rice_cost_q<=0;
                input_ended_q<=start_symbols==0 || start_k!=3 || (start_delta && start_row_bytes!=16);
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
                        expected_count = int'(symbol_total_q)-int'(received_q);
                        if (expected_count>LANES) expected_count=LANES;
                        bad_beat = int'(in_count)!=expected_count || in_count==0 ||
                                   in_last!=(int'(received_q)+int'(in_count)==int'(symbol_total_q));
                        if (bad_beat) begin error<=1;input_ended_q<=in_last;end
                        else begin
                            sum_cost=int'(rice_cost_q);
                            for(j=0;j<LANES;j=j+1) if(j<int'(in_count)) begin
                                byte_value=in_data[j*8+:8];
                                column=HISTORY_ADDR_W'((int'(received_q)+j)&(int'(row_bytes_q)-1));
                                transformed=byte_value;
                                if(delta_q) begin
                                    if(int'(received_q)+j>=int'(row_bytes_q)) transformed=byte_value-history[column];
                                    history[column]<=byte_value;
                                end
                                blocks[fill_q][int'(fill_count_q)+j]<=transformed;
                                unsigned_value=zigzag(transformed);
                                sum_cost=sum_cost+(int'(unsigned_value)>>3)+1+3;
                            end
                            new_count=int'(fill_count_q)+int'(in_count);
                            received_q<=received_q+16'(in_count);
                            if(new_count==32 || in_last) begin
                                ready_q[fill_q]<=1;raw_q[fill_q]<=sum_cost>=8*new_count;last_q[fill_q]<=in_last;
                                lengths[fill_q]<=6'(new_count);fill_q<=!fill_q;fill_count_q<=0;rice_cost_q<=0;
                            end else begin fill_count_q<=6'(new_count);rice_cost_q<=16'(sum_cost);end
                            if(in_last) input_ended_q<=1;
                        end
                    end
                    if(bad_beat) begin ready_q<=0;reservoir_q<=0;reservoir_bits_q<=0;end
                    else begin
                        work_bits=reservoir_q;work_count=int'(reservoir_bits_q);
                        if((!out_valid || out_ready) && (work_count>32 || (coding_complete_q && work_count>0))) begin
                            emit_count=work_count<32?work_count:32;
                            head_word=work_bits[255:224];
                            out_data<={head_word[7:0],head_word[15:8],head_word[23:16],head_word[31:24]};
                            out_valid_bits<=6'(emit_count);out_last<=coding_complete_q && work_count<=32;out_valid<=1;
                            work_bits=work_bits<<emit_count;work_count=work_count-emit_count;
                        end
                        if(ready_q[encode_q] && work_count<=112) begin
                            new_count=work_count;
                            if(encode_pos_q==0) begin
                                code_bits=0;code_bits[63]=raw_q[encode_q];
                                work_bits=work_bits | ({code_bits,192'b0} >> work_count);
                                work_count=work_count+1;
                            end
                            group_count=int'(lengths[encode_q])-int'(encode_pos_q);
                            if(group_count>LANES)group_count=LANES;
                            for(j=0;j<LANES;j=j+1) if(j<group_count) begin
                                byte_value=blocks[encode_q][int'(encode_pos_q)+j];code_bits=0;
                                if(raw_q[encode_q]) begin code_bits[63:56]=byte_value;code_length=8;end
                                else begin
                                    unsigned_value=zigzag(byte_value);q=int'(unsigned_value)>>3;
                                    remainder=int'(unsigned_value)&((1<<3)-1);code_length=q+1+3;
                                    code_bits=(~64'b0 << (64-q)) | (64'(remainder) << (64-code_length));
                                end
                                work_bits=work_bits | ({code_bits,192'b0} >> work_count);
                                work_count=work_count+code_length;
                            end
                            encoded_bits<=encoded_bits+32'(work_count-new_count);
                            if(int'(encode_pos_q)+group_count==int'(lengths[encode_q])) begin
                                ready_q[encode_q]<=0;encode_q<=!encode_q;encode_pos_q<=0;
                                if(last_q[encode_q])coding_complete_q<=1;
                            end else encode_pos_q<=encode_pos_q+6'(group_count);
                        end
                        reservoir_q<=work_bits;reservoir_bits_q<=8'(work_count);
                    end
                end
            end
        end
    end
    /* verilator lint_on BLKSEQ */
endmodule
`default_nettype wire
