# Synthesis-before/after functional checks

The check is side-by-side simulation of the default 99-row, 64-input, four-lane
accelerator. The RTL reference is renamed in a generated copy; production RTL
is unchanged. Both instances receive the same ICB transactions. Their ready,
response-valid, response-data and error outputs are compared at a settled
phase. All 396 results of one 99x4 tile are also checked against an independent
integer calculation.

The test includes zero/positive/negative input rows, positive/negative weights,
48-bit signed biases, nearest-even rounding of both signs, int32 saturation,
response backpressure, an invalid access, and input/weight readback. No actual
speech model accuracy is measured by this test.

**Observed results**

| Stage | Result | Exact scope |
|---|---|---|
| Current production TT mapped netlist, source state encoding preserved with `synth -nofsm`, actual vendor models | PASS | 396 output values, 10,310 ICB transactions and 28,834 settled-cycle comparisons |
| Generic synthesis netlist before cell mapping | PASS | 396 output values, 10,310 ICB transactions and 28,834 settled-cycle comparisons |
| Historical auto-FSM-recoded mapped netlist, actual PDK uniform-delay models | FAIL, archived | ID, control, loading/readback and metadata assembly agree, then the mapped FSM gains unknown bits at the final metadata capture to row initialization transition |
| Same historical variant, zero-delay functional models read from TT Liberty | FAIL, archived | Reproduces the same transition issue, so no timing/notifier conclusion can be drawn from the uniform-delay failure |
| Separate synthesis with `synth -nofsm`, same TT mapping and actual vendor models | PASS | 396 output values, 10,310 ICB transactions and 28,834 settled-cycle comparisons; production RTL unchanged |

The current engineering flow selects `synth -nofsm`, preserving source state
encoding, and its production mapped output passes this sampled check. No RTL
change was needed. The original failed variant is retained in
`reports/fsm_recode_investigation/` and `reports/gate_smoke_history/` as a
historical failed case, not relabeled as passed. Neither the generic nor the
current mapped PASS establishes full formal equivalence over all states and
inputs.

The mapped failure was observed at both 50ns and 2000ns test clock periods.
The current reproducible TB uses a 2000ns period and settled comparison 100ns
after the falling edge. Explicit reads of initialized input and all four
weight banks did not remove the mismatch. The trace shows matching metadata
reads and bias assembly before the first unknown mapped next state. The
historical failure concerns the auto-reencoded/mapped flow's four-state
behavior; these observations establish neither an RTL bug nor an ASIC timing
failure.
Disabling FSM extraction/re-encoding in a separate synthesis run removes the
observed mismatch for the complete sampled tile. This is evidence supporting
that engineering flow choice; it is not a formal all-state proof.

**Local model handling and SRAM scope**

The actual standard-cell simulation file was read from the user-provided
split ZIP using the existing virtual archive reader. Only the selected file
was extracted into `local_pdk/stdcell/verilog/`. No private model was uploaded
or copied into a public repository. The `ARM_UD_MODEL` branch of the vendor
file provides uniform functional delays; these are not SS/TT/FF signoff
timing and there is no SDF annotation.

All nine SRAM instances preserve their address-width/depth parameters in the
mapped netlist: five 16x128, two 16x4096 and two 16x1024 instances. Both DUTs
use `qingyu_sram16.sv` as a synchronous behavioral SRAM substitute. SRAM macro
timing, area and power are outside this check.

**Reproduction**

From the project root with the project Python runtime and Icarus in PATH:

```powershell
python scripts/run_gate_smoke.py
```

This runs the current production mapped check, saves `reports/gate_smoke.log`
and `reports/gate_smoke.json`, and returns a failing exit code if any mismatch
occurs. The current run passes. The script verifies SRAM parameters and available cell models,
records hashes, and bounds compile/simulation timeouts. It never edits the
production RTL or the mapped netlist.

For the separately synthesized `-nofsm` netlist, run:

```powershell
python scripts/run_gate_smoke.py --no-fsm
```

This uses `reports/gate_smoke_nofsm_netlist.v` and saves a separate passing
`reports/gate_smoke_nofsm.json` and log, preserving the original failed case.
The exact local synthesis recipe is `reports/gate_smoke_nofsm.ys`; invoke it
with the project Yosys runner and project-local cache when regenerating.

The isolated generic diagnostic netlist was generated locally from
`reports/synthesis_generic_netlist.json` with Yosys `write_verilog -noattr`.
Its command file is `reports/gate_smoke_generic_files.f`, and its successful
log is `reports/gate_smoke_generic.log`. The zero-delay cell library was
generated with Yosys `read_liberty -ignore_miss_func` followed by
`write_verilog -noattr`; that private derived file stays under `local_pdk`.
Its diagnostic log is `reports/gate_smoke_libfunc.log`.

`reports/gate_smoke_comparison.json` records the separate observations,
including the current passing production output and historical failed variant,
and their relevant file hashes. These checks make no official DC/Formality,
SoC-wide equivalence, 150MHz STA or physical implementation claim.
