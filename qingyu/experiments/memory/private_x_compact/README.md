# Optional compact private-X SRAM mapping

This experiment replaces only the physical implementation of the existing private `qingyu_sram16` instances configured as 1024×16. The frozen compute cores, arithmetic, X load order and read schedule remain unchanged. The 128×16 W/R/metadata instances retain their original direct macro wiring; no register array replaces SRAM data.

The nine-row core uses addresses0..351 per logical X bank, mapped to three actual `RAMSP128X16` cells. Prefetch8 needs addresses0..415 and uses four cells. The low seven address bits select the word and bits9..7 select the macro page. Only the selected page is enabled on an access. A three-bit page selector captures the same clock edge as the macro read; its16-bit output mux does not add another pipeline register. A real150MHz timing result is still needed for the new mux and enable decode.

There is deliberately no new reset interface. The original wrapper and SRAM contents have no reset; output is unspecified before first access. A reset of the unchanged core invalidates the task epoch, not memory cells. Writes expose the selected macro's unspecified write-Q behavior; the local functional model drives X after1ns. Disabled accesses preserve selection and activate no macros. Addresses beyond the configured valid range activate no macro, do not alias writes, and select zero output after the edge. Such accesses remain illegal for the core and are checked independently in the integration monitor.

| Core | Original private macros | Compact private macros | Original bits | Compact bits | New selector FF |
| --- | --- | --- | ---: | ---: | ---: |
| prefetch8 | 8×1024×16 +21×128×16 | 53×128×16 | 174080 | 108544 | 24 |
| task9 | 9×1024×16 +21×128×16 | 48×128×16 | 190464 | 98304 | 27 |

The table counts physical storage capacity, not square millimetres. Compact task9 allocates fewer total storage bits than compact prefetch8 because99 rows divide exactly into nine banks, but still has the extra16 paired lanes and larger output context. The new logic also includes one constant range comparison and page-enable decode per bank, plus16bit3/4-way output selection. Macro clock pins all remain connected to clock; only their CEN differs. Clock loading, disabled-macro power and mux power require the actual cell models.

Area improves only if `27*A128 + added_logic < 9*A1024` for task9 or `32*A128 + added_logic < 8*A1024` for prefetch8. The unchanged21 small macros cancel. A stored-bit reduction alone cannot establish either inequality; no area, energy or timing gain is claimed.

Run independently under WSL/Linux:

```sh
python3 experiments/memory/private_x_compact/run_checks.py --cases 12
```

This covers all twelve frozen real tasks and the original reset/stall/error recovery suite. `--unit-only` restricts execution to wrapper tests. The runner uses existing frozen inputs and explicitly local RAMSP functional stand-ins, verifies their hashes, records all commands/logs and counts elaborated macro instances. These models have the actual ASIC pin interface and one synchronous read with write-Q poison; they are not manufacturer models. The original `scripts/run_int8_private_macro_checks.py` is not edited.

Local verification is complete: `build/private_x_compact/20261111T181817149970Z/result.json` passed (SHA256 `34cec5c85e05372a53268268c23fea1466ade3ed976c88ff03d9d91a0b9aeabe`). Each of three wrapper seeds passed5380 operations across both compact configurations and the unchanged128 path, including every valid and unused address, bank transitions, writes, reads and idle holds. Unsupported parameters were rejected as intended. Both wrapper configurations passed strict Verilator lint with only filename/unused-model-pin diagnostics disabled.

Each full-core four-state run passed12 frozen real tasks plus the original recovery suite:23 successful tasks,7 interrupted tasks,2 expected errors and8 resets. Task9 checked604512 pre-RNE results and retained9355 fast cycles; prefetch8 checked604400 and retained9931. Both exercised a metadata fault while a published output context remained held and recovered cleanly. Original cores/TBs/vectors were unchanged and checked by hash before/after. The added observer checked every actual X address and selected macro CEN. Icarus reports its known frozen-core `always_*` sensitivity-list warning; it expands sensitivity and is not a waived functional failure.

The elaborated core builds contained exactly48 and53 `RAMSP128X16` instances respectively, with zero1024/4096 instances. These counts include the unchanged21 W/R/metadata macros. The12 real tasks are the frozen sample9 generated-silence slice (304128 unique output elements per mapping), not the official evaluation; independent wrapper tests supply full-address/random16bit data coverage. `VALIDATION.json` records this scope, the intentional unsupported-parameter failure and the initial runner preflight typo repaired before any RTL compilation. No arithmetic or RTL fix was needed to pass.

This optional mapping is not selected into a production candidate. Final adoption requires same-candidate official-library macro area, actual macro functionality,150MHz STA and whole-SoC power comparison.
