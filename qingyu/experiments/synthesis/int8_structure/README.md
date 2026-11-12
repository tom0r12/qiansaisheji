# Structural inventory experiment — not qualified

`run_inventory.py` converts unchanged frozen RTL with sv2v v0.0.13 and runs
generic Yosys 0.33 RTLIL passes. It does not use any process library or produce
a physical-design handoff. SRAM declarations describe ports only.

The current flow is **rejected as resource evidence**. The optimized encoder
unexpectedly removes its history and block data. Independent three-stage
testing passes the original RTL and sv2v output but fails the Yosys optimized
encoder on the first one-byte frame. The apparent 681 flip-flop count is not
a valid implementation count and must not be used for area comparison.

Evidence: `experiments/synthesis/codec_frontend_audit/runs/20261111T180912837805Z/result.json`.
The prior extraction result is retained unchanged under
`build/int8_structure/20261111T180353162824Z`; its process completion flag is
not equivalence approval. Other components from this tool flow remain
unqualified until independently checked.

The core front end also fails with a signed variable-part-select internal
cell invariant in Yosys; adding `-noopt` did not resolve it. Frozen hardware
sources were not edited to accommodate that parser failure.

Tool setup: Ubuntu's Yosys 0.33 package; official sv2v v0.0.13 Linux release
ZIP SHA256 `552799a1d76cd177b9b4cc63a3e77823a3d2a6eb4ec006569288abeff28e1ff8`,
binary SHA256 `b80a8ac6212aa72a196d9d6129cda35f16dbfa799ec61848c46321f845b6b635`.
The release and conversion behavior are documented in the
[sv2v repository](https://github.com/zachjs/sv2v).

Formal evaluation continues to require the specified competition libraries,
manufacturer memories, full equivalence, timing and whole-SoC activity.
