# Full diagnostic queued-loader corpus

`run_corpus.py` invokes the frozen `../run_profile.py` without changing it. It
uses the two existing validated queued binaries with frozen bounded codec,
prefetch8/task9, original vendor fabric and opt33 shared wrapper. There are two
masters and a four-entry merger; ONE_PER_PORT00 is a conditional producer
capability assumption, not current E203 or an identified official loader.

Samples000/009/031/127/202/255 each cover twelve layers. For each core there are
72 unique primary tasks; every primary is case id1 of a fresh simulator process
after coordinated reset. Loading is real bus traffic, starting at first source
write offer and ending at the final originating magic ACK. Subsequent cases are
functional/control checks and never enter the cold throughput mean.

| Core | Cold cycles, six-diagnostic mean | Transaction floor | Excess | Conditional tasks/s at unverified150MHz |
| --- | ---: | ---: | ---: | ---: |
| Prefetch8 | 14615.7361 | 13881.3472 | 734.3889 | 10262.91 |
| Task9 | 14463.1944 | 13881.3472 | 581.8472 | 10371.15 |

All144 primary tasks and all576 normal/control cases pass full output/source/
131072-word guard checks. Each transaction floor is `2*input_words +
unique_output_words + 1`; it includes real initial writes, subsequent source
reads, encoded output and completion-marker invalidation. All cycles partition
into accepted commands,26 fabric-blocked cycles and the remaining no-offer
cycles. Per-task values and original report hashes are in `VALIDATION.json`.

These six samples are deliberately selected diagnostics. Sample009 is generated
silence and202 is a known high-traffic sample. Their average is not an unbiased
population mean or an official result. No E203/official-loader, STA, area,
energy or manufacturer SRAM proof is supplied by this fixture.

The frozen01 controls are available for000/009/202 only. `VALIDATION.json`
compares these common samples explicitly; it does not invent01 measurements
for the other three samples.

`audit_metadata.py` independently round-trips exact integer metadata from all
72 packets. Each layer's values are identical across the six samples. A generic
lossless packed representation uses signed13/14-bit bias and4-bit shift:
average50 source words saved without a new format word, or49 with one added
format word. The latter lowers the transaction floor by98 cycles. The original
packets, numerical calibration, codec and RTL are unchanged.

At150MHz,10450task/s corresponds to14354.067 cycles. Task9's diagnostic mean is
109.127 cycles above it. If metadata packing reduced elapsed cycles by exactly
98, it would still be11.127 cycles above it. This is a budget scenario, not an
implemented speedup. A parser must preserve the existing metadata throughput,
signed extension, byte layout, ready/valid stability and fault/drain boundaries.
An extra reservoir/control delay could erase much of the benefit. A small
lossless parser is worth a separate measured experiment; expanding MAC count
alone cannot remove the transaction floor.

Reproduce from WSL project root, with two simulations and no recompilation:

```sh
python3 experiments/integration/streaming_loader_study/test_queued_corpus/run_corpus.py --workers 2
```

The orchestrator requires exact previous binary/compiled-source/options hashes.
`audit_metadata.py` rechecks metadata packing and `summarize.py RESULT.json`
revalidates retained provenance and creates the stable summary/source manifest.
