R = [
 ("""    if(start_cycle>=0||publish_commands<1||dut.u_fio.source_words!=input_words||
       dut.u_fio.available_words<10||dut.u_fio.available_words>32'(source_acked_prefix))""",
  """    if(start_cycle>=0||dut.u_fio.source_words!=input_words||
       dut.u_fio.available_words>32'(source_acked_prefix))"""),
 ("""    if(source_acked_prefix!=input_words||publish_commands<2||
       commit_responses!=publish_commands-1||observed_available!=input_words)""",
  """    if(source_acked_prefix!=input_words||(publish_commands!=0&&commit_responses!=publish_commands-1)||
       observed_available!=input_words)"""),
]
