# Qingyu accelerator engineering contract

This is the implementation interface shared by RTL, model, firmware and tests.
Baseline dimensions: ROWS=99, K=64, N=256, LANES=4. A tile computes
Y[0:ROWS, j0:j0+LANES] = X @ W_tile + bias_tile. E203 schedules all 64 tiles.
Input and weights are signed 16-bit, accumulation signed 48-bit, output signed
32-bit. Rounding is nearest, ties to even. Overflow saturates at output; an
internal accumulator overflow is an error. The 48-bit sum must include bias.

The peripheral exposes a 32-bit ICB slave with one outstanding transaction:
`icb_cmd_valid`, `icb_cmd_ready`, `icb_cmd_read` (1=read),
`icb_cmd_addr[15:0]` (relative byte address), `icb_cmd_wdata[31:0]`,
`icb_cmd_wmask[3:0]`; `icb_rsp_valid`, `icb_rsp_ready`,
`icb_rsp_rdata[31:0]`, `icb_rsp_err`. Reset is synchronous active-low `rst_n`.
Top module name is `qingyu_accel`, clock `clk`. Responses must remain stable
while stalled; no writes may occur without a request handshake. Full-width
aligned word accesses are required for memory windows; reject unsupported
byte masks and misalignment with an error. Busy-time memory accesses must
return an error. Register reads including STATUS remain available while busy.

| Offset | Register | Meaning |
|---|---|---|
| 0x0000 | ID_VERSION | 0x51590001, read only |
| 0x0004 | CONTROL | write bit0 START_TILE, bit1 CLEAR_DONE, bit2 SOFT_RESET |
| 0x0008 | STATUS | bit0 BUSY, bit1 DONE, bit2 ERROR; DONE/ERROR sticky |
| 0x000C | LAYER_ID | software label 0..11 |
| 0x0010 | TILE_COL_BASE | 0..252, multiple of LANES |
| 0x0014 | ERROR_CODE | nonzero errors; documented by RTL implementation |
| 0x0018 | COMPUTE_CYCLES | diagnostic only, not end-to-end time |
| 0x001C | OUTPUT_COUNT | ROWS*LANES when successful |

Memory windows (all little-endian words):
- INPUT 0x1000: X row-major `[t,k]`; two int16 items per 32-bit word.
- WEIGHT 0x5000: W tile `[k,p]`, p fastest; two int16 per word.
- META 0x6000: one 64-bit record per lane, low word first. Bits 0..47 are
  two's-complement bias; bits 48..55 are unsigned right shift r=0..47;
  bits 56..63 reserved zero.
- OUTPUT 0x7000: int32 `[t,p]`, p fastest, read-only.

First load the complete input and each tile's weight/meta values; then start.
The software is responsible for initializing all required memory before start.
Reset invalidates the task state and aborts work; it need not zero SRAM data.
Every independent performance task must reload input and parameters. The host
clears DONE/ERROR before a new tile and waits for DONE or ERROR with a timeout.
Hardware applies bias and output scaling; CPU performs only copies/control.

The bit-accurate model implements:
qx=clip(RNE(x/sx),-32767,32767), qw=clip(RNE(w/sw),-32767,32767),
qb=RNE(b/(sx*sw)), A=qb+sum(qx*qw),
qy=sat32(RNE(A/2**r)), y= float(qy)*sx*sw*2**r.
sx is per layer; sw/r per output channel, fixed using training calibration.

Source provenance and official data must remain distinct from deterministic
synthetic engineering vectors. Passing synthetic tests is not a KWT accuracy
measurement or an official contest acceptance result.
