# Fused transfers with queued official-bus arbitration

This isolated candidate combines the frozen `opt22_fused` numeric datapath,
driver, and fused source-read/live-write/private-commit protocol with the
`opt24_busqueue` arbitration queues. Neither source candidate is modified.

The accelerator remains eight rows by sixteen INT16 lanes with INT48
accumulation. Its RTL, C driver, header, and firmware are byte-identical to
opt22. This candidate does not contain the compact-X SRAM experiment or a
blocking fused-WAIT CSR.

## Bus contract

All six DMA channels enter `u_dma_merge` (depth 4, one transaction per source)
and then the CPU/DMA merger in `u_e203_subsys_main.u_mem_merge` (depth 4,
CPU limited to one outstanding transaction; DMA may have several). They
traverse the unchanged official `u_e203_subsys_mems` before reaching the
single-port shared SRAM. Official vendor RTL and its OUTS_NUM=1 setting remain
unchanged. There is no shared-memory bypass.

The interface and hierarchy match opt24. The six DMA indices remain CW, SW,
MEM, LD, IN, SR. Transparent hold registers in the FIO capture a command only
when it has been offered and blocked; they do not acknowledge the command
early or change the external acceptance event. Captured address, data, mask,
read direction and LD internal owner remain stable until acceptance. The
response-owner FIFO requires ordered, nonzero-latency downstream responses.

Legacy copy/staging engines have explicit read/write credits. Fused IN/CW
traffic remains one source read followed by one acknowledged live write.
Private data is committed only after that successful write response.

## Fault and abort contract

Any DMA error, or an accepted CONTROL RESET, suppresses new DMA work and
private commits. An already offered command is still accepted and drained,
including a command that was blocked at the time of the error. Accepted
responses drain independently of the cancelled engine FSMs. Global hardware
reset clears queues and holds; software reset does not discard transactions.

Faults remain sticky. New transfer descriptors return a finite error and START
is blocked from the accelerator until transport drain finishes and a subsequent
RESET clears the errors. RESET has priority when START and RESET bits are both
set. Status BUSY includes transport drain rather than only the fused FSM state.
Status error code 0x15 identifies a residual global transport/abort fault when
no more specific engine error code applies. A reset while already quiet clears
the fault in one step. A reset while traffic remains in flight requires polling
BUSY to zero and then issuing RESET again before reloading.

The LD port's metadata/weight selection is captured with a blocked offer.
Metadata acceptance and response ownership use that captured identity even if
a newer weight request becomes the current higher-priority requester.

## Local verification

- Existing public-interface test: eleven transport error scenarios and two
  soft abort/drain cases followed by a complete 3168-word X reload pass.
  Evidence: `build/fio_faults_opt26_fusedqueue_20261111_140945_834857/result.json`.
- New independent test: all six held source offers survive both a concurrent
  error and software reset; payload stability, error responses, START/RESET
  priority, drain status, no cancelled private commit, and clean reload pass.
  A blocked metadata request followed by a weight descriptor completes all
  512 weight and 36 metadata reads without owner confusion.
  Evidence: `build/fio_queue_faults/20261111T140952220394Z/result.json`.
- Whole-SoC Verilator lint: `build/opt26_initial/lint_final.log`. Existing
  vendor clock-gate latch and BIU/QSPI combinational warnings are not waived
  as new design findings; this is not a CDC or physical timing signoff.
- The queued merger is byte-identical to opt24's separately tested module.
  Full SoC numerical regression and performance measurement are a separate
  gate; the unit tests above establish no new PPA result.

Reproduce with `python scripts/run_fio_fault_checks.py --candidate
opt26_fusedqueue --fused` and `python scripts/run_fio_queue_fault_checks.py`.
The SoC runner is `scripts/run_bus_queue_candidate_soc.py` with this candidate
and explicit image provenance. It measures from the first CPU parameter read
through the final originating DMA output response, including validation/setup.


## Completed local SoC regression and metadata correction

The 12 real headroom1 tasks passed in `build/bus_queue_soc_opt26_fusedqueue_20261111_141620_604247/result.json`: 304128 correct INT16 outputs, all 12 complete-task windows at 102383 cycles, and 37440 official-fabric/SRAM transactions per task. Source/live/private X/W values and response routes were checked independently. External source initialization before reset is excluded; this is not official end-to-end throughput or PPA signoff.

After that run, only the verification-contract identity fields were corrected to name opt26 and its opt22/opt24 parents. The measured RTL and firmware bytes are unchanged. `VALIDATED_VERIFICATION_CONTRACT.json` and `VALIDATED_SOURCE_SHA256.json` preserve the exact pre-correction snapshots referenced by the original result; original results were not edited.
