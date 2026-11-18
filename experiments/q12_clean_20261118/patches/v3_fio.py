R = [
 (""" output wire shared_cache_clear,""",
  """ output wire shared_cache_clear,
 input wire [31:0] hw_acked_words, // peripheral-DMA stores acknowledged by the System Bus"""),
 (""" reg completed,failed;reg [7:0] failure_code;""",
  """ reg completed,failed;reg [7:0] failure_code;
 reg hw_publish;"""),
 ("""  .commit_valid(commit_send_pending),.commit_ready(engine_commit_ready),""",
  """  .hw_commit_enable(hw_publish),.hw_commit_words(hw_acked_words),
  .commit_valid(commit_send_pending),.commit_ready(engine_commit_ready),"""),
 ("""   completed<=0;failed<=0;failure_code<=0;host_valid<=0;host_code<=0;""",
  """   completed<=0;failed<=0;failure_code<=0;host_valid<=0;host_code<=0;hw_publish<=0;"""),
 ("""      8'h40:response_data<=commit_epoch_q;""",
  """      8'h40:response_data<=commit_epoch_q;
      8'h44:response_data<={31'b0,hw_publish};"""),
 ("""      8'h40:commit_epoch_q<=icb_cmd_wdata;""",
  """      8'h40:commit_epoch_q<=icb_cmd_wdata;
      8'h44:if(engine_busy)response_error<=1;else hw_publish<=icb_cmd_wdata[0];"""),
]
