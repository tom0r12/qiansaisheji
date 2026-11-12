# Official-bus validation and assessment bundle

This isolated bundle contains one frozen candidate, the unchanged official
E203 RTL and license, verified twelve-layer firmware/images, an independent
bus-path scoreboard, and full digital-SoC assessment entry points. It contains
no private PDK, audio dataset, framework installation or credentials.

The hardware path is six DMA sources → new DMA merge → new CPU/DMA merge →
original `e203_subsys_mems` → single-port shared SRAM. CPU memory requests
join the same original fabric. Control and bounded WAIT use sysfio, so a CPU
control wait does not occupy the memory fabric. The old multiport score wrapper
and old accelerator-only synthesis entry are not used.

## Validation

Unzip into a new directory, then run:

```sh
sh verify.sh --mode validate
export QINGYU_SRAM_MODELS=/storage1/admin_public_dir/SRAM_Lib_2025
export QINGYU_SRAM_MODEL_IDENTITY=/absolute/path/reviewed_macro_models.json
sh verify.sh --mode macro --preflight
sh verify.sh --mode macro --activity
```

Use `--mode behavioral` for an independent portable-memory comparison.
`--layers 1` is a bring-up option; final comparison requires twelve layers.
The runner finds `vcs` on PATH, or uses `QINGYU_VCS`. Assessment tool overrides
are `QINGYU_DC_SHELL`, `QINGYU_PT_SHELL`, and `QINGYU_FM_SHELL`.
`QINGYU_RUN_PARENT` names an existing writable parent, default `~/Desktop`.
Every execution creates a new `qingyu_verify_...` directory and retains its
inputs and logs. No historical directory is overwritten or deleted.

Copy `macro_models.example.json` outside the bundle, review the manufacturer's
distribution origin and populate all three model hashes. Only the external
`SRAM_Lib_2025` files selected by this reviewed identity are accepted. The
bundle contains no functional substitute or interface-only macro model.
`--macro-model-manifest` is the explicit alternative to the environment variable.

The manifest binds the scoreboard to the exact passed local runner kind.
opt31 uses same-edge-write command-before-response monitoring; opt32 additionally
uses accepted-descriptor FIFOs per DMA source. Its final timestamp is the real
response for the 12672th output word, not an earlier response after all writes
have reached SRAM. Later read-cache candidates are not supported by this bundle.

Before boot, the macro fixture explicitly resets the shared protocol state,
initializes ITCM/DTCM and shared memory through macro write ports, and checks
every shared write acceptance and response before releasing all forces. It
supports both same-edge and registered write acknowledgements and rejects
unknown handshakes. Runtime monitoring starts only after preload. The original fabric carries every
runtime DMA transaction. The fixture independently reads back all 25344 INT16
outputs through the physical shared-memory interface. The bus scoreboard
checks all original source/live/output addresses, response ownership and data,
and private X/W commits against an immutable `shared_image` reference, rather
than using the potentially modified live SRAM as the expected answer.

## Measurement window

The retained engineering window starts at the first CPU/source parameter read
attempt, including arbitration before its acceptance, and ends at the final
originating DMA output response. Parameter validation, staging-to-live loads,
CPU scheduling and bus waits are included. `QINGYU_ACTIVITY_START/END` record
the same cycle and time boundaries used by VCD `$dumpon/$dumpoff`.

The pre-boot testbench staging preload and CPU boot are excluded. The contest
guide requires input/parameter loading time, but the exact organizer start
signal and treatment of the initial platform write are still unresolved.
Therefore this is an engineering comparison, not an official task throughput
or energy acceptance. The organizer loader still needs integration and its
confirmed complete loading window must then replace this engineering window.
Reset time between independent tasks remains outside each task.

The guide is the provided `f8732a6ebb0442b1986eeec83a4bf6db.pdf`, physical pages
4 and 12–13: integration via System Bus or NICE, 150 MHz, total task loading
and scheduling time, full-SoC power, and incremental accelerator/interface area.
Only the selected local model tasks are included, not organizer-selected
600-sample accuracy results.

## Synthesis and area

Copy `platform_config.example.tcl` outside the bundle and fill it with reviewed
server-local inputs. The example intentionally fails until configured:

```sh
sh verify.sh --mode synth --config /absolute/path/platform_tt.tcl --preflight
sh verify.sh --mode synth --config /absolute/path/platform_tt.tcl
```

Use only the official `SCC40NLL_VHSC40_RVT_V0p1` family from
`SMIC40_2025/S40.tar.gz`, the matching approved corner and actual SRAM `.db`
files from `SRAM_Lib_2025`. Record hashes, library/area-unit provenance and
organizer-provided SRAM areas. Supply `LIBRARY_IDENTITY_FILE`, using the separate
identity example: approved archive hash, exact archive member, conversion
provenance, DB hash, internal library name and cell count. Every target DB must
match this allowlist, and loaded library name/count are checked. Unknown DBs
and known historical non-official library names are rejected. The archive's
trusted origin and archive-to-DB conversion still require server-side review;
a self-authored declaration is not third-party certification. Nothing is
automatically substituted.

Provide a complete SoC SDC: system and always-on clocks, generated/gated
clocks, selected JTAG mode, real input/output delays, loads, slew, uncertainty,
runtime mode and justified exceptions. The old one-clock block SDC is not
adequate. Synthesis fails on missing clocks/delays or unconstrained endpoints.
Interconnect estimation and library units are explicit configuration inputs.

The top is the actual `qingyu_e203_soc_top`, including CPU, original fabric,
new merges, FIO, accelerator, all private/shared/TCM SRAM and peripherals.
Hierarchy and SRAM instances are preserved for reproducible accounting.
`leaf_area.tsv` lists every mapped leaf exactly once:

| Counted in incremental area | Reported separately and excluded |
|---|---|
| FIO, accelerator, private macros | Reused E203 logic and its TCM macros |
| Six-source DMA merge and CPU/DMA merge | Original memory fabric and fixed peripherals |
| Shared-memory interface logic and remaining adapter glue | The 64 fixed shared SRAM macros |

The entire subsystem parent is never excluded because it contains the new
CPU/DMA merge. Unknown boundary glue is conservatively included. Standard-cell
area uses the verified physical-unit conversion; SRAM area uses the explicit
official macro-area table. Expected memory counts are recorded in the manifest
and checked before/after synthesis. Unexpected optimization/removal of a macro
requires investigation, not silently relaxing its expected count.

## Same-netlist timing, equivalence and power

```sh
sh verify.sh --mode sta --config /absolute/path/platform_ss.tcl --mapped-run /absolute/path/synthesis_run
sh verify.sh --mode formal --config /absolute/path/platform_tt.tcl --mapped-run /absolute/path/synthesis_run
sh verify.sh --mode power --config /absolute/path/platform_tt.tcl --mapped-run /absolute/path/synthesis_run --activity-review /absolute/path/activity_review.json
```

Repeat STA with every organizer-required corner, all using the same frozen
netlist and SDC. Formality compares this candidate's full-SoC RTL against that
netlist with this run's SVF. No historical SVF, arbitrary cut points or omitted
interfaces are used. Review failing, unmatched, aborted, unverified points and
both sides' SRAM black-box boundaries. Tool exit zero alone does not establish
timing or equivalence acceptance.

Power includes **all** CPU, original/new interconnect, accelerator, peripherals,
private SRAM, TCM and shared SRAM; area exclusions do not apply to power.
VCD is an activity input for a separate mapping/coverage review, not a power
number. The power entry requires a window-trimmed SAIF with duration equal to
the measured timestamps and a review JSON naming:

```json
{
  "activity_file": "/absolute/path/task.saif",
  "activity_sha256": "verified file hash",
  "netlist_sha256": "this mapped netlist hash",
  "start_ps": 0,
  "end_ps": 1,
  "strip_path": "manifest checker top/fixture/dut",
  "mapping_review": "accepted",
  "sram_power_review": "accepted",
  "power_scope": "full_digital_soc",
  "measurement_scope": "engineering first-parameter-read window; platform preload excluded"
}
```

Also provide `source_run`, `source_layer`, `source_result_sha256`,
`source_log_sha256`, and `source_vcd_sha256`. The runner verifies the source is
this bundle's passed physical-macro simulation, both measured activity markers
equal the requested window, and the result/log/VCD hashes remain unchanged.
The numbers above are placeholders, not usable task data. Acceptance requires
actual mapping evidence, clock coverage, annotated and propagated logic
activity, all macro read/write/output activity and real macro power models.
Unannotated logic and unmodeled SRAM cannot be assigned zero power. Reports
retain full hierarchy and unannotated signals. Confirm power units before
calculating `energy_J = average_power_W × window_ps × 1e-12` and aggregate all
twelve tasks by total time; do not combine different netlists' best metrics.

## Current readiness

This bundle prepares executable entry points and immutable inputs. Local
hash/CRC, Python/shell/Tcl syntax and structural/fixture checks do not execute
Synopsys commands or validate proprietary library contents. The real macro
simulation, full SoC mapping, complete SDC, multi-corner STA, Formality, activity
mapping/coverage and official task-loading window remain separate acceptance
gates. No new PPA result is supplied by preparing this package.
