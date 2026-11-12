# Bounded-history Rice32 codec

This independent source alternative preserves the frozen Rice32 format and all original ports/module names. Select these two RTL files in the file list in place of `experiments/codec/rice32/rice32_{encoder,decoder}.sv`; do not compile both definitions together. The original directory is unchanged.

The intended integration uses four symbols per accepted beat:

| Stream | Direction | Delta | Row bytes | History capacity |
| --- | --- | --- | --- | --- |
| X | Decode | Enabled | 64 | 64 bytes |
| W group | Decode | Disabled | 32 | No history access |
| Y tile | Encode | Enabled | 16 | 16 bytes |

`HISTORY_BYTES` is a power-of-two parameter in the range 16 through 256. Defaults are 16 for the encoder and 64 for the decoder. For delta mode, the original legal row sizes remain 16, 64 and 256, with the additional requirement that the row fit the selected capacity. An invalid or oversized delta row produces the existing sticky error and finite completion without waiting for input. Non-delta W with row size 32 remains supported. A caller needing a larger delta row must explicitly choose an adequate capacity.

The RTL declares the actual arrays with the bounded capacities and uses `$clog2(HISTORY_BYTES)`-wide history indices. It does not depend on synthesis discovering unused entries in a 256-byte array. The first row after each START bypasses old history and overwrites its locations; uninitialized or previous-task history is never a source of first-row data. No history clear traffic or extra frame cycles were added.

The two history arrays contain 640 data bits in total: encoder 128 plus decoder 512. The original pair contained 4096 bits, so the declared retained history data reduction is 3456 bits. The block buffers, reservoirs, arithmetic and other protocol state are unchanged. This is a state inventory, not a measured cell-area or energy result. No STA or physical PPA has been performed for this alternative.

## Verification

The runner verifies the immutable original source manifest and frozen global format before generating fixtures. Original RTL is copied into the run directory with only its module identifiers renamed. Both versions then receive exactly the same input and backpressure. Every supported transaction is checked cycle by cycle for ready, valid, payload, last/count, busy, completion, errors and counters; expected bytes/bits are additionally checked against the frozen software writer and the independently parsed packet corpus. Unsupported capacity tests deliberately disable the original shadow comparison and verify the new finite rejection behavior.

Full regression uses the preregistered 72-task corpus, six diagnostic samples across all 12 layers. Its 1800 streams contain X, all eight W groups, and all sixteen Y tiles for every task. X is decoder-only because the specialized encoder is for 16-byte Y rows; W and Y are checked in both directions. The corpus includes speech, silence and the previously selected worst-traffic sample; it is not a replacement for the official evaluation dataset and is not used for calibration or codec fitting.

Together with independent short/tail, all-eight-k, repeated-row and extreme-symbol cases, each seed checks 1952 valid fixtures, both unstalled and with random/sustained backpressure, plus 20 error cases and four reset scenarios. Errors include raw-escape canonicality, unary range, truncation, declared length, padding, missing last, malformed input count, held outputs, zero length and over-capacity rows. Reference comparison also checks error/recovery behavior for the original supported configurations. Strict Verilator RTL lint and XML elaboration confirm zero warnings and physical history dimensions of 16 and 64 entries. The alternative four-state Icarus quick run checks 72 valid fixtures plus the same error/reset scenarios.

Run from a Python environment with NumPy, Icarus and Verilator installed:

```sh
python3 experiments/codec/rice32_bounded/run_checks.py
python3 experiments/codec/rice32_bounded/run_checks.py --quick --sim iverilog --seeds 17
```

Each invocation creates a fresh `runs/<UTC timestamp>` directory. The source freeze manifest identifies the final full result and four-state quick result, their hashes, and every file in this alternative. The runner preserves logs, expected vectors, renamed references, elaboration XML and source/provenance hashes. No frozen baseline, numerical configuration, packet format or bus parameter is modified. Supported codec service cycles remain identical to the original; reduced state does not establish a whole-task throughput, area or energy target.
