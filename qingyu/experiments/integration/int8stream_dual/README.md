# Concurrent INT8 packet engine

This experimental revision separates input loading from output retirement.
After the unchanged cold BEGIN/header/layout/magic-invalidation sequence,
the reader advances X and eight W/metadata groups while the writer encodes
sixteen output tiles. Existing bounded transport, codec and row-pair buffers
provide prefill; no whole-layer or whole-tile data buffer is added. Private
W/metadata writes still require the selected core's actual ready handshake
and current load-group identity.

Every shared access crosses the unchanged official E203 memory fabric and
opt33 SRAM wrapper. The final marker waits for all input loading and every
payload/length response. The measured end is its real originating ACK.
Source preload is outside this fixture's START window; CPU scheduling and
the unresolved official initial-loader boundary are not included.

Reproduce in WSL, using two compile jobs:

```sh
python3 experiments/integration/int8stream_dual/run_checks.py --images build/int8_packet_corpus_20261112/sample009 --layers 12 --fault-checks --jobs 2
python3 experiments/integration/int8stream_dual/run_checks.py --images build/int8_packet_corpus_20261112/sample202 --layers 12 --core-dir experiments/arithmetic/winograd_task8_prefetch --fault-checks --jobs 2
python3 experiments/integration/int8stream_dual/run_lint.py --core-dir experiments/arithmetic/winograd_task8_prefetch
```

`--reuse-build` accepts only a passed run with identical compiled source,
options, tool version and binary identity. `--core-dir` defaults to the frozen
overlap core; selecting the prefetch core is explicit. The runner verifies all
packet/dependency manifests and source stability around compilation/execution.

Each selected core passed three complete twelve-layer packet sets, with a
second task immediately following each task without global reset: 72 normal
tasks and 459720 checked output allocation words per core. Every source word
and all 6385 output words, including unused poison, are checked. Output dump
hashes and architectural traffic match the frozen sequential-engine baseline;
input words match exactly (some retained files differ only in line endings).

| Sample | Sequential + overlap mean cycles | Dual + overlap | Dual + prefetch | Prefetch range |
|---|---:|---:|---:|---:|
| 009 | 14455.3333 | 14129.7500 | 10071.7500 | 10071–10073 |
| 202 | 14458.5833 | 14130.0000 | 11612.6667 | 11301–11862 |
| 000 | 14456.1667 | 14129.8333 | 10561.9167 | 10432–10677 |

Sample202 was selected by the corpus exporter for maximum input/output/total
flow among the original 3072 tasks. Its larger prefetch-engine latency is
retained, rather than extrapolating sample009's fast result to all inputs.
Back-to-back timings equal the corresponding standalone layer timings.

Both core configurations passed seven error scenarios, two in-flight hard
resets, random response stalls and clean restart after every failure on samples
009 and202. The added cases inject read/write errors while both descriptors
are active and output writes have already retired. Independent accepted-read
and accepted-write counters track ownership and actual overlap. Normal
prefetch tests also exercise mixed-owner outstanding transactions.

A directed late write error exposed a circular wait in the initial dual
revision: retained read data needed a core consumer, while the failed writer
prevented core progress. It eventually recovered only through the two-million
cycle watchdog. That diagnostic result is preserved and is not bounded-error
recovery evidence. The final RTL enters abort on the actual error-response
handshake, resets both private stream endpoints, preserves held bus commands,
and drains all accepted responses and retained read words. The final checker
requires error code0x10 and completion within200 cycles of that ACK. Failed
payloads leave marker0; malformed headers/ranges do not write any output.

Strict `--Wall` lint passes with zero warnings for both actual core selections.
`VALIDATION.json` retains exact result paths/hashes, comparisons, fault evidence
and the superseded diagnostic. `SOURCE_SHA256.json` freezes the final source
and both selected external core/component identities. Existing sequential
engine, official fabric, codecs, transport and candidate sources were unchanged.

These are local RTL engine results. Manufacturer SRAM execution, physical
area/energy, STA, complete CPU integration and official-loader acceptance are
not established by them. The project's three acceptance targets remain unproven.
