# opt29_fusedqueue4

This is a controlled four-row comparison of opt26_fusedqueue. All RTL, firmware and driver sources are copied from frozen opt26 except rtl/qingyu_accel.sv, which is byte-identical to opt25_fused4. The 0xe0 blocking-WAIT change is not included. No source in either parent candidate is modified.

The design retains the six-master DMA queue, CPU/DMA queue, unchanged official E203 memory fabric and a single-port shared SRAM. X/W fused transfers retain every source read and live write; metadata retains 576 live reads. All outputs remain INT16.

Validation uses scripts/run_bus_queue_candidate_soc.py and the same 12 headroom1 KWT tasks. The window includes validation, staging-to-live transfers and the final output write response at the DMA origin. External initial source loading remains outside this local test window. The source snapshots and input hashes are recorded per run. The complete regression passed: `build/bus_queue_soc_opt29_fusedqueue4_20261111_141855_742136/result.json`, 304128 correct outputs, all 12 tasks at 102164 cycles and 37440 official-fabric/SRAM transactions each. This is 219 cycles less than the eight-row opt26 control under the same task window. The tracked-source-template migration independently reproduced layer 0 using the same simulator binary: `build/bus_queue_soc_opt29_fusedqueue4_20261111_142829_249122/result.json`.

The FIO and merge are byte-identical to opt26, whose directed transport/concurrent error, reset and reload tests passed. The new four-row SoC passed its own 12-layer numerical/routing regression. This is not formal verification, official accuracy evaluation, or PPA signoff.
