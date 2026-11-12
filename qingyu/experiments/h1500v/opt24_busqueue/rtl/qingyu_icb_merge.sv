`default_nettype none
// Fair 32-bit ICB merger. All ports share clk and synchronous active-low reset.
// Response owners are queued in acceptance order. The downstream slave must
// return responses in order, with nonzero latency. A full queue may pop/push
// on the same edge. ONE_PER_PORT limits selected sources to one in-flight beat.
// A blocked output command is captured so later contenders cannot change it.
module qingyu_icb_merge #(
 parameter integer NP = 2,
 parameter integer OUTSTANDING = 4,
 parameter [NP-1:0] ONE_PER_PORT = {NP{1'b1}}
) (
 input wire clk, rst_n,
 input wire [NP-1:0] s_cmd_valid, s_cmd_read,
 output reg [NP-1:0] s_cmd_ready,
 input wire [32*NP-1:0] s_cmd_addr, s_cmd_wdata,
 input wire [4*NP-1:0] s_cmd_wmask,
 output reg [NP-1:0] s_rsp_valid,
 input wire [NP-1:0] s_rsp_ready,
 output wire [NP-1:0] s_rsp_err,
 output wire [32*NP-1:0] s_rsp_rdata,
 output wire m_cmd_valid,
 input wire m_cmd_ready,
 output wire m_cmd_read,
 output wire [31:0] m_cmd_addr, m_cmd_wdata,
 output wire [3:0] m_cmd_wmask,
 input wire m_rsp_valid,
 output wire m_rsp_ready,
 input wire m_rsp_err,
 input wire [31:0] m_rsp_rdata
);
 localparam integer PTR_W = NP > 1 ? $clog2(NP) : 1;
 localparam integer QUEUE_PTR_W = OUTSTANDING > 1 ? $clog2(OUTSTANDING) : 1;
 localparam integer COUNT_W = $clog2(OUTSTANDING+1);
 reg [PTR_W-1:0] next_q, lock_owner_q;
 reg [PTR_W-1:0] owner_fifo [0:OUTSTANDING-1];
 reg [QUEUE_PTR_W-1:0] read_ptr_q, write_ptr_q;
 reg [COUNT_W-1:0] count_q;
 reg [NP-1:0] active_q;
 wire pending_q = count_q != 0;
 wire [PTR_W-1:0] owner_q = owner_fifo[read_ptr_q];
 reg locked_q;
 reg lock_read_q;
 reg [31:0] lock_addr_q, lock_wdata_q;
 reg [3:0] lock_wmask_q;
 reg found;
 reg [PTR_W-1:0] grant;
 integer offset, index, reset_index;

 assign m_rsp_ready = rst_n && pending_q && s_rsp_ready[owner_q];
 wire rsp_fire = m_rsp_valid && m_rsp_ready;
 wire can_issue = count_q < COUNT_W'(OUTSTANDING) || rsp_fire;
 always @* begin
  found = 1'b0;
  grant = {PTR_W{1'b0}};
  index = 0;
  for (offset=0; offset<NP; offset=offset+1) begin
   index = int'(next_q) + offset;
   if (index >= NP) index = index - NP;
   if (!found && s_cmd_valid[index] &&
       (!ONE_PER_PORT[index] || !active_q[index] ||
        (rsp_fire && owner_q == PTR_W'(index)))) begin
    found = 1'b1;
    grant = PTR_W'(index);
   end
  end
  if (locked_q) begin
   found = 1'b1;
   grant = lock_owner_q;
  end
 end
 assign m_cmd_valid = rst_n && can_issue && found;
 assign m_cmd_read = locked_q ? lock_read_q : s_cmd_read[grant];
 assign m_cmd_addr = locked_q ? lock_addr_q : s_cmd_addr[32*grant+:32];
 assign m_cmd_wdata = locked_q ? lock_wdata_q : s_cmd_wdata[32*grant+:32];
 assign m_cmd_wmask = locked_q ? lock_wmask_q : s_cmd_wmask[4*grant+:4];
 wire cmd_fire = m_cmd_valid && m_cmd_ready;
 always @* begin
  s_cmd_ready = {NP{1'b0}};
  s_rsp_valid = {NP{1'b0}};
  if (m_cmd_valid) s_cmd_ready[grant] = m_cmd_ready;
  if (rst_n && pending_q) s_rsp_valid[owner_q] = m_rsp_valid;
 end
 assign s_rsp_err = {NP{m_rsp_err}};
 assign s_rsp_rdata = {NP{m_rsp_rdata}};

 always @(posedge clk) begin
  if (!rst_n) begin
   next_q <= 0; lock_owner_q <= 0;
   read_ptr_q <= 0; write_ptr_q <= 0; count_q <= 0; active_q <= 0; locked_q <= 0;
   for (reset_index=0; reset_index<OUTSTANDING; reset_index=reset_index+1)
    owner_fifo[reset_index] <= 0;
   lock_read_q <= 0; lock_addr_q <= 0; lock_wdata_q <= 0; lock_wmask_q <= 0;
  end else begin
   case ({cmd_fire,rsp_fire})
    2'b10: count_q <= count_q + 1'b1;
    2'b01: count_q <= count_q - 1'b1;
    default: begin end
   endcase
   if (rsp_fire) begin
    read_ptr_q <= read_ptr_q == QUEUE_PTR_W'(OUTSTANDING-1) ?
                  {QUEUE_PTR_W{1'b0}} : read_ptr_q + 1'b1;
    if (ONE_PER_PORT[owner_q]) active_q[owner_q] <= 1'b0;
   end
   if (cmd_fire) begin
    owner_fifo[write_ptr_q] <= grant;
    write_ptr_q <= write_ptr_q == QUEUE_PTR_W'(OUTSTANDING-1) ?
                   {QUEUE_PTR_W{1'b0}} : write_ptr_q + 1'b1;
    if (ONE_PER_PORT[grant]) active_q[grant] <= 1'b1;
    next_q <= grant == PTR_W'(NP-1) ? {PTR_W{1'b0}} : grant + 1'b1;
    locked_q <= 1'b0;
   end else if (m_cmd_valid && !locked_q) begin
    locked_q <= 1'b1;
    lock_owner_q <= grant;
    lock_read_q <= m_cmd_read;
    lock_addr_q <= m_cmd_addr;
    lock_wdata_q <= m_cmd_wdata;
    lock_wmask_q <= m_cmd_wmask;
   end
  end
 end
endmodule
`default_nettype wire
