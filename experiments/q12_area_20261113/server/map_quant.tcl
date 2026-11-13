# Same official TT library and 150 MHz interface budget for both variants.
set rc [catch {
 set target_library [list $env(Q12_STD_DB)]
 set synthetic_library dw_foundation.sldb
 set link_library [concat [list *] $target_library [list dw_foundation.sldb]]
 read_db $env(Q12_STD_DB)
 define_design_lib WORK -path ./WORK
 analyze -format sverilog $env(Q12_QUANT_SOURCE)
 elaborate $env(Q12_QUANT_TOP)
 current_design $env(Q12_QUANT_TOP)
 if {![link]} {error "Link failed"}
 create_clock -name virtual_clk -period 6.666666667
 set_clock_uncertainty -setup 0.1 [all_clocks]
 set_clock_uncertainty -hold 0.02 [all_clocks]
 set_clock_transition 0.1 [all_clocks]
 set_input_delay -max 1 -clock virtual_clk [all_inputs]
 set_input_delay -min 0 -clock virtual_clk [all_inputs]
 set_input_transition 0.1 [all_inputs]
 set_output_delay -max 1 -clock virtual_clk [all_outputs]
 set_output_delay -min 0 -clock virtual_clk [all_outputs]
 set_load 0.02 [all_outputs]
 if {![compile -map_effort medium]} {error "Compile failed"}
 write -format verilog -hierarchy -output mapped.v
 write -format ddc -hierarchy -output mapped.ddc
 redirect -file area.rpt {report_area -hierarchy}
 redirect -file timing.rpt {report_timing -delay_type max -max_paths 3 -significant_digits 8}
 redirect -file constraints.rpt {report_constraint -all_violators}
 redirect -file design.rpt {check_design}
 catch {redirect -file units.rpt {report_units}}
 set area 0.0
 foreach_in_collection c [get_cells -hierarchical -filter {is_hierarchical == false}] {
  set lib [get_lib_cells -quiet -of_objects $c]
  if {[sizeof_collection $lib]!=1} {error "Unresolved leaf cell"}
  set leaf_area [get_attribute $lib area]
  if {![string is double -strict $leaf_area]} {error "Missing leaf library area"}
  set area [expr {$area+$leaf_area}]
 }
 set paths [get_timing_paths -delay_type max -max_paths 1]
 if {[sizeof_collection $paths]!=1} {error "No timed path"}
 set slack [get_attribute $paths slack]
 set f [open metrics.txt w]
 puts $f "top=$env(Q12_QUANT_TOP)"
 puts $f "cell_area_library_units=$area"
 puts $f "setup_slack_ns=$slack"
 close $f
 puts "Q12_QUANT_COMPLETE top=$env(Q12_QUANT_TOP) area=$area slack_ns=$slack"
} message]
if {$rc} {puts "Q12_QUANT_FAILED: $message";puts $errorInfo;exit 2}
exit 0
