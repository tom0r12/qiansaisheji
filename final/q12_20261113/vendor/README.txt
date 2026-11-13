Q12 manufacturer SRAM functional regression, explicit loader.
No PDK/model contents are included. Existing server SRAM_Lib_2025 models and sram_models.json identity are required.
Fresh compile + 12 cold tasks + exact-window SAIF: sh run.sh
Do not reuse any baseline, previous variant or prior server simv.
Optional full-DUT activity: sh run.sh --activity --reuse-build /absolute/first/run/directory
Explicit SAIF conversion (no power): python3 convert_activity.py /absolute/activity/run/directory
Only verified successful builds may be reused. Default user-overridable limits are 1800s compile, per-task simulation, and per-task SAIF; these are not runtime estimates.
Firmware/zero/poison initialization before reset release and independent physical readback after HOST are outside the measured window.
No tensor/parameter is preloaded. Runtime source writes traverse the unchanged original System Bus and single shared SRAM ingress.
Full window begins at the first task-control or source offer and ends at final output magic response ACK.
ARM_UD_MODEL functional vendor simulation is not SDF/STA/silicon measurement. No power or energy is reported.
Historical frozen Q12 fixtures are not the organizer final accuracy dataset.
Private sample payloads: upload only to the user-owned contest server, not public GitHub.
Actual synthesizable hardware has independent CPU, engine and external-loader ICB masters, NP3 FIFO depth4/mask000. No CPU takeover/force occurs during runtime.
External request mailbox and FIO response router are real DUT logic and must be included in area/power. BFM is outside DUT and only uses public ports.
Organizer acceptance of the added external platform interface is not inferred from simulation. Original System Bus/shared SRAM controller is unchanged.
Exact activity timestamps use1ps precision; optional dump stops1ps after finalACK to retain same-edge nonblocking updates. SAIF end remains exactACK.
