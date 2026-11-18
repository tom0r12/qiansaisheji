R = [
 (""" output wire ppi_lock
);""", """ output wire ppi_lock,
 output wire [13:0] acked_words
);"""),
 (""" assign ppi_lock=busy;""", """ assign ppi_lock=busy;
 assign acked_words=mem_responses;"""),
]
