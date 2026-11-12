# INT8 packet engine: frozen sequential control baseline

This engine connects the frozen Rice32 codec, row-pair reorder adapter,
bounded-prefix ICB transport and complete-task Winograd core. Every external
read/write crosses the unchanged official E203 memory fabric and opt33 shared
SRAM wrapper in the integration fixture. This fixture does not instantiate
the CPU or an official initial-loader source.

The packet layout and marker rules are in `contract.json`. Each accepted START
clears the shared read cache and begins a fresh private-core epoch. After
header/range/non-overlap validation, the engine writes output word0=0 and waits
for its real ACK. Actual compressed payload prefixes and length headers follow.
The final success marker is issued only after all prior payload/header ACKs;
measurement ends at that marker's originating bus ACK, not encoder/core done.

Reproduce the complete integration tests in WSL:

```sh
python3 experiments/integration/int8stream/run_checks.py --layers 1 --fault-checks --jobs 2
python3 experiments/integration/int8stream/run_checks.py --layers 12 --core-dir experiments/arithmetic/winograd_task8_overlap --jobs 2
```

`--reuse-build` requires a passed run with identical compiled source hashes,
compiler version/options and binary hash. `--images` accepts another independently
validated twelve-layer packet set. Each run uses a fresh directory and preserves
logs, input copies and actual output dumps. Compilation uses a unique Linux
temporary directory; the resulting binary is retained with the evidence.

Both serial and output-overlap cores passed all twelve real model layers.
Each layer is followed immediately by the next layer without global reset:
24 complete tasks per core, including 153240 checked 32-bit allocation words.
All 6385 output words, including unused poisoned slots, match; source packets
are unchanged and each source word is fetched exactly once. Every request,
response and physical SRAM write is checked against the accepted official path.
Back-to-back task timings equal the corresponding standalone task timings.

| Frozen core | Mean START→final marker ACK | Range |
|---|---:|---:|
| `winograd_task8` | 22391.333333 cycles | 22389–22395 |
| `winograd_task8_overlap` | 14455.333333 cycles | 14453–14459 |

The overlap core saves exactly 7936 cycles on each layer with identical output
dump hashes and bus traffic. These are engine windows with testbench input
preload excluded; they are not CPU-inclusive or official-loader throughput.

Both core integrations additionally pass five fault modes (read response error,
bad packet header, overlapping source/output ranges, invalid compressed length,
invalid shift), in-flight hard reset, a clean restart after each failure and
random response backpressure. Failed payloads do not retain the old success
marker; malformed headers/ranges fail without destination writes. End-to-end
compile logs have no LATCH, MULTIDRIVEN or UNOPTFLAT diagnostic.

`VALIDATION.json` retains result/log identities, paired layer comparisons,
component identities and the measurement boundaries. `SOURCE_SHA256.json`
freezes this engine, its checker and selected external dependencies.

No manufacturer SRAM, new area/energy, STA, CPU integration or official-loader
acceptance is implied. Even the faster engine's current window exceeds the
14354.067-cycle limit implied by 10450 tasks/s at an assumed 150 MHz, before
adding CPU or unresolved initial-loader costs. The three acceptance targets
remain unproven. Concurrent read/write scheduling belongs to a new revision.
