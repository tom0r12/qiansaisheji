import sys
f = sys.argv[1] if len(sys.argv) > 1 else ''
R = [
 ("rd_word_data!=32'h32583151", "rd_word_data!=32'h32573151"),
 ("(header_index>=2 && header_index<=9 && rd_word_data!=32'd24576)", "(header_index>=2 && header_index<=9 && rd_word_data!=32'd20480)"),
 ("start_total_words!=32'd8850", "start_total_words!=32'd7826"),
]
