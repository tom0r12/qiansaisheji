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
 localparam IDLE=0, READ_CMD=1, READ_RSP=2, WRITE_CMD=3, WRITE_RSP=4;
 reg [2:0] phase;
 reg [3:0] word_number;
 reg [31:0] dst_addr, loaded_word;
 reg load_block, transfer_error, cpu_outstanding;
 reg weight_block;
 reg [4:0] weight_row_pair;
 wire weight_load_ok;
 wire weight_cmd=icb_cmd_addr[31:7]==(32'hf0000800>>7);
 wire block_cmd=icb_cmd_addr==32'hf0000030 || icb_cmd_addr==32'hf0000034 ||
                icb_cmd_addr==32'hf0000038 || weight_cmd;
 wire loading=icb_cmd_addr==32'hf0000038;
 wire block_valid, block_slot, block_has_row;
 wire [31:0] block_data;
 wire dest_ok= icb_cmd_wdata[5:0]==0 &&
              (loading ? (icb_cmd_wdata>=32'ha0000000 && icb_cmd_wdata<=32'ha003ffc0) :
                         (icb_cmd_wdata>=32'ha0000000 && icb_cmd_wdata<=32'ha007ffc0));
 // Each command reads eight words from each of two adjacent live W rows.
 // The last shared address is base + 512 + 28. Reject staging/out-of-range reads.
 wire weight_source_ok=icb_cmd_addr[1:0]==0 && icb_cmd_wdata[4:0]==0 &&
                       icb_cmd_wdata>=32'ha0000000 && icb_cmd_wdata<=32'ha003fde0;
 wire legal_block=!icb_cmd_read && icb_cmd_wmask==4'hf &&
                  (weight_cmd ? weight_source_ok && weight_load_ok :
                   dest_ok && (loading || (block_has_row && block_slot==icb_cmd_addr[2])));
 wire request_block=icb_cmd_valid && block_cmd && !pending;
 wire take_block=request_block && !cpu_outstanding;
 wire passthru=(phase==IDLE);
 wire acc_selected=select_accel && !block_cmd;
 assign icb_cmd_ready=!pending && (block_cmd ? !cpu_outstanding : !acc_selected || acc_cmd_ready);
 assign icb_rsp_valid=pending && (owner_accel ? acc_rsp_valid : passthru);
 assign cpu_cmd_ready=passthru && !request_block && mem_cmd_ready;
 assign cpu_rsp_valid=passthru && mem_rsp_valid;
 assign cpu_rsp_rdata=mem_rsp_rdata;
 assign cpu_rsp_err=mem_rsp_err;
 // During a staging copy, a successful response can launch the next transfer
 // on the same edge. If the downstream port stalls we retain address/data
 // and reissue in READ_CMD or WRITE_CMD. Weight commands keep their own path.
 wire stage_write_now = phase==READ_RSP && load_block && mem_rsp_valid && !mem_rsp_err;
 wire stage_read_next = phase==WRITE_RSP && load_block && word_number!=15 && mem_rsp_valid && !mem_rsp_err;
 assign mem_cmd_valid=passthru ? cpu_cmd_valid && !request_block :
                      phase==READ_CMD || (phase==WRITE_CMD && (load_block || block_valid)) || stage_write_now || stage_read_next;
 assign mem_cmd_addr=passthru ? cpu_cmd_addr :
                     stage_read_next ? dst_addr+32'h40004 :
                     phase==READ_CMD && !weight_block ? dst_addr+32'h40000 : dst_addr;
 assign mem_cmd_read=passthru ? cpu_cmd_read : phase==READ_CMD || stage_read_next;
 assign mem_cmd_wmask=passthru ? cpu_cmd_wmask : 4'hf;
 assign mem_cmd_wdata=passthru ? cpu_cmd_wdata : stage_write_now ? mem_rsp_rdata :
                      load_block ? loaded_word : block_data;
 assign mem_rsp_ready=passthru ? cpu_rsp_ready : phase==READ_RSP || phase==WRITE_RSP;
 wire block_pop=phase==WRITE_RSP && mem_rsp_valid && !mem_rsp_err && !load_block;
 wire weight_write=rst_n && weight_block && phase==READ_RSP && mem_rsp_valid && !mem_rsp_err;
 always @(posedge clk) begin
  if (!rst_n) begin
   phase<=IDLE; transfer_error<=0; cpu_outstanding<=0; load_block<=0;
   dst_addr<=0; word_number<=0; loaded_word<=0;
   weight_block<=0; weight_row_pair<=0;
  end else begin
   if (cpu_rsp_valid && cpu_rsp_ready) cpu_outstanding<=0;
   if (cpu_cmd_valid && cpu_cmd_ready) cpu_outstanding<=1;
   case (phase)
    IDLE: if (take_block) begin
     transfer_error<=!legal_block;
     if (legal_block) begin
      dst_addr<=icb_cmd_wdata; word_number<=0; load_block<=loading;
      weight_block<=weight_cmd; weight_row_pair<=icb_cmd_addr[6:2];
      phase<=loading || weight_cmd ? READ_CMD : WRITE_CMD;
     end
    end
    READ_CMD: if (mem_cmd_valid && mem_cmd_ready) phase<=READ_RSP;
    READ_RSP: if (mem_rsp_valid) begin
     loaded_word<=mem_rsp_rdata; transfer_error<=mem_rsp_err;
     if (weight_block) begin
      word_number<=word_number+1'b1;
      dst_addr<=dst_addr+(word_number==7 ? 32'd484 : 32'd4);
      phase<=mem_rsp_err || word_number==15 ? IDLE : READ_CMD;
     end else phase<=mem_rsp_err ? IDLE : (stage_write_now && mem_cmd_ready ? WRITE_RSP : WRITE_CMD);
    end
    WRITE_CMD: if (mem_cmd_valid && mem_cmd_ready) phase<=WRITE_RSP;
    WRITE_RSP: if (mem_rsp_valid) begin
     transfer_error<=mem_rsp_err; word_number<=word_number+1'b1; dst_addr<=dst_addr+4;
     if (mem_rsp_err || word_number==15) phase<=IDLE;
     else if (load_block) phase<=stage_read_next && mem_cmd_ready ? READ_RSP : READ_CMD;
     else phase<=WRITE_CMD;
    end
    default: phase<=IDLE;
   endcase
  end
 end
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
  .block_pop(block_pop), .block_valid(block_valid), .block_slot(block_slot),
  .block_has_row(block_has_row), .block_data(block_data),
  .weight_load_ok(weight_load_ok), .weight_write(weight_write), .weight_pair(word_number[2:0]),
  .weight_k({weight_row_pair,word_number[3]}), .weight_word(mem_rsp_rdata),
`endif
  .icb_cmd_valid(icb_cmd_valid && !pending && acc_selected),
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
