set rc [catch {
 set target_library [list $env(Q12_STD_DB)]
 set ram_libraries [list $env(Q12_RAM128_DB) $env(Q12_RAM1024_DB)]
 set synthetic_library dw_foundation.sldb
 set link_library [concat [list *] $target_library $ram_libraries [list dw_foundation.sldb]]
 foreach db [concat $target_library $ram_libraries] {read_db $db}
 define_design_lib WORK -path ./WORK
 if {![analyze -format sverilog -define Q12_USE_VENDOR_MACROS [list $env(Q12_CORE_SOURCE) $env(Q12_PAIR_SOURCE) $env(Q12_SRAM_SOURCE)]]} {error "Analyze failed"}
 elaborate q12_task4
 current_design q12_task4
 if {![link]} {error "Link failed"}
 uniquify
 set hierarchy [get_cells -hierarchical -filter {is_hierarchical == true}]
 set_ungroup $hierarchy false
 set_boundary_optimization $hierarchy false
 foreach ref {RAMSP128X16 RAMSP1024X16} {
  set_dont_touch [get_cells -hierarchical -filter "ref_name == $ref"] true
 }
 create_clock -name core_clk -period 6.666666667 [get_ports clk]
 set_ideal_network [get_ports clk]
 set_clock_uncertainty -setup 0.1 [all_clocks]
 set_clock_uncertainty -hold 0.02 [all_clocks]
 set_clock_transition 0.1 [all_clocks]
 set inputs [remove_from_collection [all_inputs] [get_ports clk]]
 set_input_delay -max 1 -clock core_clk $inputs
 set_input_delay -min 0 -clock core_clk $inputs
 set_input_transition 0.1 $inputs
 set_output_delay -max 1 -clock core_clk [all_outputs]
 set_output_delay -min 0 -clock core_clk [all_outputs]
 set_load 0.02 [all_outputs]
 redirect -file check_design_before.rpt {check_design}
 if {![compile -map_effort medium]} {error "Compile failed"}
 write -format verilog -hierarchy -output mapped.v
 write -format ddc -hierarchy -output mapped.ddc
 write_sdc mapped.sdc
 redirect -file area.rpt {report_area -hierarchy}
 redirect -file timing.rpt {report_timing -delay_type max -max_paths 10 -significant_digits 8}
 redirect -file constraints.rpt {report_constraint -all_violators}
 redirect -file check_design.rpt {check_design}
 catch {redirect -file units.rpt {report_units}}
 set area 0.0
 set macro_area 0.0
 set macro_count 0
 foreach_in_collection c [get_cells -hierarchical -filter {is_hierarchical == false}] {
  set ref [get_attribute $c ref_name]
  if {$ref eq "**logic_0**" || $ref eq "**logic_1**"} {continue}
  set lib [get_lib_cells -quiet -of_objects $c]
  if {[sizeof_collection $lib]!=1} {error "Unresolved leaf cell"}
  set leaf_area [get_attribute $lib area]
  if {![string is double -strict $leaf_area]} {error "Missing leaf library area"}
  set area [expr {$area+$leaf_area}]
  if {[regexp {^RAMSP(128|1024)X16$} $ref]} {
   set macro_area [expr {$macro_area+$leaf_area}]
   incr macro_count
  }
 }
 if {$macro_count!=36} {error "Unexpected private macro count: $macro_count"}
 set paths [get_timing_paths -delay_type max -max_paths 1]
 if {[sizeof_collection $paths]!=1} {error "No timed path"}
 set slack [get_attribute $paths slack]
 set f [open metrics.txt w]
 puts $f "top=q12_task4"
 puts $f "cell_area_library_units=$area"
 puts $f "macro_area_library_units=$macro_area"
 puts $f "macro_count=$macro_count"
 puts $f "setup_slack_ns=$slack"
 close $f
 puts "Q12_CORE_COMPLETE variant=$env(Q12_VARIANT) area=$area macro_area=$macro_area macro_count=$macro_count slack_ns=$slack"
} message]
if {$rc} {puts "Q12_CORE_FAILED: $message";puts $errorInfo;exit 2}
exit 0
