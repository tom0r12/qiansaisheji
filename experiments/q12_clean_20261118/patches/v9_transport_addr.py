"""Register running DMA addresses (rd_next_addr / wr_next_addr) and gate available_end_q
in v9a/v9b so dma_cmd_addr has zero combinational 32/35-bit adders on the output path
(fixing the -6.34 ns ss_m40c path seen in 09 with 0 cycle overhead and fewer FFs).
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import check_decl_order


def patch_gate(p: Path):
    t = p.read_text(encoding='utf-8').replace('\r\n', '\n')
    if 'output reg [34:0] available_end_o' in t:
        return
    old1 = "    output reg [31:0] source_base, total_words, available_words, epoch,\n"
    new1 = "    output reg [31:0] source_base, total_words, available_words, epoch,\n    output reg [34:0] available_end_o,\n"
    assert old1 in t, f'gate old1 missing in {p}'
    t = t.replace(old1, new1, 1)

    old2 = "            active<=0;source_base<=0;total_words<=0;available_words<=0;epoch<=0;\n"
    new2 = "            active<=0;source_base<=0;total_words<=0;available_words<=0;epoch<=0;available_end_o<=0;\n"
    assert old2 in t, f'gate old2 missing in {p}'
    t = t.replace(old2, new2, 1)

    old3 = "                    available_words<=start_available_words;epoch<=start_epoch;\n"
    new3 = "                    available_words<=start_available_words;epoch<=start_epoch;\n                    available_end_o<={3'b0,start_source_base}+{1'b0,start_available_words,2'b0};\n"
    assert old3 in t, f'gate old3 missing in {p}'
    t = t.replace(old3, new3, 1)

    old4 = "            if(active && hw_enable && hw_words>available_words && hw_words<=total_words)\n                available_words<=hw_words;\n"
    new4 = ("            if(active && hw_enable && hw_words>available_words && hw_words<=total_words)begin\n"
            "                available_words<=hw_words;\n"
            "                available_end_o<={3'b0,source_base}+{1'b0,hw_words,2'b0};\n"
            "            end\n")
    assert old4 in t, f'gate old4 missing in {p}'
    t = t.replace(old4, new4, 1)

    old5 = "                else available_words<=commit_available_words;\n"
    new5 = ("                else begin\n"
            "                    available_words<=commit_available_words;\n"
            "                    available_end_o<={3'b0,source_base}+{1'b0,commit_available_words,2'b0};\n"
            "                end\n")
    assert old5 in t, f'gate old5 missing in {p}'
    t = t.replace(old5, new5, 1)

    p.write_text(t, encoding='utf-8', newline='\n')


def patch_transport(p: Path):
    t = p.read_text(encoding='utf-8').replace('\r\n', '\n')
    if 'wr_desc_strided' in t:
        return
    old1 = " input wire wr_desc_prefix,\n input wire [31:0] wr_desc_base,wr_desc_count,\n"
    new1 = (" input wire wr_desc_prefix,\n input wire wr_desc_strided,\n input wire [3:0] wr_desc_tile,\n"
            " input wire [31:0] wr_desc_base,wr_desc_count,\n")
    assert old1 in t, f'transport old1 missing in {p}'
    t = t.replace(old1, new1, 1)

    old2 = (" reg rd_active,wr_active,fault_q,prefer_read;\n"
            " reg wr_prefix,wr_closed;\n"
            " reg [31:0] rd_base,rd_total,rd_issued,rd_delivered;\n"
            " reg [31:0] wr_base,wr_total,wr_supplied,wr_issued,wr_retired;\n")
    new2 = (" reg rd_active,wr_active,fault_q,prefer_read;\n"
            " reg wr_prefix,wr_closed,wr_strided;\n"
            " reg [34:0] rd_next_addr;\n"
            " reg [31:0] rd_total,rd_issued,rd_delivered;\n"
            " reg [31:0] wr_next_addr,wr_total,wr_supplied,wr_issued,wr_retired;\n")
    assert old2 in t, f'transport old2 missing in {p}'
    t = t.replace(old2, new2, 1)

    old3 = (" wire valid_write_descriptor=descriptor_good(wr_desc_base,wr_desc_count)&&\n"
            "                              (!wr_desc_prefix||wr_desc_count<=32'd646);\n")
    new3 = (" wire [34:0] wr_strided_end={3'b0,wr_desc_base}+{26'b0,wr_desc_tile,5'b0}+35'd50208;\n"
            " wire valid_write_descriptor=(wr_desc_strided ?\n"
            "                              (wr_desc_base[1:0]==0 && wr_desc_base>=32'ha0000000 &&\n"
            "                               wr_desc_count==32'd792 && !wr_desc_prefix && wr_strided_end<=35'ha0080000) :\n"
            "                              descriptor_good(wr_desc_base,wr_desc_count))&&\n"
            "                              (!wr_desc_prefix||wr_desc_count<=32'd646);\n")
    assert old3 in t, f'transport old3 missing in {p}'
    t = t.replace(old3, new3, 1)

    old4 = (" wire read_eligible=rd_active&&rd_issued<rd_total&&read_space&&\n"
            "                    (({3'b0,rd_base}+{1'b0,rd_issued,2'b0})<rd_avail_end);\n"
            " wire write_eligible=wr_active&&wr_issued<wr_total&&(write_count!=0);\n"
            " wire choose_read=read_eligible&&(!write_eligible||prefer_read);\n"
            " wire offer_new=rst_n&&!fault_q&&!stop_now&&credit_available&&(read_eligible||write_eligible);\n"
            " assign icb_cmd_valid=rst_n&&(held_valid||offer_new);\n"
            " assign icb_cmd_read=held_valid?held_read:choose_read;\n"
            " assign icb_cmd_addr=held_valid?held_addr:\n"
            "                     choose_read?(rd_base+(rd_issued<<2)):(wr_base+(wr_issued<<2));\n")
    new4 = (" wire read_eligible=rd_active&&rd_issued<rd_total&&read_space&&(rd_next_addr<rd_avail_end);\n"
            " wire write_eligible=wr_active&&wr_issued<wr_total&&(write_count!=0);\n"
            " wire choose_read=read_eligible&&(!write_eligible||prefer_read);\n"
            " wire offer_new=rst_n&&!fault_q&&!stop_now&&credit_available&&(read_eligible||write_eligible);\n"
            " assign icb_cmd_valid=rst_n&&(held_valid||offer_new);\n"
            " assign icb_cmd_read=held_valid?held_read:choose_read;\n"
            " assign icb_cmd_addr=held_valid?held_addr:(choose_read?rd_next_addr[31:0]:wr_next_addr);\n")
    assert old4 in t, f'transport old4 missing in {p}'
    t = t.replace(old4, new4, 1)

    old5 = ("   rd_active<=0;wr_active<=0;fault_q<=0;prefer_read<=1;wr_prefix<=0;wr_closed<=0;\n"
            "   rd_base<=0;rd_total<=0;rd_issued<=0;rd_delivered<=0;\n"
            "   wr_base<=0;wr_total<=0;wr_supplied<=0;wr_issued<=0;wr_retired<=0;\n")
    new5 = ("   rd_active<=0;wr_active<=0;fault_q<=0;prefer_read<=1;wr_prefix<=0;wr_closed<=0;wr_strided<=0;\n"
            "   rd_next_addr<=0;rd_total<=0;rd_issued<=0;rd_delivered<=0;\n"
            "   wr_next_addr<=0;wr_total<=0;wr_supplied<=0;wr_issued<=0;wr_retired<=0;\n")
    assert old5 in t, f'transport old5 missing in {p}'
    t = t.replace(old5, new5, 1)

    old6 = "     rd_active<=1;rd_base<=rd_desc_base;rd_total<=rd_desc_count;rd_issued<=0;rd_delivered<=0;\n"
    new6 = "     rd_active<=1;rd_next_addr<={3'b0,rd_desc_base};rd_total<=rd_desc_count;rd_issued<=0;rd_delivered<=0;\n"
    assert old6 in t, f'transport old6 missing in {p}'
    t = t.replace(old6, new6, 1)

    old7 = ("     wr_active<=1;wr_base<=wr_desc_base;wr_total<=wr_desc_count;\n"
            "     wr_prefix<=wr_desc_prefix;wr_closed<=!wr_desc_prefix;\n")
    new7 = ("     wr_active<=1;wr_strided<=wr_desc_strided;wr_total<=wr_desc_count;\n"
            "     wr_next_addr<=wr_desc_strided?(wr_desc_base+{23'b0,wr_desc_tile,5'b0}):wr_desc_base;\n"
            "     wr_prefix<=wr_desc_prefix;wr_closed<=!wr_desc_prefix;\n")
    assert old7 in t, f'transport old7 missing in {p}'
    t = t.replace(old7, new7, 1)

    old8 = ("    if(icb_cmd_read)rd_issued<=rd_issued+1'b1;\n"
            "    else wr_issued<=wr_issued+1'b1;\n")
    new8 = ("    if(icb_cmd_read)begin rd_issued<=rd_issued+1'b1;rd_next_addr<=rd_next_addr+35'd4;end\n"
            "    else begin\n"
            "     wr_issued<=wr_issued+1'b1;\n"
            "     wr_next_addr<=wr_next_addr+((wr_strided&&wr_issued[2:0]==3'd7)?32'd484:32'd4);\n"
            "    end\n")
    assert old8 in t, f'transport old8 missing in {p}'
    t = t.replace(old8, new8, 1)

    p.write_text(t, encoding='utf-8', newline='\n')


def patch_engine(p: Path):
    t = p.read_text(encoding='utf-8').replace('\r\n', '\n')
    if 'gate_available_end' in t:
        return
    old1 = (" wire [31:0] transport_cmd_addr;\n"
            " reg payload_map_active;\n"
            " reg [3:0] payload_tile;\n"
            " wire [31:0] payload_local_word=(transport_cmd_addr-output_base-32'd68)>>2;\n"
            " // BEGIN DENSE_ADDRESS_MAP: retain ownership through stalled offers/abort drain.\n"
            " assign icb_cmd_addr=payload_map_active&&!icb_cmd_read ?\n"
            "   output_base+32'd68+((payload_local_word>>3)<<9)+({28'b0,payload_tile}<<5)+\n"
            "   ((payload_local_word&32'd7)<<2) : transport_cmd_addr;\n"
            " always @(posedge clk)begin\n"
            "  if(!rst_n)begin payload_map_active<=0;payload_tile<=0;end\n"
            "  else begin\n"
            "   if(wr_done_valid)payload_map_active<=0;\n"
            "   if(state==RUN && write_state==OUTPUT_REQ && wr_desc_valid&&wr_desc_ready)begin\n"
            "    payload_map_active<=1;payload_tile<=tile;\n"
            "   end\n"
            "  end\n"
            " end\n"
            " // END DENSE_ADDRESS_MAP\n")
    new1 = (" wire [31:0] transport_cmd_addr;\n"
            " wire [34:0] gate_available_end;\n"
            " wire wr_desc_strided=(state==RUN && write_state==OUTPUT_REQ);\n"
            " assign icb_cmd_addr=transport_cmd_addr;\n")
    assert old1 in t, f'engine old1 missing in {p}'
    t = t.replace(old1, new1, 1)

    old2 = "  .source_base(gate_source),.total_words(gate_total),.available_words(gate_available),.epoch(gate_epoch),\n"
    new2 = ("  .source_base(gate_source),.total_words(gate_total),.available_words(gate_available),.epoch(gate_epoch),\n"
            "  .available_end_o(gate_available_end),\n")
    assert old2 in t, f'engine old2 missing in {p}'
    t = t.replace(old2, new2, 1)

    old3 = ("  .rd_avail_end({3'b0,gate_source}+{1'b0,gate_available,2'b0}),\n"
            "  .rd_desc_valid(gated_rd_valid),.rd_desc_ready(gated_rd_ready),.rd_desc_base(gated_rd_base),.rd_desc_count(gated_rd_count),\n"
            "  .rd_word_valid(rd_word_valid),.rd_word_ready(rd_word_ready),.rd_word_data(rd_word_data),.rd_word_last(rd_word_last),\n"
            "  .rd_done_valid(rd_done_valid),.rd_done_ready(1'b1),.rd_done_error(rd_done_error),\n"
            "  .wr_desc_valid(wr_desc_valid),.wr_desc_ready(wr_desc_ready),.wr_desc_prefix(wr_desc_prefix),\n"
            "  .wr_desc_base(wr_desc_base),.wr_desc_count(wr_desc_count),\n")
    new3 = ("  .rd_avail_end(gate_available_end),\n"
            "  .rd_desc_valid(gated_rd_valid),.rd_desc_ready(gated_rd_ready),.rd_desc_base(gated_rd_base),.rd_desc_count(gated_rd_count),\n"
            "  .rd_word_valid(rd_word_valid),.rd_word_ready(rd_word_ready),.rd_word_data(rd_word_data),.rd_word_last(rd_word_last),\n"
            "  .rd_done_valid(rd_done_valid),.rd_done_ready(1'b1),.rd_done_error(rd_done_error),\n"
            "  .wr_desc_valid(wr_desc_valid),.wr_desc_ready(wr_desc_ready),.wr_desc_prefix(wr_desc_prefix),\n"
            "  .wr_desc_strided(wr_desc_strided),.wr_desc_tile(tile),\n"
            "  .wr_desc_base(wr_desc_base),.wr_desc_count(wr_desc_count),\n")
    assert old3 in t, f'engine old3 missing in {p}'
    t = t.replace(old3, new3, 1)

    p.write_text(t, encoding='utf-8', newline='\n')


def main():
    for v in ['v9a', 'v9b']:
        d = HERE / 'variants' / v / 'src'
        patch_gate(d / 'q11_commit_gate.sv')
        patch_transport(d / 'q12_icb_stream_prefix.sv')
        patch_engine(d / 'q12_stream_engine_overlap.sv')
        for f in ['q11_commit_gate.sv', 'q12_icb_stream_prefix.sv', 'q12_stream_engine_overlap.sv']:
            iss = check_decl_order.check(d / f)
            assert not iss, f'decl order issue in {v}/{f}: {iss}'
            print(f'{v}/{f}: ISSUES 0')


if __name__ == '__main__':
    main()
