// System-bus endpoint. One outstanding response, including host notification.
module qingyu_fio (
 input wire clk, input wire rst_n,
`ifdef QINGYU_BLOCK_COPY
 input wire cpu_cmd_valid, cpu_cmd_read, cpu_rsp_ready,
 input wire [31:0] cpu_cmd_addr, cpu_cmd_wdata,
 input wire [3:0] cpu_cmd_wmask,
 output wire cpu_cmd_ready, cpu_rsp_valid, cpu_rsp_err,
 output wire [31:0] cpu_rsp_rdata,
 output wire mem_cmd_valid, mem_cmd_read, mem_rsp_ready,
 output wire [31:0] mem_cmd_addr, mem_cmd_wdata,
 output wire [3:0] mem_cmd_wmask,
 input wire mem_cmd_ready, mem_rsp_valid, mem_rsp_err,
 input wire [31:0] mem_rsp_rdata,
`endif
 input wire icb_cmd_valid, output wire icb_cmd_ready,
 input wire icb_cmd_read, input wire [31:0] icb_cmd_addr,
 input wire [31:0] icb_cmd_wdata, input wire [3:0] icb_cmd_wmask,
 output wire icb_rsp_valid, input wire icb_rsp_ready,
 output wire [31:0] icb_rsp_rdata, output wire icb_rsp_err,
 output reg host_valid, output reg [31:0] host_code
);
 reg pending, owner_accel, local_error;
 reg [31:0] local_data;
 wire select_accel = icb_cmd_addr[31:16] == 16'hf000;
 wire select_host = icb_cmd_addr == 32'hf0010000;
 wire acc_cmd_ready, acc_rsp_valid, acc_rsp_err;
 wire [31:0] acc_rsp_data;
`ifdef QINGYU_BLOCK_COPY
 // The E203 supplies one bounded 64-byte destination per command.
 localparam IDLE=0, READ_CMD=1, READ_RSP=2, WRITE_CMD=3, WRITE_RSP=4, INPUT_HI=5;
 reg [2:0] phase;
 reg [11:0] word_number;
 reg input_block, batch_block;
 reg [7:0] input_group;
 reg [12:0] transfer_words;
 wire [7:0] block_remaining;
 wire block_next_valid;
 wire [31:0] block_next_data;
 reg [31:0] dst_addr, loaded_word;
 reg load_block, transfer_error, cpu_outstanding;
 wire weight_load_ok;
 wire accel_busy;
 // Weight prefetch engine: reads the next tile's weights from the live bank
 // while the CPU keeps issuing output copies, so the transfer costs no CPU time.
 reg wl_busy, wl_wait, wl_tile;
 reg [9:0] wl_word;
 reg [31:0] wl_addr;
 reg [4:0] wl_pair;
 reg rsp_is_wl;
 wire wl_last;
 wire blk_rsp, wl_rsp, wl_req, wl_rsp_ok, blk_req;
 wire [31:0] blk_addr, blk_wdata, wl_addr_next;
 wire blk_read;
 wire weight_tile_cmd=icb_cmd_addr==32'hf0000080;
 wire weight_cmd=weight_tile_cmd || icb_cmd_addr[31:7]==(32'hf0000800>>7);
 wire input_full_cmd=icb_cmd_addr==32'hf0000090;
 wire stage256_cmd=icb_cmd_addr==32'hf0000084;
 wire input_cmd=input_full_cmd || icb_cmd_addr>=32'hf0000a00 && icb_cmd_addr<32'hf0000d18;
 wire batch_cmd=icb_cmd_addr==32'hf000003c || icb_cmd_addr==32'hf0000040;
 wire block_cmd=stage256_cmd || input_cmd || batch_cmd || icb_cmd_addr==32'hf0000030 || icb_cmd_addr==32'hf0000034 ||
                icb_cmd_addr==32'hf0000038 || weight_cmd;
 wire loading=stage256_cmd || icb_cmd_addr==32'hf0000038;
 wire block_valid, block_slot, block_has_row;
 wire [31:0] block_data;
 wire dest_ok= icb_cmd_wdata[5:0]==0 &&
              (loading ? (icb_cmd_wdata>=32'ha0000000 && icb_cmd_wdata<=32'ha003ffc0) :
                         (icb_cmd_wdata>=32'ha0000000 && icb_cmd_wdata<=32'ha007ffc0));
 // Each command reads eight words from each of two adjacent live W rows.
 // The last shared address is base + 512 + 28. Reject staging/out-of-range reads.
 wire weight_source_ok=icb_cmd_addr[1:0]==0 && icb_cmd_wdata[4:0]==0 &&
                       icb_cmd_wdata>=32'ha0000000 && icb_cmd_wdata<=32'ha003fde0;
 wire [32:0] batch_last={1'b0,icb_cmd_wdata}+(({25'b0,block_remaining}>>4)-1)*33'd1024+33'd63;
 wire legal_block=!icb_cmd_read && icb_cmd_wmask==4'hf &&
   (input_cmd ? weight_source_ok && !accel_busy && (!input_full_cmd || icb_cmd_wdata<=32'ha003ce80) :
    weight_cmd ? weight_source_ok && weight_load_ok && (!weight_tile_cmd || icb_cmd_wdata<=32'ha00381e0) :
    dest_ok && (loading ? (!stage256_cmd || icb_cmd_wdata<=32'ha003fc00) :
     block_has_row && block_slot==(batch_cmd ? icb_cmd_addr==32'hf0000040 : icb_cmd_addr[2]) &&
     (!batch_cmd || (block_remaining[3:0]==0 && block_remaining!=0 && batch_last<33'h0a0080000))));
 wire request_block=icb_cmd_valid && block_cmd && !pending;
 wire take_block=request_block && !cpu_outstanding;
 wire passthru=(phase==IDLE);
 wire acc_selected=select_accel && !block_cmd;
 assign icb_cmd_ready=!pending && (block_cmd ? (!cpu_outstanding && (!weight_cmd || !wl_busy)) :
                                   (!acc_selected || acc_cmd_ready) && (!wl_busy || icb_cmd_read));
 assign icb_rsp_valid=pending && (owner_accel ? acc_rsp_valid : passthru);
 assign cpu_cmd_ready=passthru && !request_block && mem_cmd_ready;
 assign cpu_rsp_valid=passthru && blk_rsp;
 assign cpu_rsp_rdata=mem_rsp_rdata;
 assign cpu_rsp_err=mem_rsp_err;
 // During a staging copy, a successful response can launch the next transfer
 // on the same edge. If the downstream port stalls we retain address/data
 // and reissue in READ_CMD or WRITE_CMD. Weight commands instead run on the
 // prefetch engine below so they never hold up the CPU's output copies.
 wire output_write_next = phase==WRITE_RSP && !load_block && word_number!=transfer_words-1 && blk_rsp && !mem_rsp_err && block_next_valid;
 wire [31:0] output_next_addr=dst_addr+(batch_block && word_number[3:0]==15 ? 32'd964 : 32'd4);
 wire input_read_next = phase==INPUT_HI && word_number!=transfer_words-1;
 wire stage_write_now = phase==READ_RSP && load_block && blk_rsp && !mem_rsp_err;
 wire stage_read_next = phase==WRITE_RSP && load_block && word_number!=transfer_words-1 && blk_rsp && !mem_rsp_err;
 assign blk_req = passthru ? cpu_cmd_valid && !request_block :
                  phase==READ_CMD || (phase==WRITE_CMD && (load_block || block_valid)) ||
                  stage_write_now || stage_read_next || input_read_next || output_write_next;
 assign blk_addr = passthru ? cpu_cmd_addr :
                  output_write_next ? output_next_addr : input_read_next ? dst_addr+4 :
                  stage_read_next ? dst_addr+32'h40004 :
                  phase==READ_CMD && !input_block ? dst_addr+32'h40000 : dst_addr;
 assign blk_read = passthru ? cpu_cmd_read : phase==READ_CMD || stage_read_next || input_read_next;
 assign blk_wdata = passthru ? cpu_cmd_wdata : stage_write_now ? mem_rsp_rdata :
                  load_block ? loaded_word : output_write_next ? block_next_data : block_data;
 // The prefetch engine takes every bus cycle the copy engine leaves idle.
 assign blk_rsp = mem_rsp_valid && !rsp_is_wl;
 assign wl_rsp = mem_rsp_valid && rsp_is_wl;
 assign wl_rsp_ok = wl_rsp && !mem_rsp_err;
 assign wl_last = wl_tile ? wl_word==10'd511 : wl_word==10'd15;
 // A request may launch in the same cycle its predecessor answers, in which
 // case the address must already be stepped.
 assign wl_addr_next = wl_addr+(wl_word[2:0]==7 ? 32'd484 : 32'd4);
 assign wl_req = wl_busy && (!wl_wait || (wl_rsp && !wl_last)) && !blk_req && rst_n;
 assign mem_cmd_valid = blk_req || wl_req;
 assign mem_cmd_addr = wl_req ? (wl_rsp ? wl_addr_next : wl_addr) : blk_addr;
 assign mem_cmd_read = wl_req ? 1'b1 : blk_read;
 assign mem_cmd_wmask = wl_req ? 4'hf : (passthru ? cpu_cmd_wmask : 4'hf);
 assign mem_cmd_wdata = wl_req ? 32'b0 : blk_wdata;
 assign mem_rsp_ready = rsp_is_wl ? 1'b1 : (passthru ? cpu_rsp_ready : phase==READ_RSP || phase==WRITE_RSP);
 wire block_pop=phase==WRITE_RSP && blk_rsp && !mem_rsp_err && !load_block;
 wire weight_write=rst_n && wl_rsp_ok;
 always @(posedge clk) begin
  if (!rst_n) begin
   phase<=IDLE; transfer_error<=0; cpu_outstanding<=0; load_block<=0;
   dst_addr<=0; word_number<=0; loaded_word<=0;
   input_block<=0; batch_block<=0; input_group<=0; transfer_words<=16;
  end else begin
   if (cpu_rsp_valid && cpu_rsp_ready) cpu_outstanding<=0;
   if (cpu_cmd_valid && cpu_cmd_ready) cpu_outstanding<=1;
   case (phase)
    IDLE: if (take_block) begin
     transfer_error<=!legal_block;
     if (legal_block && !weight_cmd) begin
      dst_addr<=icb_cmd_wdata; word_number<=0; load_block<=loading;
      input_block<=input_cmd; batch_block<=batch_cmd; input_group<=input_full_cmd ? 0 : (icb_cmd_addr-32'hf0000a00)>>2;
      transfer_words<=input_full_cmd ? 3168 : stage256_cmd ? 256 : batch_cmd ? block_remaining : 16;
      phase<=loading || input_cmd ? READ_CMD : WRITE_CMD;
     end
    end
    READ_CMD: if (blk_req && mem_cmd_ready) phase<=READ_RSP;
    READ_RSP: if (blk_rsp) begin
     loaded_word<=mem_rsp_rdata; transfer_error<=mem_rsp_err;
     if (input_block) phase<=mem_rsp_err ? IDLE : INPUT_HI;
     else phase<=mem_rsp_err ? IDLE : (stage_write_now && mem_cmd_ready ? WRITE_RSP : WRITE_CMD);
    end
    INPUT_HI: begin
     word_number<=word_number+1'b1; dst_addr<=dst_addr+4;
     phase<=word_number==transfer_words-1 ? IDLE : (mem_cmd_ready ? READ_RSP : READ_CMD);
    end
    WRITE_CMD: if (blk_req && mem_cmd_ready) phase<=WRITE_RSP;
    WRITE_RSP: if (blk_rsp) begin
     transfer_error<=mem_rsp_err; word_number<=word_number+1'b1; dst_addr<=dst_addr+(batch_block && word_number[3:0]==15 ? 32'd964 : 32'd4);
     if (mem_rsp_err || word_number==transfer_words-1) phase<=IDLE;
     else if (load_block) phase<=stage_read_next && mem_cmd_ready ? READ_RSP : READ_CMD;
     else phase<=output_write_next && mem_cmd_ready ? WRITE_RSP : WRITE_CMD;
    end
    default: phase<=IDLE;
   endcase
  end
 end
 // Independent weight prefetch: one shared-memory read per idle bus cycle,
 // written straight into the accelerator's idle W bank.
 always @(posedge clk) begin
  if (!rst_n) begin
   wl_busy<=0; wl_wait<=0; wl_word<=0; wl_addr<=0; wl_tile<=0; wl_pair<=0;
  end else begin
   if (take_block && weight_cmd && legal_block) begin
    wl_busy<=1; wl_wait<=0; wl_word<=0; wl_addr<=icb_cmd_wdata;
    wl_tile<=weight_tile_cmd; wl_pair<=icb_cmd_addr[6:2];
   end
   if (wl_rsp) begin
    wl_wait<=0;
    wl_word<=wl_word+10'd1;
    wl_addr<=wl_addr_next;
    if (mem_rsp_err || wl_last) wl_busy<=0;
   end
   if (wl_req && mem_cmd_ready) wl_wait<=1;
  end
 end
 always @(posedge clk)
  if (!rst_n) rsp_is_wl<=0;
  else if (mem_cmd_valid && mem_cmd_ready) rsp_is_wl<=wl_req;
 reg owner_block;
 always @(posedge clk)
  if (!rst_n) owner_block<=0;
  else if (icb_cmd_valid && icb_cmd_ready) owner_block<=block_cmd;
`else
 wire acc_selected=select_accel;
 assign icb_cmd_ready = !pending && (select_accel ? acc_cmd_ready : 1'b1);
 assign icb_rsp_valid = pending && (owner_accel ? acc_rsp_valid : 1'b1);
`endif
 assign icb_rsp_rdata = owner_accel ? acc_rsp_data : local_data;
`ifdef QINGYU_BLOCK_COPY
 assign icb_rsp_err = owner_block ? transfer_error : owner_accel ? acc_rsp_err : local_error;
`else
 assign icb_rsp_err = owner_accel ? acc_rsp_err : local_error;
`endif
 `ifdef QINGYU_READ_AHEAD
 qingyu_accel #(.LANES(16), .STREAM_MAC(1), .DOUBLE_BUFFER(1), .PIPE_MAC(1), .READ_AHEAD(1), .WEIGHT_STREAM(1)) u_accel(
 `elsif QINGYU_PIPE_MAC
 qingyu_accel #(.LANES(16), .STREAM_MAC(1), .DOUBLE_BUFFER(1), .PIPE_MAC(1)) u_accel(
 `elsif QINGYU_DOUBLE_BUFFER
 qingyu_accel #(.LANES(16), .STREAM_MAC(1), .DOUBLE_BUFFER(1)) u_accel(
 `elsif QINGYU_FAST_TASK
 qingyu_accel #(.LANES(16), .STREAM_MAC(1)) u_accel(
 `else
 qingyu_accel u_accel(
 `endif
  .clk(clk), .rst_n(rst_n),
  `ifdef QINGYU_BLOCK_COPY
  .input_write(rst_n && input_block && ((phase==READ_RSP && blk_rsp && !mem_rsp_err) || phase==INPUT_HI)),
  .input_elem({input_group,5'b0}+{word_number,1'b0}+(phase==INPUT_HI)),
  .input_data(phase==INPUT_HI ? loaded_word[31:16] : mem_rsp_rdata[15:0]),
  .block_next_valid(block_next_valid), .block_next_data(block_next_data), .block_remaining(block_remaining), .block_pop(block_pop), .block_valid(block_valid), .block_slot(block_slot),
  .block_has_row(block_has_row), .block_data(block_data),
  .weight_load_ok(weight_load_ok), .weight_write(weight_write), .weight_pair(wl_word[2:0]),
  .weight_k(wl_tile ? wl_word[8:3] : {wl_pair,wl_word[3]}), .weight_word(mem_rsp_rdata),
`endif
  .accel_busy(accel_busy),
  // The accelerator may only see a command the FIO actually accepted; the
  // prefetch gate must therefore also mask icb_cmd_valid, not just readiness.
  .icb_cmd_valid(icb_cmd_valid && !pending && acc_selected && (!wl_busy || icb_cmd_read)),
  .icb_cmd_ready(acc_cmd_ready), .icb_cmd_read(icb_cmd_read),
  .icb_cmd_addr(icb_cmd_addr[15:0]), .icb_cmd_wdata(icb_cmd_wdata),
  .icb_cmd_wmask(icb_cmd_wmask), .icb_rsp_valid(acc_rsp_valid),
  .icb_rsp_ready(pending && owner_accel && icb_rsp_ready),
  .icb_rsp_rdata(acc_rsp_data), .icb_rsp_err(acc_rsp_err)
 );
 always @(posedge clk) begin
  if (!rst_n) begin
   pending<=0; owner_accel<=0; local_error<=0; local_data<=0;
   host_valid<=0; host_code<=0;
  end else begin
   host_valid<=0;
   if (icb_rsp_valid && icb_rsp_ready) pending<=0;
   if (icb_cmd_valid && icb_cmd_ready) begin
    pending<=1; owner_accel<=acc_selected;
    local_error<=!select_host || (icb_cmd_addr[1:0]!=0) ||
                 (!icb_cmd_read && icb_cmd_wmask!=4'hf);
    local_data<=host_code;
    if (select_host && !icb_cmd_read && icb_cmd_wmask==4'hf) begin
     host_code<=icb_cmd_wdata; host_valid<=1;
    end
   end
  end
 end
endmodule
