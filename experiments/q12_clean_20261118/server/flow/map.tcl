# Whole-SoC mapping for the clean Q12 candidate (official SCC40NLL RVT TT).
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
 if {![analyze -format sverilog -define $Q12_DEFINES $Q12_SOURCES]} {error "Analyze failed"}
 elaborate qingyu_e203_soc_top
 current_design qingyu_e203_soc_top
 if {![link]} {error "Link failed"}
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
 if {![link]} {error "Mapped link failed"}
 # Preserve source names (SAIF/inventory paths); the writer escapes when needed.
 write -format verilog -hierarchy -output mapped.v
 write -format ddc -hierarchy -output mapped.ddc
 write_sdc mapped.sdc
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
 q12_optional_report clock_gating.rpt {report_clock_gating}
 q12_optional_report check_timing_after.rpt {check_timing}
 q12_optional_report clocks.rpt {report_clock -attributes}
 q12_optional_report units.rpt {report_units}
 q12_optional_report power_dc.rpt {report_power -hierarchy -levels 3}
 puts Q12_FINAL_SYNTH_COMPLETE
} message]
if {$rc} {puts "Q12_FINAL_SYNTH_FAILED: $message";puts $errorInfo;exit 2}
exit 0
