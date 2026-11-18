`timescale 1ns/1ps
`default_nettype none
module q12_striped_sram #(parameter WIDTH=32, DEPTH=128, ADDR_W=$clog2(DEPTH))(
 input wire clk,en,we,input wire [ADDR_W-1:0] addr,
 input wire [WIDTH-1:0] wdata,wmask,output wire [WIDTH-1:0] rdata
);
`ifdef SYNTHESIS
`ifndef Q12_USE_VENDOR_MACROS
 Q12_REQUIRE_VENDOR_MACROS_FOR_SYNTHESIS missing_explicit_macro_mode();
`endif
`endif
 localparam N=(WIDTH+15)/16;
 wire [N*16-1:0] padded_data={{(N*16-WIDTH){1'b0}},wdata};
 wire [N*16-1:0] padded_mask={{(N*16-WIDTH){1'b0}},wmask};
 wire [N*16-1:0] q;
 assign rdata=q[WIDTH-1:0];
 if(N*16>WIDTH)begin: unused_top_padding
  wire unused_padding = ^q[N*16-1:WIDTH];
 end
 for(genvar n=0;n<N;n=n+1)begin: stripe
  wire enable=en && (!we || |padded_mask[n*16+:16]);
`ifdef Q12_USE_VENDOR_MACROS
  if(DEPTH==128 && ADDR_W==7)begin:g128
   RAMSP128X16 macro_ram(.CLK(clk),.CEN(~enable),.GWEN(~we),.WEN(~padded_mask[n*16+:16]),.A(addr),.D(padded_data[n*16+:16]),.Q(q[n*16+:16]),.EMA(3'b010),.EMAW(2'b00),.RET1N(1'b1));
  end else if(DEPTH==1024 && ADDR_W==10)begin:g1024
   RAMSP1024X16 macro_ram(.CLK(clk),.CEN(~enable),.GWEN(~we),.WEN(~padded_mask[n*16+:16]),.A(addr),.D(padded_data[n*16+:16]),.Q(q[n*16+:16]),.EMA(3'b010),.EMAW(2'b00),.RET1N(1'b1));
  end else begin:g_bad
   Q12_UNSUPPORTED_MACRO_GEOMETRY invalid();
  end
`else
  reg [15:0] mem[0:DEPTH-1];reg [15:0] qreg;
  assign q[n*16+:16]=qreg;
  always @(posedge clk) if(enable)begin
   if(we)begin
    for(integer bitno=0;bitno<16;bitno=bitno+1)if(padded_mask[n*16+bitno])mem[addr][bitno]<=padded_data[n*16+bitno];
   end else qreg<=mem[addr];
  end
`endif
 end
endmodule
`default_nettype wire
