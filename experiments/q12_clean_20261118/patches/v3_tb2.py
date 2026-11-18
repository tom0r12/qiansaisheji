R = [
 ("""   if(dut.u_fio.available_words<32'(observed_available)||dut.u_fio.available_words>32'(source_acked_prefix))""",
  """   if(`ENG.gate_available<32'(observed_available)||`ENG.gate_available>32'(source_acked_prefix)||
      dut.u_fio.available_words>32'(source_acked_prefix))"""),
 ("""   observed_available=int'(dut.u_fio.available_words);""",
  """   observed_available=int'(`ENG.gate_available);"""),
]
