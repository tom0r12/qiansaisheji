# opt33_readcache

Experimental child of opt32_outputqueue. The official E203 fabric and its
parameters, queued-output FIO, compute core, payload and output format remain
unchanged. Only shared-slave response/storage control, explicit cache-clear
wiring and the engineering harness's pre-validation reset change.

Both shared-memory wrappers embed the identical independently verified
`qingyu_shared_read_ahead` controller. The wrapper preserves the platform's
byte-address convention by normalizing address bits [1:0] at the word interface;
the original byte write masks are passed unchanged. The behavioral wrapper
deliberately poisons RAM Q after writes. The physical wrapper uses the existing
64 RAMSP4096X16 macros and no speculative write path.

An accepted accelerator CONTROL_RESET clears cache tags and pending refill
eligibility. Already accepted responses survive this clear. The harness issues
that reset before its first source-validation read, and retains the ordinary
in-task reset. Task caches therefore do not rely on a global testbench reset to
be cold. Production loader integration must preserve this explicit boundary.

All external shared reads/writes still route through the original fabric.
Additional internal macro reads, cache state, comparisons and muxes are real
hardware and must be included in incremental logic area and full-SoC activity.
Warm sequential hit performance is not assumed for interleaved masters.

Independent controller verification covers write-Q poisoning, alias/masked
writes, response stalls, clear during pending transactions, reset, memory
boundaries and the final contents of all 131072 words. Integrated task and
actual manufacturer macro/STA/PPA results are separate requirements. This is
not the selected candidate, and no target metric is claimed achieved.
