# Independent SS trial against the frozen RTL, not official timing signoff.
# Start a new DC session. Do not source in a session containing another design.
if {[sizeof_collection [get_designs -quiet *]] > 0} {error "Use a new DC session"}
set desktop [file normalize ~/Desktop]
set frozen [file join $desktop qingyu_formality_margin_20261101_222303_222700 inputs]
set trial [file join $desktop qingyu_ss_trial_[clock seconds]_[pid]]
set standard_name sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_m40c
set standard [file join $desktop qingyu_stdcell_db db ${standard_name}.db]
set libraries [list $standard]
foreach macro {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
    lappend libraries [file join $desktop qingyu_sram_corners ${macro}_ss_0p99v_0p99v_m40c.db]
}
foreach path [concat $libraries [list [file join $frozen qingyu_accel.sv] [file join $frozen qingyu_sram16.sv]]] {
    if {![file readable $path]} {error "Missing input $path"}
}
file mkdir [file join $trial work]
file copy [file join $frozen qingyu_accel.sv] [file join $trial qingyu_accel.sv]
file copy [file join $frozen qingyu_sram16.sv] [file join $trial qingyu_sram16.sv]
set_svf [file join $trial qingyu_accel.svf]
foreach library $libraries {read_db $library}
set target_library [list $standard]
set link_library [concat [list *] $libraries]
define_design_lib WORK -path [file join $trial work]
analyze -format sverilog [list [file join $trial qingyu_sram16.sv] [file join $trial qingyu_accel.sv]]
elaborate qingyu_accel
current_design qingyu_accel
if {![link]} {error "Link failed"}
uniquify
set_operating_conditions ss_typical_max_0p99v_m40c -library $standard_name
set_wire_load_mode top
set_wire_load_model -name Small -library $standard_name [current_design]
create_clock -name core_clk -period 6.666666667 [get_ports clk]
foreach macro {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
    set_dont_touch [get_cells -hierarchical -filter "ref_name == $macro"] true
}
puts "QINGYU_SS_TRIAL_DIRECTORY: $trial"
puts "QINGYU_SS_TRIAL: frozen RTL, SS 0.99V -40C, 150MHz, Small wire load; IO constraints incomplete"
# Do not silently accept a missing DC Ultra license or compile failure.
set compile_result 0
redirect -tee -file [file join $trial compile.log] {set compile_result [compile_ultra]}
if {!$compile_result} {error "compile_ultra failed; inspect compile.log"}
foreach {macro expected} {RAMSP128X16 5 RAMSP1024X16 2 RAMSP4096X16 2} {
    set count [sizeof_collection [get_cells -hierarchical -filter "ref_name == $macro"]]
    puts "QINGYU_SS_MACROS: $macro $count"
    if {$count != $expected} {error "Unexpected macro count"}
}
redirect -file [file join $trial check_design.rpt] {check_design}
redirect -file [file join $trial check_timing.rpt] {check_timing}
redirect -tee -file [file join $trial area.rpt] {report_area -hierarchy}
redirect -file [file join $trial setup.rpt] {report_timing -delay_type max -max_paths 5 -significant_digits 6}
redirect -file [file join $trial hold.rpt] {report_timing -delay_type min -max_paths 5 -significant_digits 6}
redirect -tee -file [file join $trial violations.rpt] {report_constraint -all_violators}
set worst_setup [get_timing_paths -delay_type max -max_paths 1]
set worst_hold [get_timing_paths -delay_type min -max_paths 1]
if {[sizeof_collection $worst_setup] != 1 || [sizeof_collection $worst_hold] != 1} {error "Missing timed paths"}
puts "QINGYU_SS_RESULT: setup_slack_ns=[get_attribute $worst_setup slack] hold_slack_ns=[get_attribute $worst_hold slack]"
change_names -rules verilog -hierarchy
write -format ddc -hierarchy -output [file join $trial qingyu_accel.ddc]
write -format verilog -hierarchy -output [file join $trial qingyu_accel_mapped.v]
write_sdc [file join $trial precheck_only.sdc]
set_svf -off
puts "QINGYU_SS_TRIAL_COMPLETE: $trial"
puts "Candidate only. New netlist requires equivalence and all selected corner checks; no final acceptance claimed."
