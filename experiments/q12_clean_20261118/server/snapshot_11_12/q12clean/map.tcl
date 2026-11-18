# Whole-SoC mapping for the clean Q12 candidate (official SCC40NLL RVT TT setup + 5-corner bc_wc hold).
# Low-power: DC clock-gating insertion on enable registers (Q12_GATE=1).
# Area: compile_ultra with hierarchy preserved (Q12_COMPILE=ultra|medium).
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
 set q12_compile [expr {[info exists env(Q12_COMPILE)] ? $env(Q12_COMPILE) : "ultra"}]
 set q12_gate [expr {[info exists env(Q12_GATE)] ? $env(Q12_GATE) : "1"}]
 puts "Q12_SYNTH_OPTIONS compile=$q12_compile gate=$q12_gate"
 source [file join $package hardware sources.tcl]
 source [file join $package audit.tcl]
 set search_path [concat $Q12_INCLUDES $search_path]
 set target_library [list $env(Q12_STD_DB)]
 set sram_libraries [list $env(Q12_RAM128_DB) $env(Q12_RAM1024_DB) $env(Q12_RAM4096_DB)]
 set synthetic_library dw_foundation.sldb
 set link_library [concat [list *] $target_library $sram_libraries [list dw_foundation.sldb]]
 foreach db [concat $target_library $sram_libraries] {read_db $db}
 if {[sizeof_collection [get_libs -quiet *scc40nll_vhsc40_rvt_tt*]]!=1} {error "Official SCC40NLL RVT TT library required"}
 define_design_lib WORK -path ./WORK
 set_svf mapped.svf
 catch {set hdlin_enable_hier_map true}
 if {![analyze -format sverilog -define $Q12_DEFINES $Q12_SOURCES]} {error "Analyze failed"}
 elaborate qingyu_e203_soc_top
 current_design qingyu_e203_soc_top
 if {![link]} {error "Link failed"}
 catch {set_verification_top}
 uniquify
 set hierarchy [get_cells -hierarchical -filter {is_hierarchical == true}]
 set_ungroup $hierarchy false
 set_boundary_optimization $hierarchy false
 q12_inventory before
 foreach ref {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
  set_dont_touch [get_cells -hierarchical -filter "ref_name == $ref"] true
 }
 create_clock -name hfext_clk -period 6.666666667 [get_ports hfextclk]
 create_clock -name lfext_clk -period 30517.578125 [get_ports lfextclk]
 create_clock -name jtag_clk -period 100 [get_ports io_pads_jtag_TCK_i_ival]
 create_generated_clock -name core_clk -source [get_ports hfextclk] -divide_by 1 [get_pins u_e203_subsys_top/qingyu_bus_clk]
 set_ideal_network [get_ports {hfextclk lfextclk io_pads_jtag_TCK_i_ival}]
 set_ideal_network [get_pins u_e203_subsys_top/qingyu_bus_clk]
 set_clock_groups -asynchronous -group [get_clocks {hfext_clk core_clk}] -group [get_clocks lfext_clk] -group [get_clocks jtag_clk]
 set_fix_hold [get_clocks {hfext_clk core_clk}]
 set q12_inspect_clk [get_pins -quiet u_e203_subsys_top/u_e203_subsys_main/u_e203_cpu_top/inspect_core_clk]
 puts "Q12_INSPECT_CLK_PINS=[sizeof_collection $q12_inspect_clk]"
 if {[sizeof_collection $q12_inspect_clk]!=1} {error "inspect_core_clk pin not found"}
 set_false_path -through $q12_inspect_clk
 set_clock_uncertainty -setup 0.1 [all_clocks]
 set_clock_uncertainty -hold 0.02 [all_clocks]
 set_clock_transition 0.1 [all_clocks]
 set inputs [remove_from_collection [all_inputs] [get_ports {hfextclk lfextclk io_pads_jtag_TCK_i_ival}]]
 set_input_delay -max 1 -clock hfext_clk $inputs
 set_input_delay -min 0 -clock hfext_clk $inputs
 set_input_delay -max 3 -clock hfext_clk [get_ports {io_pads_gpioA_i_ival*}]
 set_input_delay -min 0.5 -clock hfext_clk [get_ports {io_pads_gpioA_i_ival*}]
 set_input_transition 0.1 $inputs
 set_output_delay -max 1 -clock hfext_clk [all_outputs]
 set_output_delay -min 0 -clock hfext_clk [all_outputs]
 set_load 0.02 [all_outputs]
 if {$q12_gate} {
  if {[catch {set_clock_gating_style -sequential_cell latch -positive_edge_logic {integrated} -control_point before -minimum_bitwidth 3 -max_fanout 64} m]} {
   puts "Q12_ICG_INTEGRATED_UNAVAILABLE=$m"
   set_clock_gating_style -sequential_cell latch -positive_edge_logic {and} -control_point before -minimum_bitwidth 3 -max_fanout 64
  }
 }
 redirect -file check_design_before.rpt {check_design}
 q12_optional_report check_timing_before.rpt {check_timing}
 puts Q12_COMPILE_BEGIN
 if {$q12_compile eq "ultra"} {
  if {$q12_gate} {set ok [compile_ultra -gate_clock -no_autoungroup -no_boundary_optimization]} else {set ok [compile_ultra -no_autoungroup -no_boundary_optimization]}
 } else {
  if {$q12_gate} {set ok [compile -map_effort medium -gate_clock]} else {set ok [compile -map_effort medium]}
 }
 if {!$ok} {error "Compile failed"}
 puts Q12_COMPILE_END
 set q12_wns [get_attribute -quiet [get_timing_paths -delay_type max -max_paths 1] slack]
 set q12_whs [get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]
 puts "Q12_POST_COMPILE_WNS=$q12_wns WHS=$q12_whs"
 if {$q12_wns ne "" && [lindex [lsort -real $q12_wns] 0] < 0} {
  redirect -file timing_pre_incremental.rpt {report_timing -delay_type max -max_paths 5 -significant_digits 4}
  set_critical_range 0.3 [current_design]
  if {![compile_ultra -incremental -no_autoungroup -no_boundary_optimization]} {error "Incremental compile failed"}
  puts "Q12_INCREMENTAL_DONE WNS=[get_attribute -quiet [get_timing_paths -delay_type max -max_paths 1] slack] WHS=[get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]"
 }
 # If FF min libraries are supplied, activate bc_wc (max=tt_v1p1_25c, min=ff_v1p21_-40c)
 # with 0.045 ns hold uncertainty so hold closes across all 5 corners (including ff_m40c and ff_125c).
 if {[info exists env(Q12_FF_STD_DB)] && $env(Q12_FF_STD_DB) ne ""} {
  set ff_dbs [list $env(Q12_FF_STD_DB) $env(Q12_FF_RAM128_DB) $env(Q12_FF_RAM1024_DB) $env(Q12_FF_RAM4096_DB)]
  set tt_dbs [concat $target_library $sram_libraries]
  foreach fdb $ff_dbs {
   if {![file readable $fdb]} {error "Missing FF min DB: $fdb"}
   read_db $fdb
  }
  foreach tdb $tt_dbs fdb $ff_dbs {set_min_library $tdb -min_version $fdb}
  set_operating_conditions -max tt_v1p1_25c -max_library scc40nll_vhsc40_rvt_tt_v1p1_25c_basic -min ff_v1p21_-40c -min_library scc40nll_vhsc40_rvt_ff_v1p21_-40c_basic
  set_clock_uncertainty -hold 0.045 [all_clocks]
  puts "Q12_BCWC_HOLD_ARMED WHS=[get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]"
 }
 set q12_whs [get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]
 if {$q12_whs ne "" && [lindex [lsort -real $q12_whs] 0] < 0} {
  redirect -file timing_min_pre_holdfix.rpt {report_timing -delay_type min -max_paths 5 -significant_digits 4}
  set q12_hold_ok 0
  foreach q12_cmd {{compile -incremental_mapping -only_hold_time} {compile -incremental -only_hold_time} {compile_ultra -incremental -only_hold_time}} {
   puts "Q12_HOLDFIX_TRY=$q12_cmd"
   if {![catch {set q12_r [eval $q12_cmd]} q12_m] && $q12_r} {set q12_hold_ok 1; puts "Q12_HOLDFIX_USED=$q12_cmd"; break}
   puts "Q12_HOLDFIX_FAILED=$q12_cmd: $q12_m"
  }
  if {!$q12_hold_ok} {error "No hold-fixing command succeeded"}
  puts "Q12_HOLDFIX_DONE WNS=[get_attribute -quiet [get_timing_paths -delay_type max -max_paths 1] slack] WHS=[get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]"
 }
 set q12_wns2 [get_attribute -quiet [get_timing_paths -delay_type max -max_paths 1] slack]
 if {$q12_wns2 ne "" && [lindex [lsort -real $q12_wns2] 0] < 0} {
  set_critical_range 0.3 [current_design]
  if {![compile_ultra -incremental -no_autoungroup -no_boundary_optimization]} {error "Post-hold incremental setup compile failed"}
  set q12_whs2 [get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]
  if {$q12_whs2 ne "" && [lindex [lsort -real $q12_whs2] 0] < 0} {
   compile -incremental_mapping -only_hold_time
  }
  puts "Q12_POST_HOLD_RESYNC WNS=[get_attribute -quiet [get_timing_paths -delay_type max -max_paths 1] slack] WHS=[get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]"
 }
 set_clock_uncertainty -hold 0.02 [all_clocks]
 if {![link]} {error "Mapped link failed"}
 write -format verilog -hierarchy -output mapped.v
 write -format ddc -hierarchy -output mapped.ddc
 write_sdc mapped.sdc
 q12_strip_opcond mapped.sdc
 set_svf -off
 q12_inventory after
 q12_inventory mapped
 set design_ok 0
 redirect -file check_design_after.rpt {set design_ok [check_design]}
 if {!$design_ok} {error "Mapped check_design failed"}
 source [file join $package hardware report_explicit_area.tcl]
 q12_report_explicit_area
 redirect -file area.rpt {report_area -hierarchy}
 redirect -file timing_max.rpt {report_timing -delay_type max -max_paths 20 -significant_digits 8}
 redirect -file timing_min.rpt {report_timing -delay_type min -max_paths 20 -significant_digits 8}
 redirect -file constraints.rpt {report_constraint -all_violators}
 q12_optional_report qor.rpt {report_qor}
 set tg [open timing_groups.rpt w];close $tg
 foreach_in_collection g [get_path_groups *] {
  set gn [get_object_name $g]
  redirect -append -file timing_groups.rpt {puts "Q12_GROUP_MAX=$gn"}
  catch {redirect -append -file timing_groups.rpt {report_timing -delay_type max -max_paths 1 -group $gn -input_pins -nets -transition_time -capacitance -significant_digits 4}}
  redirect -append -file timing_groups.rpt {puts "Q12_GROUP_MIN=$gn"}
  catch {redirect -append -file timing_groups.rpt {report_timing -delay_type min -max_paths 1 -group $gn -significant_digits 4}}
 }
 q12_optional_report high_fanout.rpt {report_net_fanout -high_fanout -threshold 200}
 q12_optional_report loops.rpt {report_timing -loops}
 q12_optional_report clock_gating.rpt {report_clock_gating}
 q12_optional_report check_timing_after.rpt {check_timing}
 q12_optional_report clocks.rpt {report_clock -attributes}
 q12_optional_report units.rpt {report_units}
 q12_optional_report power_dc.rpt {report_power -hierarchy -levels 3}
 puts Q12_FINAL_SYNTH_COMPLETE
} message]
if {$rc} {puts "Q12_FINAL_SYNTH_FAILED: $message";puts $errorInfo;exit 2}
exit 0
