# Bounded-prefix ICB stream transport

This revision adds last-terminated writes to the frozen fixed-count engine in
`../icb_stream`. Its exact interface and drain rules are in `CONTRACT.md`.
The fixed revision and its 444-scenario evidence remain unchanged.

Set `wr_desc_prefix=1` when compressed output length is initially unknown.
`wr_desc_count` then reserves a maximum of 1..398 words. An accepted input
`last` records the actual prefix length and stops accepting more input. Only
that prefix is written. Completion waits for its final real bus ACK; the
encoder's `last` alone is insufficient. If the bound is reached without `last`,
the malformed word is not queued and all previously offered/accepted traffic
drains to an error completion. `wr_desc_prefix=0` retains exact-count behavior.

The original 16-word read FIFO and 8-word write FIFO remain 96 data bytes.
There is no 398-word tile buffer and no padding write to unused slot words.
The integration controller must still write the actual bit-length headers and
then acknowledge the final completion magic, as specified in
`experiments/integration/int8stream/contract.json`.

Reproduce from the project root in WSL:

```sh
python3 experiments/transport/icb_stream_prefix/run_checks.py
```

Final evidence: `build/icb_stream_prefix/20261111T165135375437Z/result.json`.
Tracked summary: `VALIDATION.json`; frozen source identities: `SOURCE_SHA256.json`.
All 660 scenarios pass (55 cases × three seeds × four configurations).
The two credit configurations both pass standalone Verilator `-Wall` with
zero warnings or errors. All 37 fixed-mode scenarios per configuration have
identical metrics to the frozen fixed engine under the same seeds.

The additional prefix cases cover lengths 1, 397 and 398 in a 398-word slot,
the 1-word maximum, concurrent reads, first/middle/final response errors,
missing final `last`, abort and clean restart, malformed maxima 0/399, and
full-range bounds. The test reads back every slot word, including untouched
suffix words. A 397-word native-path prefix uses 397 actual commands and ACKs,
with 396 shared command intervals and 403 total test cycles; the unused word
is not written. The 1-word prefix uses one command/ACK and seven test cycles.

Only native official-fabric response timing is used for bandwidth. A separate
testbench-only return-delay FIFO exercises the full eight-credit state and
simultaneous full FIFO replacement; it is absent from the RTL and is excluded
from bandwidth claims. The original official fabric source and parameters,
and frozen opt33 shared wrapper, are verified by hashes before running.

These are synthetic standalone transport tests. No integrated Rice32/core
task, real KWT arithmetic, complete-task target, official loader scope, area,
energy, SRAM timing or STA result is claimed. Successful buffered read words
must still be consumed during abort; already committed writes cannot be undone.
