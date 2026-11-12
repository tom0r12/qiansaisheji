# Fixed-count ICB stream transport experiment

This frozen standalone revision implements the contract in `CONTRACT.md`.
It is a reusable transport block, not an integrated accelerator candidate.
`qingyu_icb_stream.sv` connects one read stream and one write stream to one
ordered 32-bit ICB master. The test uses the unchanged official E203 memory
fabric and frozen opt33 shared-SRAM wrapper. No fabric source or parameter is
modified and there is no shared-memory bypass.

Run from the project directory in WSL:

```sh
python3 experiments/transport/icb_stream/run_checks.py
```

Icarus performs four-state simulation; Verilator checks the standalone RTL
with `-Wall`. The runner verifies pinned vendor hashes, frozen slave identity
and all sources before/after the run, and writes a unique build directory.
Full evidence: `build/icb_stream/20261111T164456740217Z/result.json`.
The small tracked summary and hashes are in `VALIDATION.json`.

The final matrix has 4/8 credits, three seeds and two response paths:

- Native official return path: measured bandwidth and protocol tests.
- An extra **testbench-only** return-delay FIFO: fills all configured credits
  and exercises full FIFO pop/push. Its timing is excluded from bandwidth claims.

All 444 scenarios pass. They cover read/write/mixed descriptors, full read FIFO,
request/output/completion stalls, first/middle/final errors, held-request drain,
soft abort before/with traffic, early and missing `last`, hard reset, clean
restart, valid last-address access and invalid descriptors. Standalone RTL
lint reports zero warnings or errors in both credit configurations.

Native-path deterministic cases (same in both credit configurations):

| Work | Shared command interval | Descriptor-to-completion cycles |
|---|---:|---:|
| 1024 sequential reads, initially cold | 1024 cycles across 1023 intervals | 1031 |
| 1024 writes | 1023 cycles across 1023 intervals | 1030 |
| 1024 reads + 1024 writes | 2048 cycles across 2047 intervals | 2054 |

The first read misses; subsequent reads use the slave's adjacent-word cache.
Writes and read hits can complete at their real accepting SRAM edge. These
numbers include the literal official fabric's buffers and response return.
The native stress test observes at most four in-flight transactions with four
credits and five with eight credits; the extra testbench return FIFO verifies
the engine's full eight-credit state. Eight native outstanding transactions
are not claimed.

Data FIFO capacity is 16 read words plus 8 write words (96 data bytes), with
separate owner/last descriptors and held-command state. No whole tile is held.
This revision requires the exact write count in advance; compressed streams
whose count is only known at encoder `last` require the separate prefix revision.

These are synthetic transport tests, not real-KWT arithmetic, complete-task
throughput, official-loader compliance, SRAM timing, area, power or STA results.
The shared wrapper performs extra speculative reads; their energy is not free.
An abort preserves already offered bus requests and prior successful read words;
the consumer must drain those words before error completion. Accepted writes
cannot be undone. The parent project's three acceptance targets remain unproven.
