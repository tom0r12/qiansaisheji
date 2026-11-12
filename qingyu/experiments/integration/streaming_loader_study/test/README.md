# Conditional loader validation

This is a same-clock producer model at the existing CPU-side merger port, not
E203 firmware or an identified organizer loader. The original merger is NP=2,
OUTSTANDING=4, ONE_PER_PORT=01; the vendor memory fabric and its parameters are
unchanged. Every source write, source read and output write crosses that fabric.

`VALIDATION.json` retains six completed runs: sample000, sample009 and sample202,
all twelve layers, with frozen prefetch8 and task9 cores. Its primary statistic
uses only case id1 in each fresh simulator process, after coordinated reset and
before any source writes. Consecutive cases and serial-loading controls are
functional/control evidence; their previous private epoch is only cleared at
START, so they are not classified as cold before the first loading offer.

| Sample | Prefetch8 cold mean cycles | Task9 cold mean cycles |
| --- | ---: | ---: |
| 009, generated silence | 14547.6667 | 14243.25 |
| 000 | 15596 | 15502.25 |
| 202, high traffic | 17559.5 | 17391.75 |

These include the first real producer offer through the final originating
completion-marker ACK. Reset precedes this interval. At every normal task all
131072 shared words are compared against an independent reference, including
the immutable source and all 6385 allocated output words/unused poison slots.
Exact transactions are `2*input_words + unique_output_words + 1`; the extra
write invalidates the prior completion marker and has a real response.

Four first-layer extended suites cover delayed ACKs at eleven descriptor
boundaries, an actual speculative read of future poison followed by a producer
write, random offers/responses, four expected producer faults, coordinated
reset while traffic is pending and complete clean restarts. Producer errors
are injected at the producer-observed ACK or loader_fault sideband. The actual
fabric error wires remain unchanged; this does not prove fabric error routing.
Active error-to-done latency is bounded by the test, and accepted/offered traffic
must drain. The initial idle fault must not start or complete a task.

Reproduce in WSL from the project directory (jobs=2):

```sh
python3 experiments/integration/streaming_loader_study/run_checks.py \
  --images build/int8_packet_corpus_20261112/sample009 \
  --core-dir experiments/arithmetic/winograd_task8_prefetch \
  --layers 12 --fault-checks --jobs 2
```

Use sample000 and sample202 for the other packets, or replace core-dir with
`experiments/arithmetic/winograd_task9`. A completed build directory may be
passed with `--reuse-build`; exact source/options/binary hashes are checked.
`test/summarize.py RESULT... --output OUTPUT.json` rechecks all retained source,
packet, binary, log and output hashes and never edits the original results.

This is a diagnostic three-sample set, not the 256-sample distribution or
official 600-sample evaluation. No manufacturer SRAM, STA, area or energy result
is implied. The 150 MHz conversion is conditional and not signoff.
