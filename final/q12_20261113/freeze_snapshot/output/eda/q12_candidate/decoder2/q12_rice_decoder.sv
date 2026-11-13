`timescale 1ns/1ps
`default_nettype none
module q12_rice_decoder #(
    parameter integer LANES = 2,
    parameter integer HISTORY_SYMBOLS = 64
) (
    input wire clk, rst_n,
    input wire start_valid, output wire start_ready,
    input wire [15:0] start_symbols,
    input wire [31:0] start_encoded_bits,
    input wire [3:0] start_k,
    input wire start_delta,
    input wire [8:0] start_row_symbols,
    input wire in_valid, output wire in_ready,
    input wire [31:0] in_data,
    input wire [5:0] in_valid_bits,
    input wire in_last,
    output reg out_valid, input wire out_ready,
    output reg [47:0] out_data,
    output reg [2:0] out_count,
    output reg out_last,
    output reg busy, done, error,
    output reg [31:0] total_cycles, consumed_bits
);
    // Canonical Rice32, signed12, k6 or k9. Delta64 is modulo4096.
    // Bus bytes are little-endian words; the first stream bit is bit7 of byte0.
    // Output is at most two restored symbols in low24bits; upper24bits are zero. This is row-major;
    // the task core still needs its existing X/W pair-order reorder stage.
    // Error drains input through in_last and preserves an already held output.
    localparam integer HISTORY_ADDR_W = $clog2(HISTORY_SYMBOLS);
    // Six balanced levels count the leading unary ones; 64 means no terminator.
    function automatic [6:0] leading_ones64(input [63:0] value);
        reg [63:0] work;
        reg [6:0] count;
        begin
            work=value; count=0;
            if (&work[63:32]) begin count=count+32; work=work<<32; end
            if (&work[63:48]) begin count=count+16; work=work<<16; end
            if (&work[63:56]) begin count=count+8;  work=work<<8; end
            if (&work[63:60]) begin count=count+4;  work=work<<4; end
            if (&work[63:62]) begin count=count+2;  work=work<<2; end
            if (work[63])    begin count=count+1;  work=work<<1; end
            if (work[63]) count=count+1;
            leading_ones64=count;
        end
    endfunction
    // A72bit window covers every legal k6/k9 symbol. The complete
    //320bit reservoir is shifted once only after a whole output group commits.
    function automatic [71:0] peek72(input [319:0] bits, input [8:0] offset);
        reg [391:0] padded;
        begin
            padded={bits,72'b0};
            peek72=72'(padded >> (9'd320-offset));
        end
    endfunction
    reg [71:0] symbol_window, remainder_window;
    // Only workspace/count widths change. Invalid input does not append bits.
    // A legal append is <=288+32=320; every parse decrement is availability guarded.
    // A block has <=32 symbols, each canonical-cost contribution <=63+1+6=70.
    // Wide frame byte/bit counters and their malformed-stream guards are retained.
    reg [8:0] parse_offset;
    reg [15:0] total_q, decoded_q;
    reg [31:0] expected_bits_q, received_bits_q;
    reg [3:0] k_q;
    reg delta_q;
    reg [8:0] row_symbols_q;
    reg [11:0] history[0:HISTORY_SYMBOLS-1];
    reg end_seen_q, block_raw_q;
    reg [5:0] block_left_q;
    reg [5:0] block_symbols_q;
    reg [11:0] block_rice_cost_q;
    reg [319:0] reservoir_q, work_bits;
    reg [8:0] reservoir_count_q;
    reg [31:0] incoming;
    reg [47:0] decoded_word;
    reg [11:0] symbol_value, restored, decoded_symbols[0:3];
    reg [HISTORY_ADDR_W-1:0] column;
    reg [8:0] work_count, parse_count;
    reg [5:0] block_left;
    reg [2:0] target;
    integer j;
    reg [6:0] quotient, code_length;
    reg [8:0] remainder;
    reg [15:0] u;
    reg [8:0] bit_delta;
    reg [5:0] block_symbols;
    reg [11:0] block_rice_cost;
    reg seen_end, parse_raw, enough, bad, found_zero, frame_complete;
    assign start_ready=rst_n && !busy && !out_valid;
    assign in_ready=rst_n && busy && !end_seen_q && (error || reservoir_count_q<=288);
    initial begin
        if(LANES!=2)$fatal(1,"two-symbol decoder requires LANES=2");
        if(HISTORY_SYMBOLS!=64)$fatal(1,"fixed decoder requires HISTORY_SYMBOLS=64");
    end
    // Blocking assignments are local parse workspaces, not retained state.
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin
        if(!rst_n)begin
            busy<=0;done<=0;error<=0;out_valid<=0;out_data<=0;out_count<=0;out_last<=0;
            total_cycles<=0;consumed_bits<=0;total_q<=0;decoded_q<=0;expected_bits_q<=0;received_bits_q<=0;
            k_q<=0;delta_q<=0;row_symbols_q<=0;end_seen_q<=0;block_raw_q<=0;block_left_q<=0;reservoir_q<=0;reservoir_count_q<=0;
            block_symbols_q<=0;block_rice_cost_q<=0;
        end else begin
            done<=0;
            if(out_valid && out_ready)begin out_valid<=0;if(out_last && !error)begin busy<=0;done<=1;end end
            if(start_valid && start_ready)begin
                bad=start_symbols==0 || (start_k!=6 && start_k!=9) || start_encoded_bits==0 ||
                    start_encoded_bits>32'(start_symbols)*12+((32'(start_symbols)+31)>>5) ||
                    (start_delta && start_row_symbols!=64);
                busy<=1;error<=bad;total_cycles<=1;consumed_bits<=0;total_q<=start_symbols;decoded_q<=0;
                expected_bits_q<=start_encoded_bits;received_bits_q<=0;k_q<=start_k;delta_q<=start_delta;row_symbols_q<=start_row_symbols;
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
                            work_bits=work_bits | ({incoming,288'b0} >> work_count);
                            work_count=work_count+int'(in_valid_bits);
                        end
                        received_bits_q<=received_bits_q+32'(in_valid_bits);
                        if(in_last)begin seen_end=1;end_seen_q<=1;end
                    end
                    if(!bad && (!out_valid || out_ready) && decoded_q<total_q)begin
                        parse_offset=0;parse_count=work_count;block_left=int'(block_left_q);parse_raw=block_raw_q;
                        block_symbols=int'(block_symbols_q);block_rice_cost=int'(block_rice_cost_q);
                        target=(int'(total_q)-int'(decoded_q)>LANES) ? LANES : int'(total_q)-int'(decoded_q);
                        enough=1;decoded_word=0;
                        for(j=0;j<LANES;j=j+1)if(j<target && enough && !bad)begin
                            if(block_left==0)begin
                                if(parse_count<1)enough=0;
                                else begin
                                    parse_raw=work_bits[319-parse_offset];parse_offset=parse_offset+1;parse_count=parse_count-1;
                                    block_left=(int'(total_q)-int'(decoded_q)-j>32) ? 32 : int'(total_q)-int'(decoded_q)-j;
                                    block_symbols=block_left;block_rice_cost=0;
                                end
                            end
                            if(enough)begin
                                symbol_window=peek72(work_bits,9'(parse_offset));
                                if(parse_raw)begin
                                    if(parse_count<12)enough=0;
                                    else begin symbol_value=symbol_window[71:60];parse_offset=parse_offset+12;parse_count=parse_count-12;end
                                end else begin
                                    quotient=int'(leading_ones64(symbol_window[71:8]));
                                    found_zero=(quotient<64 && quotient<parse_count);
                                    if(quotient>parse_count)quotient=parse_count;
                                    // Invalid start_k enters error drain before this parser is active.
                                    if(quotient>(k_q==6 ? 63 : 7))bad=1;
                                    code_length=quotient+(k_q==6 ? 7 : 10);
                                    if(!found_zero || parse_count<code_length)enough=0;
                                    if(enough && !bad)begin
                                        // Signed12 k6 needs at most63 unary bits; k9 at most7.
                                        // This72-bit window contains every legal remainder.
                                        remainder_window=symbol_window << (quotient+1);
                                        if(k_q==6) remainder=int'(remainder_window[71:66]);
                                        else remainder=int'(remainder_window[71:63]);
                                        u=(k_q==6 ? (quotient<<6) : (quotient<<9))|remainder;
                                        if(u>4095)bad=1;
                                        symbol_value=12'(u>>1) ^ {12{u[0]}};
                                        parse_offset=parse_offset+code_length;parse_count=parse_count-code_length;
                                    end
                                end
                                if(enough && !bad)begin
                                    decoded_symbols[j]=symbol_value;block_left=block_left-1;
                                    u=int'({symbol_value[10:0],1'b0} ^ {12{symbol_value[11]}});
                                    block_rice_cost=block_rice_cost+(k_q==6 ? (u>>6) : (u>>9))+(k_q==6 ? 7 : 10);
                                    if(block_left==0 && parse_raw!=(block_rice_cost>=12*block_symbols))bad=1;
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
                                symbol_value=decoded_symbols[j];restored=symbol_value;
                                column=HISTORY_ADDR_W'((int'(decoded_q)+j)&(int'(row_symbols_q)-1));
                                if(delta_q)begin
                                    if(int'(decoded_q)+j>=int'(row_symbols_q))restored=symbol_value+history[column];
                                    history[column]<=restored;
                                end
                                decoded_word[j*12+:12]=restored;
                            end
                            out_data<=decoded_word;out_count<=3'(target);out_last<=frame_complete;out_valid<=1;
                            decoded_q<=decoded_q+16'(target);block_left_q<=6'(block_left);block_raw_q<=parse_raw;
                            block_symbols_q<=6'(block_symbols);block_rice_cost_q<=12'(block_rice_cost);
                            consumed_bits<=consumed_bits+32'(bit_delta);work_bits=work_bits << 9'(parse_offset);work_count=parse_count;
                        end
                    end
                    if(bad)begin error<=1;reservoir_q<=0;reservoir_count_q<=0;end
                    else begin reservoir_q<=work_bits;reservoir_count_q<=9'(work_count);end
                end
            end
        end
    end
    /* verilator lint_on BLKSEQ */
endmodule
`default_nettype wire
