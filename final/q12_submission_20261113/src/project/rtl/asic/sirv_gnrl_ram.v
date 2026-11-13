// Project-specific macro adapter for the E203 ITCM/DTCM ports.
// Replaces vendor/e203_hbirdv2/rtl/e203/general/sirv_gnrl_ram.v in ASIC builds.
// No ECC, sleep, retention or unknown-to-zero simulation behavior is added.
// The original functional model also ignored sd/ds/ls; these need separate
// qualification if a later power-management mode actually uses them.
module sirv_gnrl_ram #(
 parameter DP=16384, DW=32, MW=4, AW=14, FORCE_X2ZERO=0
)(
 input sd,ds,ls,rst_n,clk,cs,we,
 input [AW-1:0] addr,
 input [DW-1:0] din,
 input [MW-1:0] wem,
 output [DW-1:0] dout
);
 generate
  if(MW!=DW/8) begin: invalid_byte_mask
   QINGYU_UNSUPPORTED_TCM_MASK invalid_configuration();
  end
 endgenerate
 qingyu_banked_sram #(.DP(DP),.DW(DW),.AW(AW)) u_storage(
  .clk(clk),.cs(cs),.we(we),.addr(addr),.din(din),.wem(wem),.dout(dout)
 );
endmodule
