# Fixed-format Rice32 candidate

This independent candidate preserves every supported wire bit and numerical value. It does not modify frozen `rice32` or `rice32_bounded`. Compile these two module sources instead of another codec directory; module names and ports are unchanged. The task engine must use encoder k3 and decoder k2/k5, as the existing frozen INT8 packets already do.

## Contract and bounds

LANES is exactly4. Encoder history is exactly16bytes and accepts delta row16; decoder history is exactly64bytes and accepts delta row16 or64. Non-delta W rows32 need no history. START rejects unsupported k, zero length, and invalid delta row before accepting payload. The next clock completes a configuration failure. START resets positions/epoch; history data is intentionally not bulk-reset, and first-row reconstruction bypasses previous history.

Encoder k3 has maximum quotient31 and code length35. A four-symbol group crosses at most one32-symbol block header, so at most141bits are appended. Emission runs first; appending requires at most112bits remaining. 112+141=253 fits the256bit reservoir. Single-code combinational temporary is64bits. Block raw/Rice selection still uses the complete actual block cost and selects raw on a tie. There is no truncation and no automatic task/inout append helper: every append is an explicit vector expression and count addition. Encoder removes the retained variable k register because only3 is legal.

Decoder k2 has maximum63 unary ones and66bits per symbol; k5 has maximum7 and13bits. The speculative group needs at most1+4*66=265bits. This bound deliberately includes noncanonical streams, which may have to be parsed before the whole-block raw-selection check rejects them. The320bit reservoir accepts32bits only when old count<=288. A64-bit unary scan includes the legal terminating zero;64 ones is explicitly invalid and cannot become an indefinitely waiting prefix. All partial groups roll back parser position and history until the full group is available. One-bit final words, little-endian byte lane packing, zero padding, declared lengths, raw canonicality, and full final-frame consumption checks remain unchanged.

Runtime malformed input is drained through an accepted last beat. An already offered output is retained until ACK. If the peer never supplies the remaining input/last or never acknowledges output, an external engine watchdog/reset is still needed; the codec cannot claim bounded physical drain of a permanently unresponsive peer. Global reset may discard the internal stream only when integrated peers share the reset/abort contract.

## Verification and measurement

`run_checks.py` uses the original frozen scalar bit writer and immutable72-task corpus: X streams decode, W streams decode, Y streams encode against their frozen payload bytes. It checks each implementation's own accepted payload sequence. It separately runs the bounded reference with the same case-relative cycle output-ready schedule and offered-input gating, seeded independently for each frame; it does not require the two reservoir sizes to have identical ready/cycle traces. Every no-stall and stalled run counts START, fill, final flush and final output ACK.

Directed tests cover all legal k values, all unsupported k values, all-byte extremes, short and partial blocks, first-row epoch, oversized delta rows, canonical/tied raw choice, a141bit encoder append, a265bit decoder group followed by noncanonical rejection, all-one malformed prefixes, word boundaries, one-bit final words, input count/last errors, sticky error with held output, long/random backpressure and reset while active/held. Internal capacity assertions supplement the independent byte/bit scoreboards; they do not calculate golden data from the DUT.

Run (Linux/WSL):

```sh
OPENBLAS_NUM_THREADS=2 python3 experiments/codec/rice32_fixed/run_checks.py --quick --sim iverilog --seeds 17
OPENBLAS_NUM_THREADS=2 python3 experiments/codec/rice32_fixed/run_checks.py --sim verilator --seeds 17 271 20261112
```


`run_frontend_checks.py --vectors <passed-run-directory>` also checks originalSV, sv2v output and Yosys0.33 optimized Verilog with the same quick scoreboard. The prior generic task/inout miscompile remains recorded and rejected in `experiments/synthesis/codec_frontend_audit`. A first fixed-codec frontend attempt failed testbench elaboration because synthesis removes the LANES parameter. The subsequent run removes only the two elaborated parameter overrides from its generated testbench; RTL, stimulus and checker remain unchanged. Logs from both attempts are retained. This is finite simulation equivalence, not formal LEC.

## Costs and limits

History is unchanged from bounded (128+512 retained bits). Reservoir storage changes512+512 to256+320, saving448 declared bits; counters shrink by3bits total and the constant encoder k eliminates3bits. These454 retained-bit savings exclude combinational workspaces. The256→64 temporary, narrower variable shifts and256→64 unary scan are intended to reduce combinational complexity; only real synthesis/STA can establish that outcome. No mm², µJ or150MHz claim is made.

Smaller buffering can increase cycles. The deliberate repeated maximum-code example already takes14 additional no-stall cycles for512bytes versus bounded. Actual corpus cycle differences are recorded in each run's `cycle_comparison.json`; they must be assessed in the real engine/SoC before adopting this candidate. All official bus, loader window, full-task performance and physical signoff requirements remain separate.

## Frozen evidence

`VALIDATION.json` binds all result files and the exact RTL. Full72-task regression passed3seeds for both fixed and bounded reference: each seed1860 normal frames, each with no/random stalls, plus41 fixed error cases and4 resets. Separate four-state boundary regression covers exact canonical raw ties and every byte value for all accepted k. OriginalSV/sv2v/Yosys-generated quick traces all pass; this is not formal signoff.

Across real streams and3seeds, all3456 encoder and1944 decoder no-stall pairs have zero cycle difference. Under the same long random backpressure schedule, all1944 decoder pairs remain equal. Encoder increases in3455/3456 pairs, mean47.245370cycles per Y tile, range0..127. These standalone increments cannot simply be added to overlapping engine time, but they must not be hidden. Use the real E203 runner for selection; retaining the bounded encoder while selecting only the fixed decoder is a separate configuration to verify.
