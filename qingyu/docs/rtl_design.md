# RTL implementation and verification

`qingyu_accel` implements the interface in `engineering_contract.md`. Parameters
are ROWS=99, K=64, LANES=4 by default. The engine computes one output-channel
tile; firmware loads all 64 tiles for a complete 99x256 result.

Storage uses two 16x4096 input banks, LANES 16x128 weight banks, one 16x128
metadata bank, and two 16x1024 output banks. The wrapper is a behavioral,
single-port synchronous SRAM model. It must be replaced or mapped to approved
macros for contest synthesis, area and power; functional simulation is not
evidence of an ASIC macro implementation. No SRAM array has reset logic.

Each packed MMIO word uses two physical 16-bit accesses. Requests are accepted
only with no pending response; response data/error/valid remain held during
backpressure. Memory accesses while computing return errors. A synchronous
software reset aborts the engine, invalidates task control state and clears
errors without clearing memory contents. Software must load required data.

Four signed 16x16 multipliers feed signed 48-bit accumulators. The first
correctness baseline uses one SRAM read cycle plus one accumulate cycle for
each k, so it is not one-MAC-per-lane-per-clock. Biases are loaded from SRAM
before each tile. A signed 49-bit extended sum checks internal overflow before
committing each accumulation. Results use magnitude-based round-to-nearest,
ties-to-even (including negative ties) and int32 saturation, one output lane
per storage cycle. Final DONE is raised after the last output write edge.

Register error codes:

| Code | Meaning |
|---:|---|
| 1 | Unmapped/read-only/misaligned access |
| 2 | Memory access while engine busy |
| 3 | Unsupported write byte mask |
| 4 | Invalid layer/tile/control configuration |
| 5 | Start while busy |
| 6 | Signed 48-bit accumulation overflow |
| 7 | Metadata shift above 47 or reserved bits nonzero |
| 8 | Configuration write while busy |

The standalone testbench covers ID, response backpressure, invalid addressing,
write masks, packed input readback, busy-time accesses, continuous jobs,
signed multiplication/bias, positive and negative RNE ties, int32 saturation,
positive and negative accumulator overflow, invalid metadata, soft-reset abort
and recovery. `+VECTORS=tb/vectors/layer00` additionally compares every output
of a complete 99x256 external vector set using the model agent's packed files.
`+VCD` writes a functional waveform to `reports/qingyu_accel.vcd`; it is not a
signoff power activity file until clock and formal measurement windows are
configured with the contest flow.

Example (from project root):

```powershell
iverilog -g2012 -s tb_qingyu_accel -o reports/accel.vvp rtl/qingyu_sram16.sv rtl/qingyu_accel.sv tb/tb_qingyu_accel.sv
vvp reports/accel.vvp
```

This implementation has not yet been checked with the official standard-cell
and memory libraries. Timing, macro area and power remain unmeasured.

Verified locally with Icarus Verilog 12.0:

- Default ROWS=99/K=64/LANES=4 directed suite: 58,176 bus checks and 1,980
  output comparisons passed.
- `+VECTORS=tb/vectors/layer00`: all 25,344 full-matrix output comparisons
  passed; combined with directed checks, 517,921 bus checks and 27,324 output
  comparisons passed. These are deterministic synthetic engineering vectors,
  not official KWT inputs or an accuracy measurement.
- Reduced ROWS=2/K=4 configuration directed suite also passes; useful as a
  fast smoke test after interface or numerical changes.

The full default-dimensional Icarus regression takes several minutes on this
machine. No timing/area/power claim is derived from simulation wall time.
