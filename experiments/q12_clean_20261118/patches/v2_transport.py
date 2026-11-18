R = [
 (" input wire clk,rst_n,soft_abort,\n", " input wire clk,rst_n,soft_abort,\n input wire [34:0] rd_avail_end, // published source prefix end (byte address)\n"),
 (" wire read_eligible=rd_active&&rd_issued<rd_total&&read_space;",
  " wire read_eligible=rd_active&&rd_issued<rd_total&&read_space&&\n                    (({3'b0,rd_base}+{1'b0,rd_issued,2'b0})<rd_avail_end);"),
]
