# Rejected Yosys encoder inventory: behavior audit

The encoder inventory from `build/int8_structure/20261111T180353162824Z` is **not equivalent to the source RTL and must not be used as area or resource evidence**. Both original and bounded encoders are affected. No frozen RTL or original inventory file was changed by this audit.

The audited tool path is sv2v 0.0.13 followed by Yosys 0.33. The original SystemVerilog and the sv2v-converted Verilog each pass the same independent four-state miter. Yosys' generated Verilog fails the first frame. This isolates the behavioral loss after sv2v, not a numerical codec error or a real elimination of unused history/block memories.

| Candidate | Original SV | sv2v Verilog | Yosys optimized Verilog |
| --- | --- | --- | --- |
| Original encoder | PASS: 66 frames, 1093 outputs, 380 held checks | same PASS | FAIL first frame |
| Bounded encoder | same PASS | same PASS | FAIL first frame |

The miter compares all ready/valid/control signals, payload/count/last and counters each cycle against the frozen source. It includes every k0..7, raw/Rice selection, row16 delta, short and odd tails, sustained backpressure, reset and a new epoch. An additional independent golden checks the one-byte `0x7f`, k3, non-delta frame: raw encoding has 9 bits and the little-endian output word is `0x000080bf`.

For that first frame, at clock9/task counter3, the reference has `encoded_bits=9`, while the generated Yosys netlist has `encoded_bits=0`. Its emitted expression is literally `_196_ = _026_ - _026_`, which loses the append's length increment. The absence of data-dependent append behavior subsequently makes history and block storage look unused; the reported 681 FF bits and only the length memory are therefore invalid inventory results.

## Small plain-Verilog reproducer

`task_inout_repro.v` contains one automatic task with a vector and integer `inout`, called once from a clocked process. It appends a byte and increments a local cursor, then registers both outputs. There are no arrays, no codec loops, no sv2v and no memory pass.

The direct Icarus simulation passes its numeric golden. Merely `read_verilog; hierarchy; proc; write_verilog` in Yosys0.33 already fails: input value `0xa5`, length8 should produce payload `0xa500` and count8, but produces payload0 and count0. Adding the later `opt/wreduce/memory_collect` passes gives the same failure. The demonstrated root cause is lost automatic-task `inout` copy-out side effects on this tool path; it is not an optimization benefit. This evidence does not establish behavior of other tool versions or of Design Compiler.

## Artifacts and reproduction

- Original encoder three stages: `runs/20261111T180912837805Z/result.json`.
- Bounded encoder three stages: `runs/20261111T181239982447Z/result.json`.
- Plain-Verilog minimum reproducer: `runs/repro_20261111T181121454965Z/result.json`.
- First export attempt: `runs/20261111T180814669257Z/export.log`. It independently records Yosys0.33 rejecting its own JSON's malformed non-ASCII source-path escape (`Unsupported \\uXXXX ... FFFF`). The successful audit instead rereads the untouched original converted Verilog, runs the exact recorded inventory passes, and replaces only `write_json` with `write_verilog -noattr` in a new directory.

```sh
python3 experiments/synthesis/codec_frontend_audit/run_audit.py
python3 experiments/synthesis/codec_frontend_audit/run_audit.py --case bounded_encoder
python3 experiments/synthesis/codec_frontend_audit/run_repro.py
```

Each command creates fresh timestamped run artifacts and preserves expected failures. `diagnostic_complete` means the experiment finished; it does not turn the failing Yosys design into a passing implementation. Generated netlists, logs, scripts, miter source and source/provenance hashes are retained. `SOURCE_SHA256.json` identifies the frozen audit sources and all three final diagnostic results.

The next specialized codec may use explicit append expressions or pure-input functions as a new implementation choice. That does not justify changing the frozen original for a legacy parser, or accepting a revised netlist without behavior/equivalence checks. The official full-SoC synthesis flow still requires real mapped-netlist equivalence including codec control and payload, and independent timing/power assessment; syntax or cell counts cannot replace LEC.
