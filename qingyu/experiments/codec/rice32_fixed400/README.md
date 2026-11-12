# Fixed-format Rice32 with400bit encoder reservoir

This independent candidate keeps the `rice32_fixed` decoder and widens only that candidate's encoder reservoir to400bits. Frozen generic, bounded and fixed256 sources/results remain unchanged. Module ports and names stay compatible with the existing INT8 engine; compile exactly one encoder and one decoder implementation.

Encoder accepts k3 only, with delta row16 or no delta. Decoder accepts k2/k5 with delta row16/64 or no delta. LANES is4; history capacities are16/64bytes. Unsupported k/row/empty START returns a configuration error and completes next cycle without consuming a payload. Runtime malformed input keeps already offered output stable and drains input through last; permanent missing input/output ACK still requires the integrating watchdog/reset. This is not an assertion that an unresponsive peer can be physically drained.

## Why400bits

At k3, a byte's code is at most31 unary ones+one zero+3 remainder bits=35bits. Four symbols plus a block flag need at most141bits. Keep the bounded encoder's original append predicate, evaluated after any output emission: remaining count<=256. Consequently no accepted step exceeds256+141=397bits, and a400bit reservoir with9bit count is sufficient. The top output word isbits399:368. A64bit code is aligned at the top by concatenating336zero bits before shifting by the current count. Every append is an explicit expression; there is no automatic task/inout copy-out dependency.

The bound is inductive: reset/START/error set count0; emission only decreases it; a permitted append starts at<=256 and adds<=141; without an append it holds. A group cannot cross two block flags because32 is divisible by LANES4 and a short block is final. These facts hold for arbitrary accepted byte values and backpressure, not only the calibration corpus.

The original512bit reservoir's lowest115bits cannot hold valid data under these legal k3 bounds. Counts, append decisions, output emission, final flush and errors therefore have the same intended schedule as bounded. This is checked by a live original bounded encoder shadow on every cycle of every legal k3 epoch, including ready, valid, busy/done/error, counters, payload and held data. Invalid configurations are separately tested because the older generic contract accepts additional values.

The fixed decoder uses320bits, oldcount<=288 input admission and64 unary scan positions. A valid k2 symbol may require66bits; the scan counts only unary/terminator and the suffix still comes from the full320bit vector. Four symbols plus header can require265bits.64 consecutive unary ones is rejected, not silently truncated. Partial-group parsing/history updates roll back until all four symbols or the final partial group are available. The raw tie rule and all final padding/length checks remain frozen.

## Verification

`run_checks.py` runs each implementation independently against the original scalar wire encoder and immutable72task packets. X/W are decoded; Y is encoded. Every stream has no-stall and seeded backpressure trials. A deterministic per-frame clock schedule controls sink ready and producer gating for both implementations; payload comparison follows each implementation's accepted handshakes. The400bit encoder also has a live cycle shadow. Counter measurements include START, fill, flush and final ACK.

`run_boundary_checks.py --base <passed quick run>` adds exact canonical raw ties, forbidden Rice ties and every byte value, retaining all quick malformed prefix/tail/reset/held-output tests. `run_frontend_checks.py --vectors <passed quick run>` compares originalSV, sv2v output and Yosys0.33 optimized Verilog against the same independent scoreboards. Generated-netlist TB removes already-elaborated LANES overrides; stimulus and checking are unchanged. This finite regression is not formal LEC or foundry signoff. The old generic encoder Yosys task/inout miscompile remains rejected.

```sh
OPENBLAS_NUM_THREADS=2 python3 experiments/codec/rice32_fixed400/run_checks.py --quick --sim iverilog --seeds 17
OPENBLAS_NUM_THREADS=2 python3 experiments/codec/rice32_fixed400/run_checks.py --sim verilator --seeds 17 271 20261112
```

## Resource and performance limits

Compared with bounded, reservoir retained storage changes1024→720bits (-304), the two used counters each save1bit, and encoder constant k removes3bits:309 fewer declared retained bits. Compared with fixed256, the400bit buffer adds144data bits plus one counter bit,145 in total. Both histories remain128+512bits. The64bit combinational code temporary, narrower shifts and shorter unary scan are separate from retained storage. These counts are not physical area/energy and cannot establish timing.

Fixed256 showed a real backpressure penalty; its result remains a valid separate candidate. This400bit version restores the old k3 append predicate to avoid that penalty. Engine/realE203/official-bus testing and official-library area/STA/full-SoC energy are still required. No loader timing interpretation, quantization, payload format or task denominator changes here.

## Frozen results

`VALIDATION.json` binds the four-state quick,72-task three-seed regression, explicit raw-tie/all-byte tests and three-stage frontend result. Every full seed has1860 normal frames,41 error tests and4 resets. All normal paired no-stall/backpressure cycle differences are zero, including the141bit repeated-code adversarial case. The real corpus supplies3456 encoder and1944 decoder frame pairs per stall mode across three seeds. Live encoder shadow checks include the full ready/valid/status/counter/held-payload sequence; decoder checks its own accepted sequence against the immutable golden. No whole-SoC or physical result is implied.
