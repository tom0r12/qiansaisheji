# Independent read-ahead checks

Run with a four-state Icarus installation, from this directory or the repository:

```sh
python3 experiments/memory/read_ahead/run_checks.py
```

The runner compiles once and executes ten fixed seeds, stops on the first failure,
and records commands, logs, metrics, and before/after source hashes in a new
`runs/<UTC timestamp>/` directory. `--seeds 17` is a quick directed/random smoke.
No existing run is overwritten. RTL is owned separately from this testbench.

The physical RAM and golden memory are independent arrays. The RAM follows only
the public RAM pins; the golden memory follows only accepted ICB commands. The
expected response FIFO is populated before checking same-edge responses. Every
word is initialized before any read. Every RAM write, including mask zero,
poisons Q with X. An implementation that wrongly relies on write-Q retention
therefore fails in four-state simulation.

| Contract | Directed / monitored evidence |
|---|---|
| Writes commit at acceptance, even if response is stalled | All 16 masks with six-cycle stalls; every RAM write checked for an owning accepted ICB command, address, mask and data |
| Responses retained under backpressure | Exact data/error/valid stability on every held cycle; random stalls can last up to 37 cycles |
| No second command accepted with pending response | Accepted-command FIFO occupancy checked on every edge |
| Exact ready behavior | Idle and not clear must offer ready; pending response must suppress ready |
| Alias and unrelated writes after a prefetch | Immediate offered write meets fresh prefetch Q; all masks; alias invalidates and unrelated write preserves the next-word hit |
| Cold clear preserves accepted responses | Clear during a miss, a held cache hit, held write and invalid read; next eligible read must miss |
| Clear suppresses new commands and all RAM operations | Continuous protocol assertions, including random clear with a held offered command |
| Correct range and alignment | Below/above shared range, unaligned read/write, first/last word, macro-bank boundary; invalid commands must cause no RAM operation |
| No end-of-region speculative wrap | Last-word miss causes exactly one RAM read; first word afterward must miss |
| Sequential initiation interval | 1,024 continuous reads; every warm gap equals one cycle; exactly 1,025 macro reads counts the unused final speculation |
| Reset does not clear SRAM | Pending read is explicitly aborted by global reset; next read misses and returns retained memory contents |
| Multi-stream correctness | Random sequential, two-stream and random-address reads/writes, mixed invalid accesses, masks, backpressure and clear; no assumed hit-rate requirement |
| No hidden storage corruption | Every physical RAM word compared with independent golden memory at completion |

This is a standalone controller check. It does not demonstrate original-fabric
throughput, real SRAM macro timing, 150 MHz STA, area or energy. The speculative
RAM reads are reported separately and must be included in subsequent power
activity. SoC integration still needs explicit task-cold cache-clear wiring and
an unchanged complete-task timing window.

Latest completed run: `runs/20261111T160015834129Z/result.json`, all ten seeds
passed with an empty `-Wall` compile log and unchanged source hashes. Result
SHA-256: `e9f7cb82faad3217ccc79092f1c11b39266e47763c09b888231d4e017291add5`.
Each seed checked 3,570 accepted commands, 3,569 consumed responses and one
explicit global-reset abort. The 1,024-read sequential phase has a first-to-last
acceptance span of 1,024 cycles, warm maximum gap of one cycle, and 1,025 actual
RAM reads including its last unused lookahead. These are controller metrics,
not SoC task throughput.
