# Producer-credit profile

`PROFILE_VALIDATION.json` rechecks eight independent runs and their source,
packet, binary, log and output hashes. The four ONE_PER_PORT01 controls reproduce
every metric in the first four cases of the corresponding frozen baseline run,
not just the primary cycle count. The original fixture and results are unchanged.

The sole control difference within a core/sample pair is the compile-time merger
parameter ONE_PER_PORT01 versus00. Both use two existing ports, OUTSTANDING4,
unchanged merger RTL, unchanged official fabric/parameters and one shared slave.
00 models an unknown queued platform producer; it is not current E203 behavior
or an identified official loader. It does not acknowledge writes early: source
commit still advances only on successful originating write responses.

| Core / layer0 sample | Transactions | 01 cold cycles | 00 cold cycles | Saved | 00 excess over service floor |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prefetch8 / 000 | 13550 | 15286 | 14215 | 1071 | 665 |
| Prefetch8 / 202 | 15230 | 17374 | 16004 | 1370 | 774 |
| Task9 / 000 | 13550 | 15180 | 14109 | 1071 | 559 |
| Task9 / 202 | 15230 | 17196 | 15826 | 1370 | 596 |

Only case id1 after coordinated reset is used here. The table is two diagnostic
layer0 tasks, not a dataset mean. All 6385 output words, all input words and the
complete 131072-word shared guard are checked. Each queued core also passes
the sample202 extended suite: eleven delayed-ACK boundaries, future-poison
prefetch/write coherence, random stalls, four expected producer faults,
coordinated reset and clean restarts.

For prefetch8/sample000, 01's 15286 cycles partition exactly into 13550 command
acceptances, 25 fabric-input blocked cycles and 1711 cycles with no routed offer.
00 partitions into the same 13550 acceptances, 26 blocked cycles and 639 cycles
with no routed offer. It removes 1072 idle cycles while adding one blocked cycle,
for 1071 cycles saved. Sample202 similarly removes 1371 idle cycles and adds one
blocked cycle. The effect is identical for both cores.

The isolated serial producer control measures `2*I+1` cycles with01 and `I+2`
with00 from first offer through final producer ACK. Thus the existing fabric can
carry real writes each cycle; the one-outstanding producer restriction accounts
for the two-cycle isolated write rate. The streaming producer competes with DMA,
so it does not finish all writes at that isolated rate. These serial controls
are not cold-before-first-offer throughput results.

For the same two samples, source-read hit rates are4707/4732 (99.47%) and
5009/5034 (99.50%). Both policies issue exactly25 read misses and respectively
4757/5059 physical reads; prefetch overhead is counted. Read misses account for
only25 or26 blocked-fabric cycles. The remaining queued idle cycles lie mainly
after producer completion: decoder/core/encoder task tail and final response
drain. Other load/output stall counters overlap; summing them would invent a
performance decomposition.

Task9+00 occupies96.04% and96.23% of cycles with actual commands. Its residual
559/596 cycles bound the possible scheduling gain for these tasks if traffic
and this one-command-per-cycle port remain fixed. Sample202's15230 transactions
alone exceed the14354.07-cycle budget corresponding to10450tasks/s at150MHz;
this is a per-task observation and does not determine the official average.
Reducing the entire remaining idle tail cannot change that task's service floor.

Reproduce one control (WSL, project directory):

```sh
python3 experiments/integration/streaming_loader_study/run_profile.py \
  --images build/int8_packet_corpus_20261112/sample202 --layers 1 --jobs 2 \
  --core-dir experiments/arithmetic/winograd_task9
```

Add `--queued-loader` for the independent00 capability assumption, and
`--fault-checks --seed 5131` for its extended suite. The default remains01.
`test/summarize_profile.py RESULT... --output OUTPUT.json` compares all source
hashes and verifies that only the producer-credit compile parameter differs.

The next useful decisions are the actual loader's supported outstanding count,
the full input/output traffic distribution, and codec/stream-tail costs. This
experiment establishes no area, energy, 150MHz timing or official-loader result.
