# Run in a NEW dc_shell session. TT margin experiment, not final acceptance.
# Optimize at 6ns, then report at the original 6.666666667ns requirement.
# No assumed IO delays, loads, input slew or clock uncertainty are supplied.
# Consequently external paths are not fully constrained and this is NOT signoff.
set precheck_desktop [file dirname [file normalize [info script]]]
set precheck_dir [file join $precheck_desktop qingyu_dc_margin_[clock seconds]_[pid]]
file mkdir $precheck_dir
set_svf [file join $precheck_dir qingyu_accel.svf]
source [file join $precheck_desktop check_sram_macros.tcl]
current_design qingyu_accel
create_clock -name core_clk -period 6.000000000 [get_ports clk]
foreach macro {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
    set_dont_touch [get_cells -hierarchical -filter "ref_name == $macro"] true
}
puts "QINGYU_PRECHECK: TT, 6ns optimization target, report at 150MHz; IO constraints incomplete"
redirect -tee -file [file join $precheck_dir compile.log] { compile -map_effort high }
set_svf -off
# Restore the actual 150MHz requirement for all following reports.
create_clock -name core_clk -period 6.666666667 [get_ports clk]
foreach {macro expected} {RAMSP128X16 5 RAMSP1024X16 2 RAMSP4096X16 2} {
    set count [sizeof_collection [get_cells -hierarchical -filter "ref_name == $macro"]]
    puts "QINGYU_POST_COMPILE_MACROS: $macro $count (expected $expected)"
    if {$count != $expected} { error "Unexpected post-compile macro count" }
}
redirect -tee -file [file join $precheck_dir check_design.rpt] { check_design }
redirect -tee -file [file join $precheck_dir check_timing.rpt] { check_timing }
redirect -tee -file [file join $precheck_dir area.rpt] { report_area -hierarchy }
redirect -tee -file [file join $precheck_dir timing_max.rpt] { report_timing -delay_type max -max_paths 5 -significant_digits 6 }
redirect -file [file join $precheck_dir timing_min.rpt] { report_timing -delay_type min -max_paths 5 -significant_digits 6 }
redirect -file [file join $precheck_dir constraints.rpt] { report_constraint -all_violators }
redirect -file [file join $precheck_dir references.rpt] { report_reference -hierarchy }
redirect -file [file join $precheck_dir units.rpt] { report_units }
change_names -rules verilog -hierarchy
write -format ddc -hierarchy -output [file join $precheck_dir qingyu_accel.ddc]
write -format verilog -hierarchy -output [file join $precheck_dir qingyu_accel_mapped.v]
write_sdc [file join $precheck_dir precheck_only.sdc]
puts "QINGYU_DC_MARGIN_FINISHED: $precheck_dir"
puts "Review compile/errors, unmapped logic, violations and unconstrained paths."
puts "Scope: accelerator with SRAM macros only; separate FIO adapter excluded."
puts "No full-SoC power, all-corner timing, IO timing or equivalence acceptance claimed."
