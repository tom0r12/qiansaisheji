# Copy outside the bundle and replace every placeholder with verified server
# information. This example intentionally cannot start EDA as supplied.
set STD_CELL_FAMILY SCC40NLL_VHSC40_RVT_V0p1
set STD_CELL_LIBS {}
set SRAM_LIBS {}
set PLATFORM_SDC {}
set SYSTEM_CLOCK_NAME {}
set AON_CLOCK_NAME {}
set OPERATING_CONDITION {}
set OPERATING_LIBRARY {}
set WIRE_LOAD_MODE {}
set WIRE_LOAD_MODEL {}
set WIRE_LOAD_LIBRARY {}
set LIBRARY_PROVENANCE {}
set LIBRARY_IDENTITY_FILE {}
set TIMING_PROVENANCE {}
set AREA_UNIT_PROVENANCE {}
set AREA_UNIT_TO_UM2 {}
set SRAM_AREA_PROVENANCE {}
set SRAM_AREA_UM2 [dict create]
# Standard library origin: official SMIC40_2025/S40.tar.gz,
# SCC40NLL_VHSC40_RVT_V0p1/basic/NLDM, selected approved corner.
# SRAM origin: /storage1/admin_public_dir/SRAM_Lib_2025.
# PLATFORM_SDC must cover hfextclk, lfextclk, selected JTAG mode, generated/
# gated clocks, all top I/O timing/load, and the actual boot/runtime mode.
# Include the 150 MHz system clock and 32.768 kHz always-on domain. Supply
# reviewed provenance for any case analysis, asynchronous clock groups or
# timing exception. Do not inherit a one-clock accelerator-only SDC.
