# Source origins and contribution record

- Official E203 RTL, peripherals and test material remain under
  `vendor/e203_hbirdv2`, from Nuclei's Apache-2.0 licensed repository, revision
  `9f3e34f337f5d0a1236a285871ffa2032491617a`.
- `scripts/prepare_soc.py` generates three renamed project adapters from
  upstream files and records the upstream file SHA256 values. Original
  copyright/license headers remain intact. It exports the real bus clock/reset,
  connects shared memory and FIO endpoints, and configures this project's test
  boot vector to the firmware preloaded in ITCM (0x80000000).
- New accelerator RTL, wrappers, model, driver, firmware and tests were created
  with Codex assistance for this project. Contest members must review, understand
  and maintain the submitted design and accurately describe their contributions.
- Official KWT source is pinned separately to commit
  `237e4097afd4f6851e0b82f0a8d65c2dfe8eae30`. Source/checkpoint loading and
  real-dataset accuracy must be recorded separately from synthetic test results.
- User-supplied SMIC40 PDK is private local input. Do not redistribute
  `local_pdk/`, the original PDK archives, or extracted library contents in a
  public source submission. Use the organizer-authorized distribution method.

The project integration map is 0xA0000000..0xA007ffff for 512 KiB shared SRAM,
0xF0000000..0xF000ffff for the accelerator, and 0xF0010000 for simulation host
notification. These addresses were selected for this integration based on the
upstream memory/FIO decode; they are not represented as organizer-prescribed.

Behavioral memory and clock/PLL models are functional models. An RTL simulation
at a clock period does not prove setup/hold closure or 150 MHz silicon timing.
