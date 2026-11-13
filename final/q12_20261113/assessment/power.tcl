# Exact-window RTL SAIF annotated onto the exact mapped whole SoC.
proc q12_optional_report {name command} {
 puts "Q12_OPTIONAL_REPORT_BEGIN=$name"
 if {[catch {redirect -file $name $command} message]} {
  set f [open $name a];puts $f "Q12_REPORT_UNAVAILABLE: $message";close $f
  puts "Q12_REPORT_UNAVAILABLE=$name: $message"
 }
 puts "Q12_OPTIONAL_REPORT_END=$name"
}
set rc [catch {
 set power_enable_analysis true
 set power_analysis_mode averaged
 set link_path [concat [list *] $env(Q12_LIBRARIES)]
 read_verilog $env(Q12_NETLIST)
 current_design qingyu_e203_soc_top
 if {![link_design qingyu_e203_soc_top]} {error "Power link failed"}
 source [file join $env(Q12_PACKAGE) audit.tcl]
 q12_inventory power
 read_sdc $env(Q12_SDC)
 redirect -file read_saif.rpt {read_saif -strip_path tb_q12soc/dut $env(Q12_SAIF)}
 redirect -file activity_before.rpt {report_switching_activity}
 redirect -file analysis_coverage.rpt {report_analysis_coverage}
 redirect -file check_timing.rpt {check_timing}
 redirect -file setup.rpt {report_timing -delay_type max -max_paths 20 -significant_digits 8}
 redirect -file hold.rpt {report_timing -delay_type min -max_paths 20 -significant_digits 8}
 redirect -file check_power.rpt {check_power}
 update_power
 redirect -file activity_after.rpt {report_switching_activity}
 redirect -file power.rpt {report_power -verbose}
 redirect -file power_hierarchy.rpt {report_power -hierarchy}
 redirect -file units.rpt {report_units}
 redirect -file power_units.rpt {report_units -power}
 q12_optional_report pin_attributes.rpt {list_attributes -application -class pin}
 # Compatibility-sensitive fields are diagnostic, never silently accepted.
 # Unsupported source metadata becomes UNKNOWN and closes the acceptance gate.
 set f [open macro_pin_activity.tsv w]
 puts $f "instance\tpin\tdirection\ttoggle_rate\tstatic_probability\ttoggle_source\tprobability_source"
 puts Q12_OPTIONAL_REPORT_BEGIN=macro_pin_activity
 foreach_in_collection cell [get_cells -hierarchical] {
  if {![string match RAMSP* [get_attribute $cell ref_name]]} {continue}
  foreach_in_collection pin [get_pins -of_objects $cell] {
   set direction [get_attribute $pin direction]
   if {$direction ne "in"} {continue}
   set values {}
   foreach attribute {toggle_rate static_probability toggle_rate_source static_probability_source} {
    set value UNKNOWN
    if {[catch {set found [get_attribute -quiet $pin $attribute]}]} {set found ""}
    if {$found ne ""} {set value $found}
    lappend values $value
   }
   puts $f "[get_object_name $cell]\t[get_object_name $pin]\t$direction\t[join $values \t]"
  }
 }
 close $f
 puts Q12_OPTIONAL_REPORT_END=macro_pin_activity
 puts Q12_FINAL_POWER_REPORTS_COMPLETE
} message]
if {$rc} {puts "Q12_FINAL_POWER_FAILED: $message";puts $errorInfo;exit 2}
exit 0
