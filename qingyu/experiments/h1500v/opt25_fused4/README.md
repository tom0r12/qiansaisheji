# opt25: four-row fused X/W loading over the system bus

Engineering candidate; no official compliance, synthesis, STA, power or
Formality signoff is claimed. The unmodified base RTL is identified by
`BASE_SOURCE_SHA256.json` from opt20_sysbus. This directory retains opt20's
single 32-bit system-bus path and shared SRAM. It inherits the final opt22
FIO/driver, but uses opt12's four-row INT48 arithmetic for a same-bus comparison.
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
| 0xd0 | read | Interface ID `0x51462201` |
| 0xd4 | write | Copy/load all 3168 packed X words; argument is live base |
| 0xd8 | write | Copy/load one 512-word W tile; argument is live first-column address |
| 0xdc | read | bit 0 busy, bit 1 error, bit 2 completed, bit 3 W descriptor; error code at bits 15:8 |

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

Error codes: 1 fused source read, 2 fused live write, 3 fused abort,
0x10 metadata read, 0x11 staging, 0x12 legacy W load, 0x13 legacy X load,
0x14 copy. Status is diagnostic; success still requires the independent SoC
scoreboard, complete output writes and zero reported firmware errors.

Validation is in progress; consult freshly hashed run artifacts rather than
reusing an opt20 result for this candidate.
