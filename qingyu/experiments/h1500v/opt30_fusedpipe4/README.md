# Four-row fused loader with overlapped system-bus transfers

This candidate derives from opt26_fusedqueue. It uses opt25_fused4's four-row,
sixteen-lane accelerator, opt27/28's bounded WAIT_FUSED driver interface, and a
two-entry FIFO between fused source reads and live writes. All shared-memory
commands still traverse both added arbiters and the unmodified official E203
memory fabric. There is no direct shared-SRAM connection.

Each input/weight source is read once and written to its real live address.
The next source read can overlap the preceding live write. A FIFO entry stays
allocated until the write response, and only a successful response commits
that word into the private operand SRAM. Separate read and retirement counters
preserve strided W addressing and packed X indices. At most one read and one
write from this engine are accepted but unanswered; the two slots account for
both returned words and the reserved slot for an outstanding read.

The four-row datapath retains INT16 operands/output and INT48 accumulation.
It contains 64 MAC lanes, eight 1024x16 X macros and 41 128x16 operand/output
macros in the production configuration. These are source structure facts, not
measured area or energy. Model configuration and output size are unchanged.

## Failure and reset behavior

The opt26 six-port command holds and response ownership queues are retained.
Any transport error or accepted soft reset suppresses new work and private
commits. Commands already offered remain stable until accepted; accepted
responses drain. Local FIFO cancellation does not erase outstanding shared-bus
transactions or undo completed live writes. Restart is rejected until drain
finishes and a subsequent quiet RESET clears sticky errors.

WAIT_FUSED (0xe0, read only, capability 0x51462202) blocks the control interface
while fused work or abort drain is busy, leaving the memory bus available.
Its default watchdog is 1,000,000 bus clocks, independent of software poll_limit.
Timeout returns a captured busy/error status with code 0x80 and no ICB error.
It does not cancel DMA or claim completion. RESET is accepted even with metadata
in flight; a permanently unresponsive downstream device remains busy and blocks
restart, while later WAIT calls return within their watchdog interval.

## Validation before full SoC regression

- Eleven transport-fault scenarios and two abort/drain cases with complete X reload:
  build/fio_faults_opt30_fusedpipe4_20261111_142545_331162/result.json.
- Six held ports, both error and reset cancellation, plus metadata/W owner contention:
  build/fio_queue_faults/20261111T142545331875Z/result.json.
- Three seeds, full X/W loads, independent address-derived data, FIFO reservations,
  simultaneous read/write requests and mid-stream faults:
  build/fused_pipe_checks/20261111T142545343863Z/result.json.
- Bounded WAIT, stable responses, stalled requests/responses and concurrent metadata
  timeout/reset/drain/reload:
  build/fused_wait_opt30_fusedpipe4_20261111_142545_480423/result.json.

Full numeric/performance regression uses scripts/run_bus_queue_candidate_soc.py.
The engineering timing window starts at the first CPU parameter-source request
and ends at the originating DMA's final output-write response. Initial external
loading of the source staging region is not included. Official loader timing,
600-sample scoring, physical timing, area and whole-SoC energy remain unmeasured.
