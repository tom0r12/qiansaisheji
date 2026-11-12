`timescale 1ns/1ps
`default_nettype none
// Shared SRAM slave with explicitly cleared, coherent adjacent-word read-ahead.
module qingyu_shared_sram (
 input wire clk, rst_n, cache_clear,
 input wire icb_cmd_valid, output wire icb_cmd_ready,
 input wire icb_cmd_read, input wire [31:0] icb_cmd_addr, icb_cmd_wdata,
 input wire [3:0] icb_cmd_wmask,
 output wire icb_rsp_valid, input wire icb_rsp_ready,
 output wire [31:0] icb_rsp_rdata, output wire icb_rsp_err
);
 wire ram_cs,ram_we;
 wire [16:0] ram_addr;
 wire [31:0] ram_wdata,ram_rdata;
 wire [3:0] ram_wmask;
 qingyu_shared_read_ahead u_cache(
  .clk(clk),.rst_n(rst_n),.cache_clear(cache_clear),
  .icb_cmd_valid(icb_cmd_valid),.icb_cmd_ready(icb_cmd_ready),
  // Preserve the platform byte-address convention; byte lanes are in wmask.
  .icb_cmd_read(icb_cmd_read),.icb_cmd_addr({icb_cmd_addr[31:2],2'b00}),
  .icb_cmd_wdata(icb_cmd_wdata),.icb_cmd_wmask(icb_cmd_wmask),
  .icb_rsp_valid(icb_rsp_valid),.icb_rsp_ready(icb_rsp_ready),
  .icb_rsp_rdata(icb_rsp_rdata),.icb_rsp_err(icb_rsp_err),
  .ram_cs(ram_cs),.ram_we(ram_we),.ram_addr(ram_addr),
  .ram_wdata(ram_wdata),.ram_wmask(ram_wmask),.ram_rdata(ram_rdata)
 );
 reg [31:0] mem [0:131071];
 reg [31:0] ram_q;
 assign ram_rdata=ram_q;
 integer b;
 always @(posedge clk) if(ram_cs) begin
  if(!ram_we) ram_q<=mem[ram_addr];
  else begin
   for(b=0;b<4;b=b+1)
    if(ram_wmask[b])mem[ram_addr][8*b+:8]<=ram_wdata[8*b+:8];
   ram_q<=32'bx; // Avoid relying on memory output retention during writes.
  end
 end
endmodule
`default_nettype wire

// Controller source, identical to the standalone verified prototype.
`timescale 1ns/1ps
`default_nettype none
// Experimental ICB slave controller for a synchronous 512 KiB, 32-bit SRAM.
// All architectural reads/writes still handshake at the original bus port.
// The extra SRAM reads are speculative adjacent-word reads, never writes.
// One registered cache entry plus the current macro-Q prefetch are retained.
module qingyu_shared_read_ahead (
 input wire clk, rst_n,
 input wire cache_clear,
 input wire icb_cmd_valid,
 output wire icb_cmd_ready,
 input wire icb_cmd_read,
 input wire [31:0] icb_cmd_addr, icb_cmd_wdata,
 input wire [3:0] icb_cmd_wmask,
 output wire icb_rsp_valid,
 input wire icb_rsp_ready,
 output wire [31:0] icb_rsp_rdata,
 output wire icb_rsp_err,
 output reg ram_cs, ram_we,
 output reg [16:0] ram_addr,
 output wire [31:0] ram_wdata,
 output wire [3:0] ram_wmask,
 input wire [31:0] ram_rdata
);
 wire good = icb_cmd_addr[31:19] == 13'h1400 && icb_cmd_addr[1:0] == 2'b00;
 wire [16:0] word_addr = icb_cmd_addr[18:2];
 reg cache_valid, look_valid;
 reg [16:0] cache_addr, look_addr;
 reg [31:0] cache_data;
 reg response_pending, response_from_ram;
 reg [31:0] response_data;
 reg response_error;
 reg [16:0] response_addr;
 reg response_prefetch_allowed;

 wire look_hit = look_valid && look_addr == word_addr;
 wire cache_hit = cache_valid && cache_addr == word_addr;
 wire read_hit = good && (look_hit || cache_hit);
 wire [31:0] hit_data = look_hit ? ram_rdata : cache_data;
 wire immediate = !icb_cmd_read || !good || read_hit;
 // A hit/write may be accepted even when the response is stalled. In that
 // case it becomes an ordinary held response on the next cycle, with the
 // exact same data and error bit. No second command is accepted meanwhile.
 assign icb_cmd_ready = rst_n && !cache_clear && !response_pending;
 assign icb_rsp_valid = rst_n && (response_pending ||
                        (!cache_clear && icb_cmd_valid && immediate));
 assign icb_rsp_rdata = response_pending ?
                       (response_from_ram ? ram_rdata : response_data) :
                       (icb_cmd_read && read_hit ? hit_data : 32'b0);
 assign icb_rsp_err = response_pending ? response_error : !good;
 wire accept = icb_cmd_valid && icb_cmd_ready;
 wire retire = response_pending && icb_rsp_ready;
 assign ram_wdata = icb_cmd_wdata;
 assign ram_wmask = icb_cmd_wmask;
 reg speculative_read;

 always @* begin
  ram_cs = 1'b0;
  ram_we = 1'b0;
  ram_addr = word_addr;
  speculative_read = 1'b0;
  if (rst_n && !cache_clear) begin
   if (retire && response_from_ram && response_prefetch_allowed &&
       response_addr != 17'h1ffff) begin
    // The retiring read is sampled before the macro Q changes at this edge.
    ram_cs = 1'b1;
    ram_addr = response_addr + 17'd1;
    speculative_read = 1'b1;
   end else if (accept && good) begin
    if (!icb_cmd_read) begin
     ram_cs = 1'b1;
     ram_we = 1'b1;
    end else if (!read_hit) begin
     ram_cs = 1'b1;
    end else if (word_addr != 17'h1ffff) begin
     ram_cs = 1'b1;
     ram_addr = word_addr + 17'd1;
     speculative_read = 1'b1;
    end
   end
  end
 end

 always @(posedge clk) begin
  if (!rst_n) begin
   cache_valid <= 1'b0;
   look_valid <= 1'b0;
   cache_addr <= 0;
   look_addr <= 0;
   cache_data <= 0;
   response_pending <= 1'b0;
   response_from_ram <= 1'b0;
   response_data <= 0;
   response_error <= 1'b0;
   response_addr <= 0;
   response_prefetch_allowed <= 1'b0;
  end else begin
   // Preserve the old macro output BEFORE any read or write can replace it.
   // This is required even for writes to an unrelated bank: write-Q behavior
   // is not assumed to be defined by the manufacturer memory model.
   if (look_valid) begin
    cache_valid <= 1'b1;
    cache_addr <= look_addr;
    cache_data <= ram_rdata;
   end
   if (ram_cs) begin
    look_valid <= speculative_read;
    look_addr <= ram_addr;
   end
   if (retire) begin
    response_pending <= 1'b0;
    if (response_from_ram && response_prefetch_allowed) begin
     cache_valid <= 1'b1;
     cache_addr <= response_addr;
     cache_data <= ram_rdata;
    end
   end
   if (accept) begin
    response_addr <= word_addr;
    response_error <= !good;
    response_from_ram <= icb_cmd_read && good && !read_hit;
    response_prefetch_allowed <= icb_cmd_read && good && !read_hit;
    response_data <= icb_cmd_read && read_hit ? hit_data : 32'b0;
    response_pending <= !immediate || !icb_rsp_ready;
    if (!icb_cmd_read && good) begin
     // Invalidate the value being retained, including a prefetch that became
     // visible on this very cycle. The write commits exactly at accept.
     if ((look_valid && look_addr == word_addr) ||
         (!look_valid && cache_valid && cache_addr == word_addr))
      cache_valid <= 1'b0;
    end
   end
   // Clearing caches must not discard an already accepted response. Prevent
   // an older outstanding miss from refilling the cache after the clear.
   if (cache_clear) begin
    cache_valid <= 1'b0;
    look_valid <= 1'b0;
    response_prefetch_allowed <= 1'b0;
   end
  end
 end
endmodule
`default_nettype wire
