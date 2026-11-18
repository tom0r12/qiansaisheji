R = [
 # gate: hardware-published prefix from the peripheral DMA's acknowledged count
 ("""    input wire commit_valid, output wire commit_ready,""",
  """    input wire hw_enable, input wire [31:0] hw_words,
    input wire commit_valid, output wire commit_ready,"""),
 ("""            if(commit_fire)begin""",
  """            // Hardware prefix: count of input-DMA stores whose write responses
            // have returned. Monotonic within a task; never beyond total.
            if(active && hw_enable && hw_words>available_words && hw_words<=total_words)
                available_words<=hw_words;
            if(commit_fire)begin"""),
]
