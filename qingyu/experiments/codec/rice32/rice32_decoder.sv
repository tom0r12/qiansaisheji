`timescale 1ns/1ps
`default_nettype none
module rice32_decoder #(
    parameter integer LANES = 4
) (
    input wire clk, rst_n,
    input wire start_valid, output wire start_ready,
    input wire [15:0] start_symbols,
    input wire [31:0] start_encoded_bits,
    input wire [2:0] start_k,
    input wire start_delta,
    input wire [8:0] start_row_bytes,
    input wire in_valid, output wire in_ready,
    input wire [31:0] in_data,
    input wire [5:0] in_valid_bits,
    input wire in_last,
    output reg out_valid, input wire out_ready,
    output reg [31:0] out_data,
    output reg [2:0] out_count,
    output reg out_last,
    output reg busy, done, error,
    output reg [31:0] total_cycles, consumed_bits
);
    reg [15:0] total_q, decoded_q;
    reg [31:0] expected_bits_q, received_bits_q;
    reg [2:0] k_q;
    reg delta_q;
    reg [8:0] row_bytes_q;
    reg [7:0] history[0:255];
    reg end_seen_q, block_raw_q;
    reg [5:0] block_left_q;
    reg [5:0] block_symbols_q;
    reg [15:0] block_rice_cost_q;
    reg [511:0] reservoir_q, work_bits, parse_bits;
    reg [9:0] reservoir_count_q;
    reg [31:0] incoming, decoded_word;
    reg [7:0] byte_value, restored, decoded_bytes[0:3];
    reg [7:0] column;
    integer work_count, parse_count, block_left, target, j, scan, quotient, remainder, code_length, u;
    integer bit_delta, block_symbols, block_rice_cost, signed_byte;
    reg seen_end, parse_raw, enough, bad, found_zero, frame_complete;
    assign start_ready=rst_n && !busy && !out_valid;
    assign in_ready=rst_n && busy && !end_seen_q && (error || reservoir_count_q<=480);
    initial begin if(LANES!=2 && LANES!=4)$fatal(1,"LANES must be 2 or 4");end
    // Blocking assignments are local parse workspaces, not retained state.
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin
        if(!rst_n)begin
            busy<=0;done<=0;error<=0;out_valid<=0;out_data<=0;out_count<=0;out_last<=0;
            total_cycles<=0;consumed_bits<=0;total_q<=0;decoded_q<=0;expected_bits_q<=0;received_bits_q<=0;
            k_q<=0;delta_q<=0;row_bytes_q<=0;end_seen_q<=0;block_raw_q<=0;block_left_q<=0;reservoir_q<=0;reservoir_count_q<=0;
            block_symbols_q<=0;block_rice_cost_q<=0;
        end else begin
            done<=0;
            if(out_valid && out_ready)begin out_valid<=0;if(out_last && !error)begin busy<=0;done<=1;end end
            if(start_valid && start_ready)begin
                bad=start_symbols==0 || start_encoded_bits==0 ||
                    start_encoded_bits>32'(start_symbols)*8+((32'(start_symbols)+31)>>5) ||
                    (start_delta && start_row_bytes!=16 && start_row_bytes!=64 && start_row_bytes!=256);
                busy<=1;error<=bad;total_cycles<=1;consumed_bits<=0;total_q<=start_symbols;decoded_q<=0;
                expected_bits_q<=start_encoded_bits;received_bits_q<=0;k_q<=start_k;delta_q<=start_delta;row_bytes_q<=start_row_bytes;
                end_seen_q<=bad;block_left_q<=0;block_raw_q<=0;reservoir_q<=0;reservoir_count_q<=0;block_symbols_q<=0;block_rice_cost_q<=0;
            end else if(busy)begin
                total_cycles<=total_cycles+1;
                if(error)begin
                    reservoir_q<=0;reservoir_count_q<=0;
                    if(in_valid && in_ready && in_last)end_seen_q<=1;
                    if((end_seen_q || (in_valid && in_ready && in_last)) && (!out_valid || out_ready))begin busy<=0;done<=1;end
                end else begin
                    work_bits=reservoir_q;work_count=int'(reservoir_count_q);seen_end=end_seen_q;bad=0;
                    if(in_valid && in_ready)begin
                        incoming={in_data[7:0],in_data[15:8],in_data[23:16],in_data[31:24]};
                        bad=in_valid_bits==0 || in_valid_bits>32 || (!in_last && in_valid_bits!=32) ||
                            received_bits_q+32'(in_valid_bits)>expected_bits_q ||
                            in_last!=(received_bits_q+32'(in_valid_bits)==expected_bits_q);
                        if(in_valid_bits<32 && (incoming & (32'hffffffff >> in_valid_bits))!=0)bad=1;
                        if(!bad)begin
                            work_bits=work_bits | ({incoming,480'b0} >> work_count);
                            work_count=work_count+int'(in_valid_bits);
                        end
                        received_bits_q<=received_bits_q+32'(in_valid_bits);
                        if(in_last)begin seen_end=1;end_seen_q<=1;end
                    end
                    if(!bad && (!out_valid || out_ready) && decoded_q<total_q)begin
                        parse_bits=work_bits;parse_count=work_count;block_left=int'(block_left_q);parse_raw=block_raw_q;
                        block_symbols=int'(block_symbols_q);block_rice_cost=int'(block_rice_cost_q);
                        target=int'(total_q)-int'(decoded_q);if(target>LANES)target=LANES;
                        enough=1;decoded_word=0;
                        for(j=0;j<LANES;j=j+1)if(j<target && enough && !bad)begin
                            if(block_left==0)begin
                                if(parse_count<1)enough=0;
                                else begin
                                    parse_raw=parse_bits[511];parse_bits=parse_bits<<1;parse_count=parse_count-1;
                                    block_left=int'(total_q)-int'(decoded_q)-j;if(block_left>32)block_left=32;
                                    block_symbols=block_left;block_rice_cost=0;
                                end
                            end
                            if(enough)begin
                                if(parse_raw)begin
                                    if(parse_count<8)enough=0;
                                    else begin byte_value=parse_bits[511:504];parse_bits=parse_bits<<8;parse_count=parse_count-8;end
                                end else begin
                                    quotient=0;found_zero=0;
                                    for(scan=0;scan<256;scan=scan+1)if(!found_zero && scan<parse_count)begin
                                        if(parse_bits[511-scan])quotient=quotient+1;
                                        else found_zero=1;
                                    end
                                    if(quotient>(255>>k_q))bad=1;
                                    code_length=quotient+1+int'(k_q);
                                    if(!found_zero || parse_count<code_length)enough=0;
                                    if(enough && !bad)begin
                                        remainder=0;
                                        for(scan=0;scan<7;scan=scan+1)if(scan<int'(k_q))
                                            remainder=(remainder<<1)|int'(parse_bits[510-quotient-scan]);
                                        u=(quotient<<k_q)|remainder;
                                        if(u>255)bad=1;
                                        byte_value=8'((u&1)!=0?-((u+1)>>1):(u>>1));
                                        parse_bits=parse_bits<<code_length;parse_count=parse_count-code_length;
                                    end
                                end
                                if(enough && !bad)begin
                                    decoded_bytes[j]=byte_value;block_left=block_left-1;
                                    signed_byte=byte_value<128?int'(byte_value):int'(byte_value)-256;
                                    u=signed_byte<0?-2*signed_byte-1:2*signed_byte;
                                    block_rice_cost=block_rice_cost+(u>>k_q)+1+int'(k_q);
                                    if(block_left==0 && parse_raw!=(block_rice_cost>=8*block_symbols))bad=1;
                                end
                            end
                        end
                        if(!enough && seen_end)bad=1;
                        frame_complete=int'(decoded_q)+target==int'(total_q);
                        bit_delta=work_count-parse_count;
                        if(enough && !bad && frame_complete &&
                           (!seen_end || parse_count!=0 || consumed_bits+32'(bit_delta)!=expected_bits_q))bad=1;
                        if(enough && !bad)begin
                            for(j=0;j<LANES;j=j+1)if(j<target)begin
                                byte_value=decoded_bytes[j];restored=byte_value;
                                column=8'((int'(decoded_q)+j)&(int'(row_bytes_q)-1));
                                if(delta_q)begin
                                    if(int'(decoded_q)+j>=int'(row_bytes_q))restored=byte_value+history[column];
                                    history[column]<=restored;
                                end
                                decoded_word[j*8+:8]=restored;
                            end
                            out_data<=decoded_word;out_count<=3'(target);out_last<=frame_complete;out_valid<=1;
                            decoded_q<=decoded_q+16'(target);block_left_q<=6'(block_left);block_raw_q<=parse_raw;
                            block_symbols_q<=6'(block_symbols);block_rice_cost_q<=16'(block_rice_cost);
                            consumed_bits<=consumed_bits+32'(bit_delta);work_bits=parse_bits;work_count=parse_count;
                        end
                    end
                    if(bad)begin error<=1;reservoir_q<=0;reservoir_count_q<=0;end
                    else begin reservoir_q<=work_bits;reservoir_count_q<=10'(work_count);end
                end
            end
        end
    end
    /* verilator lint_on BLKSEQ */
endmodule
`default_nettype wire
