# Native Verilator SoC simulation

The project-local native toolchain is extracted from the official
[MSYS2 package repository](https://repo.msys2.org/mingw/mingw64/), under
`tools/verilator/mingw64`. No system-wide compiler or PATH setting is changed.
Downloaded package names, versions and hashes are in
`tools/verilator_packages/installed_packages.json`; archives remain local.
Verilator 5.050 and GCC 16.2.0 were selected. The existing GCC 8.1 cannot
compile this timing model because Verilator timing support requires C++20
coroutines, as described in the [official timing documentation](https://verilator.org/guide/latest/languages.html#time).

`scripts/run_soc_verilator.py` reuses the existing `tb_qingyu_soc` testbench,
official E203 RTL, augmentation, compiled firmware and shared-memory vectors.
The same testbench checks all 25,344 outputs; the script reports success only
after the checker emits its PASS marker. `--timing` retains delays and event
controls. The common 1ns/1ps timescale fixes upstream models that contain
unqualified simulation delays, matching the Icarus flow's timescale setting.
The 150MHz high clock and 32.768kHz AON clock of the production testbench are
retained. This is functional RTL simulation, not static timing closure.

From the project directory:

```text
python scripts/run_soc_verilator.py --layer 0 --vectors tb/vectors
```

Preparation calls `run_soc.py --build-only` to rebuild firmware and matching
input images. Use `--skip-prepare` only when those files already match the
requested layer/vectors. Use `--build-only` to create the native simulator,
or `--skip-build` to reuse it; the latter checks all HDL file hashes against
the build manifest. `--jobs` controls parallel C++ compilation (default four),
and `--timeout` limits runtime. Build stages allow at least 300 seconds.

The runner sets `VERILATOR_ROOT` and prepends the project tool directory only
in its child-process environment. It uses the existing local mingw32-make,
Git Perl and bundled Python with explicit make-variable overrides. Alternate
paths can be supplied with `--make`, `--cxx`, `--verilator` and `--gcc`.
Both generated C++ and runtime logs stay under `build/verilator_soc` and
`build/*verilator*.log`; successful checks produce
`reports/soc_verilator_result.json`.

Tool installation or C++ generation alone is not a passing SoC test. Numerical
accuracy, source provenance, official SRAM models, total area, timing and
power require their separate verification flows.

## Standalone full-matrix regression

The same runner also compiles `tb_qingyu_accel` at the full 99x64x256 sizes:

```text
python scripts/run_soc_verilator.py --rtl-only --all-layers --vectors tb/vectors
python scripts/run_soc_verilator.py --rtl-only --all-layers --skip-build --vectors model/full_v2_run/validation_vectors
```

The second command requires that the model extraction already produced and
froze all twelve layer directories. Each invocation checks all directed
edge/control cases and all 25,344 external matrix outputs. It never modifies
the firmware/shared-memory files. `reports/rtl_verilator_result.json` lists
individual layer results, vector-file hashes and the total output count.
Input files changing during a run invalidate its result. The original
compiled model is reused only if the RTL and testbench hashes still match.

For repeated full-size RTL regression, the `--rtl-only --all-layers
--skip-build` command above is the quick path: it reuses the compiled checker
and normally takes under a second per layer on this machine. Remove
`--skip-build` after changing the RTL or testbench. Preserve the matching
vector manifests when comparing runs.

The native production SoC run passed all 25,344 outputs using synthetic
layer00 data in 107.91 seconds, with the original AON clock and all timing
controls retained: 3,710,460 external clock cycles and 2,466,208 driver task
cycles. This is functional integration evidence, not a KWT accuracy result.
The standalone full-size synthetic layer00..11 regression passed 304,128
external outputs in about nine seconds after its 14.9-second C++ build.
Real frozen model vectors have a separate run and provenance record.
The frozen `model/full_v2_run/validation_vectors` layer00..11 regression also
passed all **304,128** outputs against the integer model, using one exported
held-out validation input per layer. This does not substitute for the wider
256-sample software precision evaluation or the official 600-sample set.
