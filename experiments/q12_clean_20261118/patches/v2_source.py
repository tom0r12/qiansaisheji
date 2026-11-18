R = [
 ("module q12_gpio_source #(parameter integer WORDS=8873)(\n input wire req,input wire[4:0]count,input wire[5:0]oe,",
  "module q12_gpio_source #(parameter integer WORDS=8873)(\n input wire req,input wire[7:0]count,input wire[8:0]oe,"),
 ("wait(oe===6'b111111);", "wait(oe===9'h1ff);"),
 ("if(n<1||n>16||requested_words+n>input_words||oe!==6'b111111)", "if(n<1||n>255||requested_words+n>input_words||oe!==9'h1ff)"),
 ("if(req!==previous_req||count!==5'(n)||oe!==6'b111111)", "if(req!==previous_req||count!==8'(n)||oe!==9'h1ff)"),
 ("always @(oe)if(presented_words!=0&&oe!==6'b111111)", "always @(oe)if(presented_words!=0&&oe!==9'h1ff)"),
]
