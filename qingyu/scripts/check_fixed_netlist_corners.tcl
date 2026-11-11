# Fixed mapped netlist, independent DC process per corner, NO compile.
# Internal path engineering check only: IO delays/loads/uncertainty pending.
set corner $env(QINGYU_STA_CORNER)
set out [file join $env(QINGYU_STA_RUN_ROOT) $corner]
file mkdir $out
array set standard_names {
    tt_25c tt_typical_max_1p10v_25c
    ss_125c ss_typical_max_0p99v_125c
    ss_m40c ss_typical_max_0p99v_m40c
    ff_125c ff_typical_min_1p21v_125c
    ff_m40c ff_typical_min_1p21v_m40c
}
array set memory_names {
    tt_25c tt_1p10v_1p10v_25c
    ss_125c ss_0p99v_0p99v_125c
    ss_m40c ss_0p99v_0p99v_m40c
    ff_125c ff_1p21v_1p21v_125c
    ff_m40c ff_1p21v_1p21v_m40c
}
if {![info exists standard_names($corner)]} {error "Unknown corner $corner"}
set desktop [file normalize ~/Desktop]
set standard_name sc9mc_logic0040ll_base_rvt_c40_$standard_names($corner)
set standard [file join $desktop qingyu_stdcell_db db ${standard_name}.db]
set libraries [list $standard]
foreach macro {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
    lappend libraries [file join $desktop qingyu_sram_corners ${macro}_$memory_names($corner).db]
}
foreach library $libraries {
    if {![file readable $library]} {error "Missing $library"}
    read_db $library
}
set target_library [list $standard]
set link_library [concat [list *] $libraries]
read_verilog [file join $env(QINGYU_STA_RUN_ROOT) qingyu_accel_mapped.v]
current_design qingyu_accel
if {![link]} {error "Fixed netlist failed to link"}
set_operating_conditions $standard_names($corner) -library $standard_name
set_wire_load_mode top
set_wire_load_model -name Small -library $standard_name [current_design]
create_clock -name core_clk -period 6.666666667 [get_ports clk]
foreach {macro expected} {RAMSP128X16 5 RAMSP1024X16 2 RAMSP4096X16 2} {
    set count [sizeof_collection [get_cells -hierarchical -filter "ref_name == $macro"]]
    if {$count != $expected} {error "Macro count mismatch: $macro $count"}
}
redirect -file [file join $out design.rpt] {report_design}
redirect -file [file join $out check_design.rpt] {check_design}
redirect -file [file join $out check_timing.rpt] {check_timing}
redirect -file [file join $out setup.rpt] {report_timing -delay_type max -max_paths 5 -significant_digits 6}
redirect -file [file join $out hold.rpt] {report_timing -delay_type min -max_paths 5 -significant_digits 6}
redirect -file [file join $out violations.rpt] {report_constraint -all_violators}
set max_path [get_timing_paths -delay_type max -max_paths 1]
set min_path [get_timing_paths -delay_type min -max_paths 1]
if {[sizeof_collection $max_path] != 1 || [sizeof_collection $min_path] != 1} {
    error "Missing timed paths; cannot summarize this corner"
}
set setup_slack [get_attribute $max_path slack]
set hold_slack [get_attribute $min_path slack]
set summary [open [file join $out summary.txt] w]
puts $summary "corner=$corner setup_slack_ns=$setup_slack hold_slack_ns=$hold_slack macros=9"
close $summary
puts "QINGYU_CORNER_RESULT: $corner setup_slack_ns=$setup_slack hold_slack_ns=$hold_slack macros=9"
puts "QINGYU_CORNER_COMPLETE: $corner"
puts "QINGYU_SCOPE: fixed netlist, Small wire-load estimate, ideal clock, incomplete IO constraints; not signoff"
exit
