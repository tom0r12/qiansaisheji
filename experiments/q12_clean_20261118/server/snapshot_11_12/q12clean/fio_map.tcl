# Standalone accelerator subsystem (qingyu_q12_stream_fio = u_fio + all private SRAM macros)
# 5-corner bc_wc synthesis at 150 MHz (max = ss_v0p99_-40c, min = ff_v1p21_-40c) on exact staged RTL.
proc q12_optional_report {name command} {
 puts "Q12_OPTIONAL_REPORT_BEGIN=$name"
 if {[catch {redirect -file $name $command} message]} {
  set f [open $name a];puts $f "Q12_REPORT_UNAVAILABLE: $message";close $f
  puts "Q12_REPORT_UNAVAILABLE=$name: $message"
 }
 puts "Q12_OPTIONAL_REPORT_END=$name"
}
proc q12_strip_opcond {sdc_file} {
 set fin [open $sdc_file r];set lines [split [read $fin] "\n"];close $fin
 set fout [open $sdc_file w]
 foreach ln $lines {
  if {[regexp {^\s*set_operating_conditions\b} $ln]} {continue}
  puts $fout $ln
 }
 close $fout
}
set rc [catch {
 set package $env(Q12_PACKAGE)
 set q12_gate [expr {[info exists env(Q12_GATE)] ? $env(Q12_GATE) : "1"}]
 source [file join $package hardware sources.tcl]
 source [file join $package audit.tcl]
 set ::env(Q12_EXPECT_4096) 0
 set search_path [concat $Q12_INCLUDES $search_path]
 set ss_dbs [list $env(Q12_SS_STD_DB) $env(Q12_SS_RAM128_DB) $env(Q12_SS_RAM1024_DB) $env(Q12_SS_RAM4096_DB)]
 set ff_dbs [list $env(Q12_FF_STD_DB) $env(Q12_FF_RAM128_DB) $env(Q12_FF_RAM1024_DB) $env(Q12_FF_RAM4096_DB)]
 foreach db [concat $ss_dbs $ff_dbs] {
  if {![file readable $db]} {error "Missing corner DB: $db"}
  read_db $db
 }
 set target_library [list $env(Q12_SS_STD_DB)]
 set synthetic_library dw_foundation.sldb
 set link_library [concat [list *] $ss_dbs [list dw_foundation.sldb]]
 foreach sdb $ss_dbs fdb $ff_dbs {set_min_library $sdb -min_version $fdb}
 define_design_lib WORK -path ./WORK
 set_svf fio_mapped.svf
 catch {set hdlin_enable_hier_map true}
 if {![analyze -format sverilog -define $Q12_DEFINES $Q12_SOURCES]} {error "Analyze failed"}
 elaborate qingyu_q12_stream_fio
 current_design qingyu_q12_stream_fio
 if {![link]} {error "Link failed"}
 catch {set_verification_top}
 uniquify
 set hierarchy [get_cells -hierarchical -filter {is_hierarchical == true}]
 set_ungroup $hierarchy false
 set_boundary_optimization $hierarchy false
 q12_inventory before
 foreach ref {RAMSP128X16 RAMSP1024X16} {
  set_dont_touch [get_cells -hierarchical -filter "ref_name == $ref"] true
 }
 set_operating_conditions -max ss_v0p99_-40c -max_library scc40nll_vhsc40_rvt_ss_v0p99_-40c_basic -min ff_v1p21_-40c -min_library scc40nll_vhsc40_rvt_ff_v1p21_-40c_basic
 create_clock -name core_clk -period 6.666666667 [get_ports clk]
 set_ideal_network [get_ports clk]
 set_fix_hold [get_clocks core_clk]
 set_clock_uncertainty -setup 0.1 [get_clocks core_clk]
 set_clock_uncertainty -hold 0.045 [get_clocks core_clk]
 set_clock_transition 0.1 [get_clocks core_clk]
 set timed_inputs [remove_from_collection [all_inputs] [get_ports clk]]
 set_input_delay -max 1.0 -clock core_clk $timed_inputs
 set_input_delay -min 0.0 -clock core_clk $timed_inputs
 set_input_transition 0.1 $timed_inputs
 set_output_delay -max 1.0 -clock core_clk [all_outputs]
 set_output_delay -min 0.0 -clock core_clk [all_outputs]
 set_load 0.02 [all_outputs]
 if {$q12_gate} {
  if {[catch {set_clock_gating_style -sequential_cell latch -positive_edge_logic {integrated} -control_point before -minimum_bitwidth 3 -max_fanout 64} m]} {
   set_clock_gating_style -sequential_cell latch -positive_edge_logic {and} -control_point before -minimum_bitwidth 3 -max_fanout 64
  }
 }
 puts Q12_FIO_COMPILE_BEGIN
 if {$q12_gate} {
  set ok [compile_ultra -gate_clock -no_autoungroup -no_boundary_optimization]
 } else {
  set ok [compile_ultra -no_autoungroup -no_boundary_optimization]
 }
 if {!$ok} {error "FIO compile_ultra failed"}
 set wns [get_attribute -quiet [get_timing_paths -delay_type max -max_paths 1] slack]
 set whs [get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]
 puts "Q12_FIO_POST_COMPILE WNS=$wns WHS=$whs"
 if {$wns ne "" && [lindex [lsort -real $wns] 0] < 0} {
  set_critical_range 0.4 [current_design]
  if {![compile_ultra -incremental -no_autoungroup -no_boundary_optimization]} {error "FIO incremental setup failed"}
  puts "Q12_FIO_INC_DONE WNS=[get_attribute -quiet [get_timing_paths -delay_type max -max_paths 1] slack]"
 }
 set whs [get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]
 if {$whs ne "" && [lindex [lsort -real $whs] 0] < 0} {
  set hok 0
  foreach hcmd {{compile -incremental_mapping -only_hold_time} {compile -incremental -only_hold_time}} {
   if {![catch {set hr [eval $hcmd]} hm] && $hr} {set hok 1; puts "Q12_FIO_HOLDFIX_USED=$hcmd"; break}
  }
  if {!$hok} {error "FIO holdfix failed"}
  puts "Q12_FIO_HOLDFIX_DONE WNS=[get_attribute -quiet [get_timing_paths -delay_type max -max_paths 1] slack] WHS=[get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]"
 }
 set wns2 [get_attribute -quiet [get_timing_paths -delay_type max -max_paths 1] slack]
 if {$wns2 ne "" && [lindex [lsort -real $wns2] 0] < 0} {
  set_critical_range 0.4 [current_design]
  compile_ultra -incremental -no_autoungroup -no_boundary_optimization
  set whs2 [get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]
  if {$whs2 ne "" && [lindex [lsort -real $whs2] 0] < 0} {
   compile -incremental_mapping -only_hold_time
  }
 }
 set_clock_uncertainty -hold 0.02 [get_clocks core_clk]
 if {![link]} {error "FIO mapped link failed"}
 write -format verilog -hierarchy -output fio_mapped.v
 write -format ddc -hierarchy -output fio_mapped.ddc
 write_sdc fio_mapped.sdc
 q12_strip_opcond fio_mapped.sdc
 set_svf -off
 q12_inventory after
 redirect -file fio_area.rpt {report_area -hierarchy}
 redirect -file fio_timing_max.rpt {report_timing -delay_type max -max_paths 20 -significant_digits 8}
 redirect -file fio_timing_min.rpt {report_timing -delay_type min -max_paths 20 -significant_digits 8}
 redirect -file fio_constraints.rpt {report_constraint -all_violators}
 q12_optional_report fio_qor.rpt {report_qor}
 q12_optional_report fio_loops.rpt {report_timing -loops}
 q12_optional_report fio_clock_gating.rpt {report_clock_gating}
 puts Q12_FIO_SYNTH_COMPLETE
} message]
if {$rc} {puts "Q12_FIO_SYNTH_FAILED: $message";puts $errorInfo;exit 2}
exit 0
