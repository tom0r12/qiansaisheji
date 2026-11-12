# INT8 E203 verification and assessment bundle

This is a separate full digital SoC experiment: the actual E203 executes the
packaged firmware, the concurrent INT8 packet engine uses the prefetch8 core
and bounded Rice codec, and every shared SRAM access traverses the unchanged
official memory fabric. This package does not reuse any historical candidate's
numerical, macro, area, timing or power report as proof of this composition.

The manifest binds ordered compilation inputs, included headers, firmware,
the six-sample/twelve-layer diagnostic corpus, expected metrics, and the local
physical-port fixture evidence. This corpus is diagnostic, not an unbiased
population estimate or the official600 accuracy evaluation.

Start with the immutable package check:

```sh
python3 run_int8_server.py --mode validate
python3 run_int8_server.py --mode behavioral --tasks 1
python3 run_int8_server.py --mode macro --tasks 1 --macro-model-manifest /reviewed/location/models.json
python3 run_int8_server.py --mode macro --macro-model-manifest /reviewed/location/models.json --activity
```

Omitting `--tasks` runs all72 listed sample/layer tasks. Each invocation creates
a new `qingyu_verify_int8_dual_prefetch8_bounded_*` directory and preserves its
inputs, tool output, log hashes and result. The wrapper `qi` first verifies the
archive SHA, extracts into a unique directory, then forwards these arguments.

Physical validation replaces exactly the behavioral SRAM wrappers. During CPU
reset, all131072 shared words are initialized through the shared ICB interface;
ITCM/DTCM are initialized at the real banked macro write ports. All simulation
forces are released before CPU execution. After host completion, a cold-clear
and131072 actual shared-port reads check every output word, untouched output
slot, unchanged source word and guard word. No manufacturer-private array is
read or written by the fixture. The original DMA/fabric/shared request and
response scoreboards remain active only during runtime.

The three external SRAM models must be reviewed originals from SRAM_Lib_2025:
`RAMSP128X16`, `RAMSP1024X16`, `RAMSP4096X16`. The review JSON must record exact
model SHA256 values, official source identity and explicit accepted review.
The runner reads each model from its library directory's `verilog/NAME.v`.
Local functional substitute models are deliberately absent from this package.
Local substitute evidence only establishes fixture/storage functionality;
manufacturer behavior, electrical timing and power remain to be validated.

Macro binding is explicit: `CLK`, active-low `CEN`, `GWEN`, per-bit `WEN`,
address `A`, write `D`, read `Q`, `EMA=3'b010`, `EMAW=2'b00`, `RET1N=1`.
Private memories use full16-bit writes; CPU/shared wrappers replicate each
byte write enable over its eight mask bits. No initialization, read-during-write
value or unknown-to-zero conversion is added to the macro adapter. Qualify
these pins/margin settings and the chosen library corner against the actual
manufacturer source before assessment.

The expected hierarchy contains21 private128x16 macros,8 private1024x16,
64 shared4096x16 and16 CPU4096x16 macros. Synthesis audits these counts both
before and after compile. Incremental area includes all new compute, transport,
codec, row reorder, engine control, FIO MMIO, CPU/DMA merge, shared cache and
wrapper/interface logic. Only individually enumerated unchanged CPU/fabric/
peripheral boundaries and fixed shared/CPU macros are excluded. Whole-SoC
power includes every category, including speculative SRAM reads.

Copy the configuration examples outside the immutable package and complete
them with reviewed server-local library/SDC identities. They intentionally fail
before compilation when incomplete. Only the official
`SCC40NLL_VHSC40_RVT_V0p1` family is accepted; archive-to-database identity,
cell inventory, area units, macro area, operating corner and timing provenance
are mandatory. The platform SDC must constrain the full150MHz digital SoC and
32.768kHz AON domain, generated clocks and real I/O timing, rather than only
the compute block.

```sh
python3 run_int8_server.py --mode synth --config /reviewed/platform.tcl
python3 run_int8_server.py --mode sta --config /reviewed/platform.tcl --mapped-run /this_bundle/synthesis_run
python3 run_int8_server.py --mode formal --config /reviewed/platform.tcl --mapped-run /this_bundle/synthesis_run
python3 run_int8_server.py --mode power --config /reviewed/platform.tcl --mapped-run /this_bundle/synthesis_run --activity-review /reviewed/activity.json
```

The engineering cycle window begins at the first accepted CPU parameter write
and includes the final originating marker-write ACK cycle. Its trace starts at
that parameter edge and ends at the following edge after the marker ACK, so
the trace duration covers the same inclusive number of actual bus clocks.
Both timestamps and the marker ACK cycle are printed. Source/firmware preload
and boot preceding that first CPU write are excluded. The official initial
loader boundary is still OPEN; this is not a claim about official timing.

Power requires a reviewed, window-trimmed SAIF from this bundle's passed real
manufacturer macro simulation. The review binds source task ID, result/log/VCD
hashes, start/end timestamps, mapped netlist hash, full-SoC scope and mapping/
SRAM power reviews. The full hierarchy strip path is `tb_int8soc/dut`. Missing
activity or SRAM power is never assigned zero. Tool exit0 retains artifacts
pending report review; it does not establish timing, formal or PPA acceptance.

No upload, remote execution or PPA completion is implied by package creation.
