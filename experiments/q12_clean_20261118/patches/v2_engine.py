R = [
 ("""  .clk(clk),.rst_n(rst_n),.soft_abort(abort_now || (state==ABORT_DRAIN && !abort_issued)),""",
  """  .clk(clk),.rst_n(rst_n),.soft_abort(abort_now || (state==ABORT_DRAIN && !abort_issued)),
  .rd_avail_end({3'b0,gate_source}+{1'b0,gate_available,2'b0}),"""),
]
