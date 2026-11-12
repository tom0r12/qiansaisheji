# opt31_fastwrite

Experimental child of frozen opt30_fusedpipe4. Only the behavioral and physical
shared SRAM response wrappers change. Official E203 fabric source/parameters,
FIO, four-row accelerator, firmware, payload and engineering timing window are
unchanged. This is not the selected candidate or an official PPA result.

The original splitter supports zero-cycle responses through ALLOW_0CYCL_RSP=1.
A write now accepts the command and response on the same edge that performs the
actual byte-enabled SRAM write. Response backpressure stalls both handshakes and
storage mutation. Reads keep a pending response until consumed; no later memory
operation is accepted while that read is pending. Reset clears protocol state,
does not clear SRAM, and gates all handshakes and writes.

Behavioral SRAM and the macro wrapper use identical handshake logic. Macro
timing, write-enable paths and 150 MHz closure still require the specified
library and actual vendor models. A local stand-in macro can verify wrapper
semantics only and must never be used as physical power/area evidence.

Verification must cover same-edge writes, all byte masks, reads, held responses,
invalid addresses, reset during a stalled write/read, and sustained write
throughput. Then run the unchanged full SoC protocol/data checks on actual KWT
task images and compare against opt30 using the same complete engineering
window. Never infer fewer bus transactions or official-loader compliance from
the shorter write response alone.
