# Qingyu C driver

The SDK-independent driver is `sw/qingyu_accel.c` and its public header is
`sw/qingyu_accel.h`. `sw/example_main.c` supplies a callable example, not an
E203 reset handler or a complete platform firmware image. No heap, libc
calls, floating point, or model arithmetic are used in the driver.

The driver accepts the absolute accelerator base at runtime. A platform must
connect the peripheral, reserve a 64 KiB MMIO region, and use the matching
address in firmware. No target base is invented by this driver.

## Data contract

`qingyu_job` contains row-major signed INT16 input `[99][64]` and weight
`[64][256]`, signed-48-bit bias values in an `int64_t[256]`, shifts in
`uint8_t[256]`, and an INT32 destination `[99][256]`. Dimensions must be
exactly 99, 64, 256 and the layer identifier must be 0 through 11.

Input and weight pointers require 2-byte alignment, biases require 8-byte
alignment, and output requires 4-byte alignment. These checks, pointer-span
overflow checks, output/input-parameter overlap checks, bias signed-48 range
checks and all 256 shift range checks happen before any MMIO write. The
caller must still allocate sufficiently large, accessible arrays; C cannot
verify allocation length from a raw pointer.

All four arrays of model data are already encoded offline. Bias is not a
floating-point value. The CPU only packs and copies its 48-bit two's
complement representation. Bits 48 through 55 of the 64-bit metadata record
contain the shift; bits 56 through 63 are zero. All peripheral transactions
are aligned 32-bit accesses, using the little-endian hardware layout.

`qingyu_run` checks the ID, starts diagnostic timing if a hook is present,
resets control state, loads the complete input once, and executes 64 tiles.
Each tile copies four weight columns in `[k,p]` order, loads all four metadata
records, starts hardware, and polls with a finite limit. It requires DONE
with BUSY cleared, no ERROR, and exactly 396 outputs. Tile output `[row,p]`
is copied into the global destination `[row,column_base+p]`. Hardware does
all dot products, bias additions, rounding and saturation.

Every independent call reloads all inputs and parameters. DONE/ERROR are
cleared per tile; a soft reset aborts a failed computation. On failure,
`completed_tiles` records the copied prefix and the destination must not be
used as a completed task. The saved status and hardware error identify the
failure even after the abort resets the hardware state. The RTL document
defines numeric hardware error codes; software preserves them verbatim.

## Platform integration

```c
qingyu_device dev;
qingyu_job job;
qingyu_result result;
qingyu_init(&dev, platform_accel_base, 1000000u);
/* Fill job pointers with encoded real data and set 99/64/256/layer_id. */
int rc = qingyu_run(&dev, &job, &result);
```

The normal backend uses volatile 32-bit MMIO. GNU RISC-V builds use
`fence iorw, iorw` at task/tile boundaries. GNU/Clang host builds retain a
compiler memory barrier. If another compiler or a cached platform is used,
adapt the barrier and perform platform-specific cache maintenance. The
baseline E203 integration must verify its memory map and coherent/noncached
shared SRAM behavior.

Optional paired read/write callbacks permit host testing and transports
without direct pointer MMIO. Their addresses include `dev.base`. The callback
context is shared with the optional `read_ticks` hook. A platform bus fault
is handled by the platform exception handler; a C volatile access cannot
convert an ICB error into a normal return value. The driver issues only
contract-valid accesses after validation.

`poll_limit` is a maximum number of STATUS reads per wait, not a duration in
seconds. It must exceed measured worst-case tile latency. The optional timing
hook must return a stable 64-bit monotonic tick count. For a 32-bit CPU,
reading a split counter requires high/low/high retry or an equivalent
platform implementation. Diagnostic timing starts before reset and input
loading and ends after the last result store plus memory fence. It excludes
preflight validation and the ID read, and does not include any earlier
official testbench parameter-loader stage. `timing_valid` is set only after
a successful entire task. `compute_cycles_sum` is a diagnostic sum of the
hardware tile counters, not official end-to-end latency.

The contest environment's complete loading-to-writeback timing remains the
official measurement. Never use a failed task or an internal compute counter
as the task throughput/energy result.

## Reproduction and provenance

The example needs application-supplied vectors and does not claim a measured
KWT error, area, power, or timing result. Passing synthetic engineering vectors
proves packing and control behavior only. Use the separately verified model
extractor and frozen calibration parameters for contest data.

The driver can be compiled independently with a host C99 compiler and the
E203-target RISC-V compiler, using `-std=c99 -Wall -Wextra -Werror` and
`-march=rv32imac -mabi=ilp32 -ffreestanding` for the latter. Startup code,
linker layout, interrupt/trap handling and SDK selection belong to the SoC
firmware integration.

Verification performed during implementation: both C files compiled cleanly
with host GCC C99 `-Wall -Wextra -Werror -pedantic` and with RISC-V GCC using
`-march=rv32imac -mabi=ilp32 -ffreestanding -Wall -Wextra -Werror`. A callback
host test checked all 64 tiles and 25,344 scattered outputs, signed bias and
weight packing, finite timeout, hardware-error/output-count rejection, reset
on failure, and validation before writes. This is a driver control/packing
test; actual E203 execution and ICB RTL integration are separate checks.
