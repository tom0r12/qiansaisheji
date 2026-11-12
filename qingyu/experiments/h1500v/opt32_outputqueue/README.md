# opt32_outputqueue

Experimental child of frozen opt31_fastwrite. The selected project candidate
remains opt30_fusedpipe4. Only FIO output issue/retirement and DMA merger port 2
ONE_PER_PORT change. Official E203 fabric source and FIFO parameters, CPU,
shared SRAM wrappers, accelerator arithmetic, firmware and data are unchanged.

The output port accepts up to four ordered writes. output_issued and the
address advance on real command acceptance, consuming one stream word.
word_number retires only on real responses. A result slot is released only
after its final successful response; no fabricated acknowledgement is used.
Batches drain completely before the next slot starts.

mem_inflight replaces the old pending bit for port 2. Errors and software reset
stop new offers, preserve already offered payloads, and drain accepted traffic.
Held-output identity prevents a late accepted old write from popping a reset
stream. Sticky errors block restart until quiet plus a clearing reset. The
other five DMA sources remain single outstanding; the merger still has four
total entries and the official splitter remains unchanged at one outstanding.

Reproduce in WSL from qingyu:

```text
python3 scripts/run_outputqueue_checks.py --candidate opt32_outputqueue
python3 scripts/run_bus_outputqueue_candidate_soc.py --candidate opt32_outputqueue --layers 12 --jobs 2 --images build/model_headroom1_20261111/soc_images_out16 --data-kind KWT_VALIDATION
```

The first test uses an explicitly synthetic independent stream: two 99-row
tiles, three-row tail, four credits, sustained actual accepts, random stalls,
held payloads, first/middle/final response errors, 0/1/4-inflight software reset,
hardware reset, concurrent metadata error, drain and full restart. The real-FIO
fault, concurrent-owner, fused-input and bounded-WAIT suites also apply.
The SoC checker uses the actual arithmetic and immutable model outputs, with
per-port accepted-descriptor FIFOs. Timing ends at the true response for the
12672nd output write, even if all SRAM writes finished before earlier responses
returned to the originating port.

This engineering window includes validation and source-to-live cold copies,
but excludes testbench source preloading. Official loader timing is still open.
No official throughput, area, energy, STA or 600-sample accuracy is claimed.
This alone cannot reach 10450 full tasks/s with current INT16 traffic and the
four-row arithmetic. Refer to run result.json files for actual verification.
