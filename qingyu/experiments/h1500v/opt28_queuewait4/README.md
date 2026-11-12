# opt28: four-row fused load, queued system bus and bounded WAIT

Engineering candidate; no official compliance, synthesis, STA, power or
Formality signoff is claimed. The unmodified base RTL is identified by
`BASE_SOURCE_SHA256.json` from opt26_fusedqueue. This directory combines
opt26 queued bus transport and unified fault/drain logic, opt25 four-row INT48
arithmetic, and opt27 version-2 bounded WAIT and driver. Vendor RTL is unchanged.
All six DMA channels use a depth-4 DMA queue followed by a depth-4 CPU/DMA
queue, the original E203 memory fabric and a single shared SRAM port. CPU
outstanding depth stays one; distinct DMA channels may overlap transactions.
The official OUTS_NUM=1 setting is unchanged; no SRAM bypass is used.
Historical opt12 PPA is not a measurement of this integration.

Each packed X/W word performs an actual staging source read and an actual
live-address write. Its private SRAM write occurs only after a successful
live write response. A register retains the address/data through arbitrary
backpressure. There is no third live-address read. Metadata keeps its existing
source-to-live copy followed by 576 live reads; numeric formats are unchanged.

The firmware copies metadata first, calls the ordinary accelerator soft reset,
checks the fused interface version, and then starts X and per-tile W loading.
There is no earlier X/W copy to snoop. W descriptors cover 16 columns and use
the accelerator's inactive bank; the next START cannot pass an active loader.
The old 0x80 and 0x90 commands retain their original live-read semantics.

| Register offset | Access | Meaning |
|---|---|---|
| 0xd0 | read | Interface ID `0x51462202` (bounded WAIT support) |
| 0xd4 | write | Copy/load all 3168 packed X words; argument is live base |
| 0xd8 | write | Copy/load one 512-word W tile; argument is live first-column address |
| 0xdc | read | bit 0 busy, bit 1 error, bit 2 completed, bit 3 W descriptor; error code at bits 15:8 |
| 0xe0 | read | Wait for fused idle/drain, then capture the same status; watchdog timeout returns busy/error with code 0x80 |

The driver keeps all 33 normal wait-helper call sites, replacing the repeated
0xdc reads with one 0xe0 read per call. WAIT is exclusively a sysfio control
transaction; it never owns the memory-fabric response slot. DMA proceeds while
its command is blocked. Status is captured at the command handshake into the
existing response register and remains stable under response backpressure.
Data-path errors return as status bits with ICB response error deasserted,
allowing the driver to return QINGYU_ERR_HARDWARE rather than taking a CPU trap.

FUSED_WAIT_TIMEOUT_CYCLES defaults to 1,000,000 bus clocks. This is a hardware
cycle limit (valid parameter values are at least one), not the previous device.poll_limit count of software polling
iterations, and the two values are not numerically interchangeable. A platform
needing another bound must select and record the synthesis parameter. The
existing device.poll_limit remains in use for other driver polling functions.
At timeout, WAIT returns code 0x80 with busy still asserted. It does not discard
an outstanding request, mark a transfer complete, or reset DMA. The driver
returns QINGYU_ERR_TIMEOUT and retains the existing reset/drain/reset error
cleanup. CONTROL RESET bypasses all DMA-engine busy gates, including metadata, so
cleanup can always issue RESET after consuming a WAIT timeout response.
If a slave never responds, the cleanup WAIT also times out: control can
return while the old transaction stays quarantined. BUSY includes held offers
and pending transport, not merely the fused FSM. No new fused descriptor can
overwrite that transaction. A second quiet RESET clears sticky errors only
after real drain; a permanently disconnected slave is not claimed to recover.
Software RESET preserves queued requests; global hardware reset clears them.

Source addresses equal the corresponding configured live addresses plus
0x40000. W advances 4 bytes within eight packed column pairs, then 484 bytes
to the next row. It visits each of the 8192 W words exactly once across all
16 descriptors. Addresses, full live write data, shifts, biases and outputs
must match the same frozen input images used by the baseline.

The independent `verification_contract.json` fixes the intended counts:

- 11936 source load reads and 11936 live writes are retained.
- 3168 private X writes and 8192 private W writes are checked by value/address.
- Live-to-private reads decrease from 11936 to 576; the reduction is 11360.
- 12672 packed output writes remain. CPU validation reads are counted separately.

These are payload transaction counts, not the complete official traffic or a
cycle prediction. Initial loading, parameter validation, CPU scheduling and
all waits must remain inside the applicable task/activity window. The existing
staging-source harness models loading from prepositioned source data; matching
that boundary to the organizer's actual loading interface still requires
platform confirmation. Removing the staging copy while starting the timer
after externally preloading live SRAM would omit real loading work.

Source/read and live/write failures never commit private data. Errors remain
visible in 0xdc, and a failed START returns an error without sending START to
the accelerator. Metadata read errors stop the gatherer. An active fused
descriptor drains its in-flight transaction on software reset, suppresses
private commits, and reports abort. Reset does not erase completed private X
data; the driver resets before loading each new task. The driver uses bounded
polls and retains its original failure result while draining/resetting an
aborted load.

Error codes: 1 fused source read, 2 fused live write, 3 fused abort, 0x80 WAIT timeout,
0x10 metadata read, 0x11 staging, 0x12 legacy W load, 0x13 legacy X load,
0x14 copy, 0x15 residual global transport/abort. Status is diagnostic; success still requires the independent SoC
scoreboard, complete output writes and zero reported firmware errors.

Independent WAIT tests use a 256-clock watchdog and cover busy success with
continued DMA traffic, all four X/W read/write failures, status changes during
response backpressure, command-not-accepted timeout, response-never-arrives
timeout, and reset/drain/reload after each timeout. The shared fault suite also
covers the original 11 faults and two in-flight software-reset recovery cases.
Use fresh hashed artifacts; no earlier candidate's SoC cycle/PPA result applies.


opt28 additionally retains opt26 transparent hold registers and captured LD
metadata/weight ownership. On any DMA fault or accepted software RESET, all
new work and private commits stop, but already offered/accepted commands must
drain. WAIT timeout only captures status; it never changes DMA state.

Local validation before freezing:

- WAIT success/fault/backpressure/watchdog and concurrent metadata/fusion
  command or response stalls; bounded RESET, repeat timeout, restart rejection,
  genuine drain and complete 512-word W reload:
  `build/fused_wait_opt28_queuewait4_20261111_142146_752916/result.json`.
- Original eleven faults plus two soft-abort/drain/reload cases:
  `build/fio_faults_opt28_queuewait4_20261111_142448_923771/result.json`.
- All six held offers with concurrent fault or RESET, plus 512 W and 36
  metadata reads under owner competition:
  `build/fio_queue_faults/20261111T142448892351Z/result.json`.
- Verilator FIO/accelerator elaboration: `build/opt28_checks/lint.log`,
  no errors; existing width warnings remain and are not a signoff waiver.

Reproduce with `scripts/run_fused_wait_checks.py --candidate opt28_queuewait4
--queue`, `scripts/run_fio_fault_checks.py --candidate opt28_queuewait4 --fused`
and `scripts/run_fio_queue_fault_checks.py --candidate opt28_queuewait4`.
Full SoC regression is a separate gate using
`scripts/run_bus_queue_candidate_soc.py`. Source initialization before reset
is outside that local measurement window. Elaborate private SRAM counts from
this four-row design; do not copy eight-row opt26 counts.
