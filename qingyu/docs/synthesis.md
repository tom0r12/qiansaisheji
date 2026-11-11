# Synthesis scope and reproduction

`scripts/run_synthesis.py` provides a local engineering synthesis check. It
uses native Yosys when available or the isolated `tools/yosys` YoWASP package.
The latter is installed from PyPI into this project, without changing the
system Python environment. Its Wasmtime compilation cache is also project
local at `tools/yosys_cache`.

Run from the project directory with the bundled Python:

```text
python scripts/run_synthesis.py --generic-only
python scripts/run_synthesis.py
```

The mapped run defaults to the locally extracted TT 1.10 V/25 C Liberty.
`--liberty` can select another local corner; the script does not upload data.
`--timeout` sets a per-stage limit in seconds, default 300. All input RTL and
Liberty checksums are captured. If source RTL changes while the tool is
running, the summary marks the result failed/stale and requires another run
on the frozen source.

Both modes read `qingyu_sram16.sv` using Yosys `read_verilog -lib`, preserving
the wrapper as a parameterized black box. The large data arrays are never
converted to flip-flops in this check. The script requires nine SRAM
instances: two 16x4096 input banks, four 16x128 weight banks, two 16x1024
output banks and one 16x128 metadata bank, totaling 174,080 bits (21.25 KiB).
Accumulator, bias and controller state registers are ordinary logic and are
included in the mapping.

The generic pass elaborates the design and maps its operators into generic
logic, then runs Yosys `check -assert`. The mapped pass imports Liberty cells,
maps flip-flops, runs ABC combinational mapping, and runs another structural
check. Output files are under `reports/synthesis*`: the exact tool version,
scripts, logs, generic/mapped JSON and Verilog netlists, tool statistics, and
the consolidated `synthesis_summary.json`.

The production Yosys flow uses `synth -nofsm` to preserve the source control
encoding. In the investigated automatic FSM-recoding flow, the generic
one-hot netlist behaved correctly, but the TT-mapped four-state simulation
became unknown at the final metadata-capture transition. Independent
Liberty-derived zero-delay models reproduced the same failure, and slowing
the test clock did not remove it. A cone probe found an unknown upper bit of
the mapped `meta_lane` counter feeding the next-state D input. The preserved
binary-control flow passed the same sampled mapped functional check without
changing the RTL algorithm or initializing SRAM to hide unknown values.
This is a tested flow choice, not a claim that every possible FSM recoding or
all technology mappings are faulty. Original reports, failing netlist/logs
and the fanin probe are retained in `reports/fsm_recode_investigation`.

Logic area is independently summed from the mapped cell instances and each
Liberty cell's `area` attribute. Unknown or remaining generic cell types
invalidate the mapped result. The report retains **library area units** by
default because Liberty does not universally define the physical unit of
`area`. Only use `--area-unit-um2` after confirming that the vendor's numbers
are square micrometres; it then additionally reports logic mm². Never infer
physical area from the numerical scale alone.

SRAM macro area is excluded, and the report explicitly leaves official total
area acceptance unset. Add actual allowed macro areas, including every
instantiated macro, before comparing accelerator plus interface plus SRAM
against 2.25 mm². A successful mapping is not a proof of 150 MHz timing,
functional equivalence or power/energy. ABC mapping is not static timing
analysis. No such pass is claimed by this script.

## Formal ASIC flow template

`scripts/synth_dc.tcl` is a Design Compiler entry point. It requires actual
standard-cell `.db` libraries, actual SRAM `.db` libraries and a replacement
`qingyu_sram16` wrapper that instantiates the allowed macros. It intentionally
does not read the checked-in behavioral SRAM array. The library cell names
and ports in that replacement must match the supplied macro models.

Required environment settings are:

| Setting | Value |
|---|---|
| QINGYU_TARGET_LIBS | Tcl list of standard-cell .db paths for the selected run |
| QINGYU_SRAM_LIBS | Tcl list of actual SRAM .db timing library paths |
| QINGYU_SRAM_RTL | Tcl list of replacement wrapper HDL file paths |
| QINGYU_INPUT_DELAY_NS | Platform input delay relative to sys_clk |
| QINGYU_OUTPUT_DELAY_NS | Platform output delay relative to sys_clk |
| QINGYU_CLOCK_UNCERTAINTY_NS | Required clock uncertainty |
| QINGYU_INPUT_SLEW_NS | Required non-clock input transition |
| QINGYU_OUTPUT_LOAD_PF | Required load on each output |

Optional settings are `QINGYU_CLOCK_PERIOD_NS` (default 6.666666667 ns),
`QINGYU_RUN_TAG` (safe output suffix), and `QINGYU_USE_ULTRA=1` when licensed.
Run the script with the installed licensed `dc_shell` and its normal
`-f scripts/synth_dc.tcl` option. Libraries and constraints must match the
actual contest conditions; library paths are not populated with fabricated
SRAM substitutes. Run and assess required process/temperature corners
separately, including minimum-delay checks.

`constraints/accelerator.sdc` creates the 150 MHz clock while requiring
explicit I/O delays, slew, uncertainty and loads. Synchronous reset remains
timed, and there are no blanket false-path/multicycle exceptions. The unit
assumption of ns/pF must match the supplied libraries. Missing platform
assumptions stop the formal script rather than silently generating a pass.

The formal flow writes pre/post design checks, timing checks, maximum/minimum
paths, all constraint violations, hierarchical area/reference information,
units, clocks, mapped HDL, DDC and final SDC. Review these results and perform
functional equivalence or appropriate post-synthesis simulation. Full-SoC
SAIF/VCD power coverage and SRAM energy models are additional required work.
Design Compiler/STA execution cannot be claimed on a machine where those
tools or the actual SRAM models are unavailable.

## Verified engineering run

The local Yosys 0.70 run completed generic synthesis, TT cell mapping and
structural checks on the RTL hashes recorded in `synthesis_summary.json`.
The production `-nofsm` mapped design contains 12,825 standard cells and nine SRAM black boxes.
The black boxes preserve 174,080 storage bits, and none of that bulk storage
was expanded into flip-flops. Both the tool statistic and an independent
sum of Liberty `area` attributes report **18,360.5436** for the logic.

Area units were then confirmed against the matching vendor LEF, extracted
alone from the local split ZIP. LEF `MACRO SIZE` dimensions are specified in
micrometres by the [Cadence LEF/DEF 5.7 reference, page 183](https://ispd.cc/contests/18/lefdefref.pdf#page=183).
The library's macro LEF declares version 5.7 and has no separate UNITS block;
the text SIZE dimensions follow that micrometre convention. For all **1,027**
shared Liberty/LEF cell names, Liberty `area` agrees with LEF width times
height within 1e-8 µm². All **64** mapped standard-cell types are represented.

| Mapped example | LEF width × height (µm) | LEF and Liberty area (µm²) |
|---|---|---:|
| INV_X0P5B_A9TR40 | 0.38 × 1.26 | 0.4788 |
| NAND2_X0P5A_A9TR40 | 0.57 × 1.26 | 0.7182 |
| DFFQ_X0P5M_A9TR40 | 3.04 × 1.26 | 3.8304 |
| MXIT2_X0P5M_A9TR40 | 1.33 × 1.26 | 1.6758 |
| XNOR2_X0P5M_A9TR40 | 1.33 × 1.26 | 1.6758 |

Re-summing the 12,825 mapped instances from their LEF geometries gives
**18,360.5436 µm² = 0.0183605436 mm²**. This is the standard-cell area of the
`qingyu_accel` top only, including its internal MMIO/control logic. Its nine
SRAM macros and the separate SoC/FIO adapter are excluded, as are physical
implementation overheads. It is not an official total-area pass.
`reports/synthesis_area_units.json` records the comparisons, LEF/Liberty and
netlist hashes, original synthesis-summary hash, and the exact RTL hashes.
The original synthesis summary retains its conservative default unit field;
the companion unit-validation report establishes this conversion for this
specific library and mapped netlist without rerunning synthesis.

The Tcl scripts passed a balanced-script syntax check using the installed
Tcl interpreter. Running the formal entry without platform configuration
stopped at its intended missing-library preflight check. This validates the
guard, not Design Compiler command execution: no licensed DC or STA tool was
available, no actual SRAM timing/area view was supplied, and no formal
150 MHz or power/total-area acceptance result has been produced.
