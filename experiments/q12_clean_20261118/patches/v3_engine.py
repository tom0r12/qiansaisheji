R = [
 (""" input wire commit_valid,output wire commit_ready,""",
  """ input wire hw_commit_enable,input wire [31:0] hw_commit_words,
 input wire commit_valid,output wire commit_ready,"""),
 ("""  .commit_valid(commit_valid),.commit_ready(commit_ready),""",
  """  .hw_enable(hw_commit_enable),.hw_words(hw_commit_words),
  .commit_valid(commit_valid),.commit_ready(commit_ready),"""),
]
