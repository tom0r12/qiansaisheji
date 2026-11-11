"""Add the INT16-output (OUT16) option to a candidate rtl/ dir and its tb/ dir.

usage: python apply_out16.py <experiment_dir>   (expects <dir>/rtl and <dir>/tb)
Accelerator: parameter OUT16. Two INT16 results per 32-bit word (low lane
first) in the same 8 Y banks and the same bank/address pattern, so the
read-ahead stream is unchanged; the store writes 4 lanes per cycle (4 rounders)
instead of 2, halving store time. FIO/driver/TB: `QINGYU_OUT16` define.
"""
import sys
from pathlib import Path

EXP = Path(sys.argv[1])


def edit(path, reps):
    raw = path.read_bytes().decode()
    crlf = "\r\n" in raw
    s = raw.replace("\r\n", "\n")
    for a, b in reps:
        n = s.count(a)
        assert n == 1, (str(path), a[:80], n)
        s = s.replace(a, b, 1)
    path.write_bytes((s.replace("\n", "\r\n") if crlf else s).encode())


R, T = EXP / "rtl", EXP / "tb"
SEL = lambda L: ("odd_store==3 ? acc3[%s] : odd_store==2 ? acc2[%s] : odd_store==1 ? odd_acc[%s] : acc[%s]"
                 % (L, L, L, L))
LO, HI = "{lane_index[3:2],store_lane[0],1'b0}", "{lane_index[3:2],store_lane[0],1'b1}"

edit(R / "qingyu_accel.sv", [
    ("    parameter integer WEIGHT_STREAM = 0\n) (",
     "    parameter integer WEIGHT_STREAM = 0,\n    parameter integer OUT16 = 0\n) ("),
    ("    localparam TAIL_WORDS = ROWS%8 == 0 ? 128 : (ROWS%8)*16;\n"
     "    assign batch_words[0] = batch_tail[0] ? TAIL_WORDS : 128;\n"
     "    assign batch_words[1] = batch_tail[1] ? TAIL_WORDS : 128;\n",
     "    // OUT16: a row of 16 INT16 results is 8 packed words.\n"
     "    localparam ROW_WORDS = OUT16 ? 8 : 16;\n"
     "    localparam BATCH_WORDS = 8*ROW_WORDS;\n"
     "    localparam TAIL_WORDS = ROWS%8 == 0 ? BATCH_WORDS : (ROWS%8)*ROW_WORDS;\n"
     "    assign batch_words[0] = batch_tail[0] ? TAIL_WORDS : BATCH_WORDS;\n"
     "    assign batch_words[1] = batch_tail[1] ? TAIL_WORDS : BATCH_WORDS;\n"),
    ("(batch_words[stream_slot]-dequeued >= 16)", "(batch_words[stream_slot]-dequeued >= ROW_WORDS)"),
    ("    wire [31:0] current_output = round_sat32(",
     "    // Same arithmetic floor/guard/sticky RNE as round_sat32, INT16 saturation.\n"
     "    function automatic [15:0] round_sat16;\n"
     "        input signed [47:0] value;\n"
     "        input [7:0] amount;\n"
     "        reg signed [95:0] extended, shifted;\n"
     "        reg signed [48:0] rounded;\n"
     "        reg increment;\n"
     "        begin\n"
     "            extended = {value,48'b0};\n"
     "            shifted = extended >>> amount;\n"
     "            increment = shifted[47] && ((|shifted[46:0]) || shifted[48]);\n"
     "            rounded = $signed({shifted[95],shifted[95:48]}) + $signed({48'b0,increment});\n"
     "            if (rounded > 49'sd32767) round_sat16=16'h7fff;\n"
     "            else if (rounded < -49'sd32768) round_sat16=16'h8000;\n"
     "            else round_sat16=rounded[15:0];\n"
     "        end\n"
     "    endfunction\n\n"
     "    wire [31:0] current_output = round_sat32("),
    ("                for(store_lane=0;store_lane<2;store_lane=store_lane+1) begin\n"
     "                    bank_index=write_slot*4+store_lane*2;\n"
     "                    packed_output=round_sat32(",
     "                // OUT16: lanes 4m..4m+3 per cycle; word j=lane/2 of the row goes to\n"
     "                // bank pair j[0] at {row,j[2:1]}, matching the read-ahead pattern.\n"
     "                if (OUT16) for(store_lane=0;store_lane<2;store_lane=store_lane+1) begin\n"
     "                    bank_index=write_slot*4+store_lane*2;\n"
     "                    y_en[bank_index+:2]=2'b11; y_we[bank_index+:2]=2'b11;\n"
     "                    y_addr[bank_index]={store_row[2:0],lane_index[3:2]};\n"
     "                    y_addr[bank_index+1]=y_addr[bank_index];\n"
     "                    y_wdata[bank_index]=round_sat16(" + SEL(LO) + ",shift[" + LO + "]);\n"
     "                    y_wdata[bank_index+1]=round_sat16(" + SEL(HI) + ",shift[" + HI + "]);\n"
     "                end else\n"
     "                for(store_lane=0;store_lane<2;store_lane=store_lane+1) begin\n"
     "                    bank_index=write_slot*4+store_lane*2;\n"
     "                    packed_output=round_sat32("),
    ("                    if (lane_index==LANES-2) begin\n",
     "                    if (lane_index==LANES-(OUT16 ? 4 : 2)) begin\n"),
    ("                    end else lane_index<=lane_index+2;\n",
     "                    end else lane_index<=lane_index+(OUT16 ? 4 : 2);\n"),
])

edit(R / "qingyu_fio.sv", [
    (" localparam IDLE=0, READ_CMD=1, READ_RSP=2, WRITE_CMD=3, WRITE_RSP=4, INPUT_HI=5;\n",
     " localparam IDLE=0, READ_CMD=1, READ_RSP=2, WRITE_CMD=3, WRITE_RSP=4, INPUT_HI=5;\n"
     "`ifdef QINGYU_OUT16\n"
     " // INT16 outputs: an output row is 8 words; output rows are 512 bytes apart.\n"
     " localparam [12:0] OROW_WORDS=8;\n localparam [32:0] OROW_BYTES=512;\n"
     "`else\n"
     " localparam [12:0] OROW_WORDS=16;\n localparam [32:0] OROW_BYTES=1024;\n"
     "`endif\n"),
    (" wire dest_ok= icb_cmd_wdata[5:0]==0 &&\n",
     " wire dest_ok= (loading || OROW_WORDS==16 ? icb_cmd_wdata[5:0]==0 : icb_cmd_wdata[4:0]==0) &&\n"),
    (" wire [32:0] batch_last={1'b0,icb_cmd_wdata}+(({25'b0,block_remaining}>>4)-1)*33'd1024+33'd63;\n",
     " wire [32:0] batch_rows={25'b0,block_remaining}>>(OROW_WORDS==16 ? 4 : 3);\n"
     " wire [32:0] batch_last={1'b0,icb_cmd_wdata}+(batch_rows-1)*OROW_BYTES+(OROW_WORDS*4-1);\n"
     " wire batch_row_multiple = OROW_WORDS==16 ? block_remaining[3:0]==0 : block_remaining[2:0]==0;\n"
     " wire row_last_word = OROW_WORDS==16 ? word_number[3:0]==15 : word_number[2:0]==7;\n"
     " wire [31:0] row_jump = OROW_BYTES[31:0]-(OROW_WORDS-1)*4;\n"),
    ("(!batch_cmd || (block_remaining[3:0]==0 && block_remaining!=0 && batch_last<33'h0a0080000))",
     "(!batch_cmd || (batch_row_multiple && block_remaining!=0 && batch_last<33'h0a0080000))"),
    (" wire [31:0] output_next_addr=dst_addr+(batch_block && word_number[3:0]==15 ? 32'd964 : 32'd4);\n",
     " wire [31:0] output_next_addr=dst_addr+(batch_block && row_last_word ? row_jump : 32'd4);\n"),
    ("dst_addr<=dst_addr+(batch_block && word_number[3:0]==15 ? 32'd964 : 32'd4);",
     "dst_addr<=dst_addr+(batch_block && row_last_word ? row_jump : 32'd4);"),
    ("transfer_words<=input_full_cmd ? 3168 : stage256_cmd ? 256 : batch_cmd ? block_remaining : 16;",
     "transfer_words<=input_full_cmd ? 3168 : stage256_cmd ? 256 : batch_cmd ? block_remaining : loading ? 16 : OROW_WORDS;"),
    (" qingyu_accel #(.LANES(16), .STREAM_MAC(1), .DOUBLE_BUFFER(1), .PIPE_MAC(1), .READ_AHEAD(1), .WEIGHT_STREAM(1)) u_accel(\n",
     "`ifdef QINGYU_OUT16\n"
     " qingyu_accel #(.LANES(16), .STREAM_MAC(1), .DOUBLE_BUFFER(1), .PIPE_MAC(1), .READ_AHEAD(1), .WEIGHT_STREAM(1), .OUT16(1)) u_accel(\n"
     "`else\n"
     " qingyu_accel #(.LANES(16), .STREAM_MAC(1), .DOUBLE_BUFFER(1), .PIPE_MAC(1), .READ_AHEAD(1), .WEIGHT_STREAM(1)) u_accel(\n"
     "`endif\n"),
])

edit(R / "qingyu_accel.h", [
    ("} qingyu_device;\n", "} qingyu_device;\n\n#ifdef QINGYU_OUT16\n/* Two INT16 results per 32-bit word, low column first. */\n"
     "typedef int16_t qingyu_out_t;\n#define QINGYU_OUT_PER_WORD 2u\n#define QINGYU_OUT_ALIGN_MASK 31u\n#else\n"
     "typedef int32_t qingyu_out_t;\n#define QINGYU_OUT_PER_WORD 1u\n#define QINGYU_OUT_ALIGN_MASK 63u\n#endif\n"),
    ("    int32_t *output;           /* [rows][cols], row major */",
     "    qingyu_out_t *output;      /* [rows][cols], row major */"),
])

edit(R / "qingyu_accel.c", [
    ("    size_t output_bytes = (size_t)QINGYU_ROWS * QINGYU_COLS * sizeof(int32_t);",
     "    size_t output_bytes = (size_t)QINGYU_ROWS * QINGYU_COLS * sizeof(qingyu_out_t);"),
    ("            if (count != rows*QINGYU_LANES) {",
     "            if (count != rows*QINGYU_LANES/QINGYU_OUT_PER_WORD) {"),
    ("            if (direct && ((uintptr_t)(job->output+first*QINGYU_COLS+column_base)&63u)==0 &&",
     "            if (direct && ((uintptr_t)(job->output+first*QINGYU_COLS+column_base)&QINGYU_OUT_ALIGN_MASK)==0 &&"),
    ("                int32_t *dst=job->output+(first+row)*QINGYU_COLS+column_base;",
     "                qingyu_out_t *dst=job->output+(first+row)*QINGYU_COLS+column_base;"),
    ("    qingyu_fence();\n    if (device->read_ticks != NULL) {\n        start_ticks = device->read_ticks(device->context);\n    }\n",
     "#ifdef QINGYU_OUT16\n    /* Packed INT16 results are only produced through the FIO batch path. */\n"
     "    if (device->read32 != NULL || device->write32 != NULL) {\n        return QINGYU_ERR_ARGUMENT;\n    }\n#endif\n"
     "    qingyu_fence();\n    if (device->read_ticks != NULL) {\n        start_ticks = device->read_ticks(device->context);\n    }\n"),
])

edit(R / "soc_perf_main.c", [
    ("    job.output = (int32_t *)(uintptr_t)0xa0010000u;", "    job.output = (qingyu_out_t *)(uintptr_t)0xa0010000u;"),
])

edit(T / "tb_qingyu_soc_performance.sv", [
    (" integer ticks=0,", "`ifdef QINGYU_OUT16\n localparam integer OUT_WORDS=12672, OUT_PER_WORD=2;\n"
     "`else\n localparam integer OUT_WORDS=25344, OUT_PER_WORD=1;\n`endif\n integer ticks=0,"),
    ("pending_addr >= 32'ha0010000 && pending_addr < 32'ha0028c00) begin",
     "pending_addr >= 32'ha0010000 && pending_addr < 32'ha0010000+4*OUT_WORDS) begin"),
    ("    outputs++;\n", "    outputs+=OUT_PER_WORD;\n"),
    ("     if(prefetched!=25344 || consumed!=25344)", "     if(prefetched!=OUT_WORDS || consumed!=OUT_WORDS)"),
    ("   if(end_tick<0 || outputs!=25344 || output_seen!={25344{1'b1}})",
     "   if(end_tick<0 || outputs!=25344 || !(&output_seen[OUT_WORDS-1:0]))"),
])

fx = T / "tb_qingyu_soc.sv"
edit(fx, [
    ("   for(i=0;i<25344;i=i+1) begin\n",
     "`ifdef QINGYU_OUT16\n   for(i=0;i<12672;i=i+1) begin  // 25344 INT16 results, two per word\n"
     "`else\n   for(i=0;i<25344;i=i+1) begin\n`endif\n"),
])
print("OUT16 applied to", EXP)
