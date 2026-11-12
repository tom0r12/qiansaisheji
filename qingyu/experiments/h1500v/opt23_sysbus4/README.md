# Four-row system-bus comparison

This candidate uses the frozen opt20_sysbus integration, FIO and validate4
firmware, with only `qingyu_accel.sv` replaced by the four-row opt12_wait engine.
The original platform memory fabric and all cold-loading transfers remain in
the measured path. No SRAM bypass or numerical-format change is introduced.

The purpose is to compare four and eight compute rows under the same single
32-bit platform memory bus. The historical opt12 area/power measurements do
not apply to this new integration. Use new complete-task simulation and new
official-library synthesis/STA/power evidence when selecting a submission.
