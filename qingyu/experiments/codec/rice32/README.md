# Rice32 streaming codec prototype

Independent lossless encoder and decoder for the frozen global Rice32 format.
This is a functional/cycle experiment, not a selected SoC candidate or PPA result.
It changes neither the numerical INT8 configuration nor the published codec
parameters. X/W/Y retain global k=2/5/3, with row delta on X/Y and raw W.

The public interfaces and precise framing/error rules are in `contract.json`.
Both modules accept a local START handshake and use 32-bit ready/valid data
ports. Symbols occupy consecutive low-to-high bytes; bitstream byte zero is
also in bits[7:0], with MSB-first bits inside each byte. Each nonfinal symbol
beat has `LANES` bytes; the tail has one through `LANES`. Encoded nonfinal beats
have 32 bits, and the final beat declares 1..32 valid bits with zero padding.

The encoder collects a complete block of up to 32 transformed bytes before
choosing its canonical one-bit raw escape. Two block buffers allow collection
and coding to overlap. The decoder commits a group only after its complete
parse succeeds; an incomplete group leaves the bit reservoir and block state
unchanged. It rejects out-of-range unary codes, noncanonical raw choices,
declared length/count mismatch, nonzero padding and explicit truncation.

`row_bytes=16/64/256` is supported when delta is enabled. Every START resets
the row epoch. The first row overwrites its history locations while bypassing
old contents; no initialized RAM assumption or cross-task row reuse is needed.
The fixed byte codec can operate on a 99x16 output tile, but any larger task
layout, reorder buffer, FIO framing and cold-task protocol remain integration
work. No matrix multiplication or Winograd factor is computed by the codec.

Error is sticky until the next START. An already offered output retains valid,
data/count/last until its ACK. Input is discarded through explicit last before
error completion. An absent producer or absent last cannot be diagnosed as a
finite truncation; reset aborts that stalled transaction. A consumer must discard
the frame on error, even if some prefix bytes were delivered previously.

## Verification

The independent Python writer produces actual frozen-format bitstreams. RTL
encoder words must match those bitstreams exactly; decoder symbols must match
the original quantized bytes. Expected results do not use RTL internal state.
The 36 full-matrix real streams also cross-check their encoded lengths against
the separately completed global codec study. Tests verify inclusive local START
through final ACK counters, held outputs, restart epochs and actual tail flush.

Final LANES=4 regression:

- `runs/20261111T163558870629Z/result.json`, SHA-256
  `b05ff6a9cb7f4e24e85015637fef0714b2de8c37d75cef3776aeae93e3337738`.
- Three seeds, each 117 normal cases with both no stalls and randomized stalls:
  69 synthetic/extreme/tail cases and 48 true validation streams (sample index9,
  12 layers' X/W/Y plus each layer's first 16-column Y tile).
- Per seed, 16 malformed/configuration/error-drain cases and four reset/abort
  cases. Errors while output is held are explicitly tested. Masks, widths and
  code choices are not altered to match RTL.
- Verilator RTL `--lint-only -Wall` is clean with one documented BLKSEQ style
  waiver for blocking local parse/packing workspaces; retained state is written
  nonblocking. Full simulation compile has no remaining warnings.
- Four-state Icarus quick run on the same final RTL:
  `runs/20261111T163542260188Z/result.json`, one seed, 19 normal cases plus the
  same 16 error/four reset cases.
- LANES=2 compatibility quick run:
  `runs/20261111T163558885428Z/result.json`, three four-state seeds. This smaller
  configuration has not run the full real-data suite and is not substituted
  for the LANES=4 performance numbers.

Reproduction (new timestamped output directory each run):

```sh
env OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
  python3 experiments/codec/rice32/run_checks.py --sim verilator
python3 experiments/codec/rice32/run_checks.py --quick --seeds 17
python3 experiments/codec/rice32/run_checks.py --quick --lanes 2
```

## Measured controller cycles

All three seeds have identical unstalled cycles. These are inclusive local
START through final output ACK, including row transformation, block flags,
internal buffering and final flush. Random-backpressure results are retained
per case in the report. Local START captures configuration in one handshake;
external packet-header transfers and official-fabric traffic are additional
costs and are not hidden in these codec-only figures.

| Stream, 12 validation layers | Symbols | Mean encoder cycles | Mean decoder cycles |
|---|---:|---:|---:|
| Complete X | 6,336 | 1,595.583 | 1,587 |
| Complete W | 16,384 | 4,108 | 4,098.250 |
| Complete Y | 25,344 | 6,347.583 | 6,338.833 |
| First 99x16 Y tile | 1,584 | 407.500 | 398.833 |

Details: `runs/20261111T163558870629Z/cycle_summary.json`. These figures do not
prove a complete 10,450-task/s schedule: loader, system bus, CPU, numerical
compute, buffer arbitration and end-of-task output acknowledgement must all
be measured together. Four symbols is a maximum per cycle; unusually long
codes cause real reservoir stalls rather than truncation or invented speed.

## Physical implementation limits

Each generic module allocates 256x8 history bits with up to four byte reads and
four byte writes per cycle. This is currently RTL register-array storage, not
a claimed single-port SRAM mapping. The encoder additionally holds two 32-byte
blocks (512 bits), a 512-bit bit reservoir and a 32-bit output hold. The decoder
has its own 512-bit reservoir and 32-bit output hold. The two histories, block
buffers and reservoirs alone total 5,632 state bits, before output/control
state. A production fixed-width/disabled-delta instance could be specialized,
but no such savings are claimed here.

Variable shifts and up to four dependent unary parses form nontrivial
combinational paths. Their synthesis area, fanout, power and 150 MHz timing
are unmeasured. The standalone test clock and its cycle counts are not STA
evidence. This prototype must not be assigned zero area/power or used to turn
the analytical transport upper bound into an achieved task throughput.
