# Decoded row-pair adapter experiment

`rowpair_pack` converts the frozen four-byte decoder stream into the exact X
and W loading order in `experiments/arithmetic/winograd_task8/contract.json`.
It does not change Rice bitstreams, quantization, the official fabric or any
frozen compute/codec source. This is a standalone transport component, not a
measured full-system performance result.

## Interface and mapping

See `contract.json` and the module port list. An accepted START selects X
(`start_mode_w=0`) or one 32-column W group (`=1`). Each input is exactly four
little-endian bytes; count and last are checked independently of the data.

- X takes 1,584 words for 99x64 bytes and emits 1,600 words. Each output packs
  two adjacent K bytes from an even row in the low half, then the corresponding
  two bytes from the odd row in the high half. The nonexistent row 99 is
  generated locally as zero. Its 16 additional output words are real handshakes.
- W takes and emits 512 words per 64x32 group. For two K rows and two adjacent
  columns, output bytes from low to high are even-K/even-column,
  odd-K/even-column, even-K/odd-column, odd-K/odd-column.
- `done` pulses only after the final output ACK on success. A completed input
  stream alone cannot finish the operation. Data/last/index stay stable while
  output valid is blocked.

## Storage and timing cost

The only data array is 64x32 bits: **2,048 data state bits**, divided into two
128-byte ping-pong slots. W uses 64 bytes in each slot. Two combinational
halfword selectors form output from an immutable completed slot; there is no
extra output data register. The declared control/counter state is another
85 bits. Selection, write enables, checking and control logic are additional
area. These are source-level counts, not synthesized area or energy.

The memory contents are not reset. START invalidates slot readiness and all
indices; X tail padding is a literal zero, never an old buffer value. A buffer
cannot be overwritten while it owns an offered output.

Unstalled simulation counts the accepted START edge as cycle 1 and includes
the final output ACK:

| Mode | Input words | Output words | First output offset from START | Complete cycles |
|---|---:|---:|---:|---:|
| X | 1,584 | 1,600 | 33 | 1,633 |
| One W group | 512 | 512 | 17 | 529 |

After filling, output handshakes are continuous at one word per clock; both
streams can progress concurrently. Serially running X and eight W groups
would take 5,865 adapter cycles, including all nine START/fill intervals. In
integration these cycles may overlap decoding and private loading; do not add
or subtract them from a SoC budget without the actual schedule. Stalls and the
16 padding words remain counted. There is no 150 MHz timing, area, power or
throughput signoff.

## Error and reset ownership

`error_code` is sticky until the next START: 1 invalid count, 2 early last,
3 missing last, 4 upstream error. An error stops new output offers while
preserving any already offered word until it is acknowledged. Input format
errors drain to an explicit last or `upstream_error`.

Connect `upstream_error` to the matching decoder epoch's error signal. That
signal declares no new payload will be produced. An existing producer-held
prefix word is accepted and discarded even if both adapter slots are full.
An upstream error may terminate without an input last, but cannot revoke a
held output. Do not start a new decoder or adapter epoch until the enclosing
controller has handled both components' completion/drain conditions.

A producer that disappears without last/error, or a permanently stalled
consumer, cannot be declared drained. This block has no independent watchdog.
The surrounding controller owns bounded failure reporting. Hard reset can
discard an offered internal word only when both attached stream endpoints are
reset together; outstanding ICB work belongs to the enclosing transport and
must not be silently canceled by this block.

## Verification

The independent Python golden gathers bytes by matrix coordinates, separately
from RTL word/halfword selection. Full runs use unchanged frozen INT8 configs
and validation sample 9: all 12 X matrices and all eight W groups for each of
12 layers, plus 10 synthetic cases. The 108 real frames cover 68,352 distinct
output words, including local padding; no training/calibration is performed.

Final four-state Icarus result:
`runs/20261111T165527044550Z/result.json`, SHA-256
`84f75c3ce13f968a07be69a59085419811c15d2c5b7a62f374317c5585fdcaee`.
Three seeds (17, 271, 20261112) each pass 272 normal/recovery frames, 28 error
scenarios and 8 reset scenarios. Each fixture runs continuously and with
random source/consumer stalls plus a sustained 24-cycle output stall.

Directed checks include every unsupported count, early/missing last,
upstream failure before data and with held/full buffers, preservation of
offered output through failure, reset during partial fill/held output/active
output/final output, and complete fresh reload after every failure/reset.
Four-state simulation starts the data buffer uninitialized and checks output
with case inequality. Strict `verilator --lint-only -Wall` on the RTL passes
with zero warnings; Icarus compilation also has zero warnings. Evidence stores
source hashes before/after, immutable fixture hashes and numerical provenance.

The same RTL also passes Verilator quick regression (56 normal/recovery
frames, 28 errors, 8 resets) with no compile warnings:
`runs/20261111T165527031909Z/result.json`, SHA-256
`7c4fc597ac3bd2ac60359d6a48ae69ee0f66305d9692c9fdb01c2f1ef5c34913`.
`SOURCE_SHA256.json` freezes all source/contract/README files and both result
identities. No simulation remains running after these recorded completions.

Reproduce under WSL Ubuntu from any working directory:

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 python3 \
  experiments/transport/rowpair_pack/run_checks.py
```

Use `--quick` to omit the real validation data, or `--sim verilator` for the
alternative simulator. Every invocation creates a fresh timestamped directory.
