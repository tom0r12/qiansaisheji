# SRAM-backed eight-row INT8 arithmetic prototype

This is an independent `99x64 * 64x16` compute block. It keeps the original frozen INT8 numerical format and evaluates the exact paired-product identity with hardware-generated factors. It is not a CPU/FIO/SystemBus integration, a complete 256-channel task benchmark, or a PPA result. Production candidates and vendor RTL are unchanged.

The `contract.json` defines every accepted 32-bit input word and packed output word. A start handshake creates one task. The loader then sends 1600 X words, 256 W words, eight bias words and four shift words. X words contain adjacent-K pairs from two adjacent rows; W words contain adjacent-K pairs from two adjacent output channels. Each word therefore writes two different physical SRAM banks in one cycle. Row99 is padding and is never computed or emitted. The output consists of396 ordered words, each packing four adjacent INT8 channels from one real row. Every task reloads all its X/W and metadata; reset discards incomplete work.

X uses eight1024x16 single-port SRAMs and W uses sixteen128x16 single-port SRAMs:163840 allocated bits, or20KiB. `rtl/qingyu_sram16.sv` supplies the project synchronous behavioral SRAM. The matching ASIC wrapper uses official128/1024 macro sizes, but no foundry-macro functional or physical claim is made here. Verilator XML elaboration is checked for these exact depths/counts,128 raw pair lanes and24 hardware factor units. There is no large register array masquerading as free payload SRAM.

The PE is `winograd_int8_pair_acc32`: two signed9 pre-adders, one9x9 multiplier, an18-bit product register and a23-bit accumulator. The accumulator itself holds the completed pair sum under backpressure. Each PE has45 declared state bits including control, before synthesis. It has no R/C/bias copies. The24 reused factor units retain R8/C16 directly in their21-bit output registers; there are no additional shadow arrays. Bias16 and shift8 are stored once per channel. Four shared24-bit factor/bias correction and RNE paths produce the four output bytes. The scalar reference kernels remain frozen in `../winograd_int8`.

The control schedule is deliberately sequential: cold load;32 column-factor reads; then, for each of13 row groups,32 row-factor reads,32 paired-product reads and serialized output. The last group has three active rows. A group changes only after its final packed-output ACK. This also keeps every factor/bias epoch stable while outputs are stalled. SRAM requests have one-cycle read latency; verification checks that every resulting factor/PE transfer has a ready receiver. Factors are reset on each new task and never supplied by software.

The no-stall testbench measures3210 cycles from start acceptance to final output ACK:1869 load,490 cold-factor,455 compute and396 store. The1869 load cycles include1868 accepted words plus one explicit driver gap following start. These are compute-block testbench cycles, not a150MHz timing result. Multiplying3210 by16 is also not an optimized full-task architecture: a future full256-channel design needs an explicit X/factor lifetime across channel tiles, load/store overlap and an actual official-bus path. The current codec experiment's row-major stream cannot feed this row-pair layout for free; decoding/reordering storage and cycles must be included.

The shared correction/RNE path remains unverified by STA. Although valid bits gate PE registers, current unisolated operands may toggle PE combinational multipliers during factor reads. Operand isolation, factor/compute overlap and output double buffering are future candidates, requiring their own functional/timing/power evidence. Counts of multipliers, register bits or SRAM capacity are not area or energy estimates.

The vector exporter verifies the original frozen training-config hashes and independent validation identities. It declares sample9 before reading data and exports all12 layers and all16 channel tiles:192 real tiles and304128 real output elements. The golden uses the ordinary64-product integer accumulation, scalar ties-to-even right shift and signed8 saturation; it never uses the Winograd formula. Twenty-two additional full-range, rounding-boundary and random tiles exercise -128, extreme signed16 bias and shifts0..47. Every output check also compares the pre-RNE signed24 accumulator, preventing saturation from hiding arithmetic defects.

The regression includes input/output stalls, held-output stability, reset during load/factors/compute/stalled and partially consumed output, complete reload, and rejection of invalid early/late shift metadata. Verilator gets both the testbench seed and `+verilator+seed+N`, so separate seeds actually vary its random stream. Strict RTL lint is separate from testbench compilation. Testbench-only integer-as-Boolean and intentional signed24-to-integer extension diagnostics are reviewed separately; they are not RTL width waivers.

From the project root:

```
.venv-model/Scripts/python.exe experiments/arithmetic/winograd_array8/export_vectors.py --output build/new_array8_vectors
.venv-model/Scripts/python.exe experiments/arithmetic/winograd_array8/run_lane_equivalence.py
.venv-model/Scripts/python.exe experiments/arithmetic/winograd_array8/run_array_checks.py --vectors build/new_array8_vectors
```

All output directories must be new. The optional `--reuse-build` accepts only a completed report whose compiled RTL and testbench hashes match, and records that report and the reused binary hash. Final frozen source and validation identities are recorded in `SOURCE_SHA256.json`; older failed parser or superseded-shadow results remain separate evidence.
