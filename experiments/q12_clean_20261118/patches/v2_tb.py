R = [
 (".req(gpio_b_out[1]),.count(gpio_b_out[6:2]),.oe(gpio_b_oe[6:1]),",
  ".req(gpio_b_out[1]),.count(gpio_b_out[9:2]),.oe(gpio_b_oe[9:1]),"),
 ("""    if(start_cycle>=0||publish_commands!=1||dut.u_fio.source_words!=input_words||
       source_acked_prefix<(serial_load?input_words:boundaries[0])||
       dut.u_fio.available_words!=(serial_load?input_words:boundaries[0]))""",
  """    if(start_cycle>=0||publish_commands<1||dut.u_fio.source_words!=input_words||
       dut.u_fio.available_words<10||dut.u_fio.available_words>32'(source_acked_prefix))"""),
 ("""    if(full_start<0||publish_commands>=(serial_load?1:9)||
       dut.sysfio_icb_cmd_wdata!=32'(serial_load?input_words:boundaries[publish_commands])||""",
  """    if(full_start<0||publish_commands>=LEDGER||dut.sysfio_icb_cmd_wdata>32'(input_words)||
       dut.sysfio_icb_cmd_wdata<32'(observed_available)||"""),
 ("gpio_requested-gpio_word_responses>16)", "gpio_word_responses-source_writes>16)"),
 ("gpio_b_oe!=126))", "gpio_b_oe!=32'h3fe))"),
 ("""    if(source_acked_prefix!=input_words||publish_commands!=(serial_load?1:9)||
       commit_responses!=(serial_load?0:8)||observed_available!=input_words)""",
  """    if(source_acked_prefix!=input_words||publish_commands<2||
       commit_responses!=publish_commands-1||observed_available!=input_words)"""),
]
