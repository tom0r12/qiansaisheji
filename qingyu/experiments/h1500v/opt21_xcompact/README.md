# Compact input storage on the system-bus candidate

This candidate inherits the system-bus integration of opt20_sysbus and changes
only the private X storage in the eight-row accelerator. INT16 operands, INT48
bias/accumulation, rounding, saturation and register semantics are unchanged.

For the production 99 x 64 input matrix:

```
physical_bank = (row % 8) ^ (k % 2)
physical_address = (row / 8) * 64 + k
```

Eight 1024 x 16 macros replace sixteen. All eight rows can read the same K in
one cycle, and a packed even/odd K pair writes two different physical banks in
one cycle. The returned parity is registered with the synchronous SRAM access;
tail row enables are mapped with their logical requests. The non-packed
configuration retains its previous storage layout.

The useful 6336 halfwords occupy 77.34% of the allocated 8192 halfwords. This
is a structural capacity result, not a measured chip-area or energy result.
SRAM access count and arithmetic work do not decrease.

Component verification uses independent integer reference outputs, random
response/stream backpressure, tail rows, reset aborts and a resident-weight
restart. `--x-storage-checks` additionally reads every input word after packed
stream writes, MMIO writes and single-element stream writes, in both address
directions. These tests do not establish official PPA or platform acceptance.

```
python3 scripts/run_candidate_checks.py --candidate experiments/h1500v/opt21_xcompact/rtl --cases 12 --x-storage-checks
```
