set rc [catch {
 set target_library [list $env(Q12_STD_DB)]
 set link_library [concat [list *] $target_library [list dw_foundation.sldb]]
 set synthetic_library dw_foundation.sldb
 read_db $env(Q12_STD_DB)
 define_design_lib WORK -path ./WORK
 set_svf mapped.svf
 analyze -format sverilog $env(Q12_DECODER_SOURCE)
 elaborate q12_rice_decoder
 current_design q12_rice_decoder
 if {![link]} {error "Decoder link failed"}
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
 if {![compile -map_effort medium]} {error "Decoder compile failed"}
 write -format verilog -hierarchy -output mapped.v
 write -format ddc -hierarchy -output mapped.ddc
 write_sdc mapped.sdc
 set_svf -off
 redirect -file area.rpt {report_area -hierarchy}
 redirect -file setup.rpt {report_timing -delay_type max -max_paths 10 -significant_digits 8}
 redirect -file hold.rpt {report_timing -delay_type min -max_paths 10 -significant_digits 8}
 redirect -file constraints.rpt {report_constraint -all_violators}
 redirect -file check_timing.rpt {check_timing}
 set area 0.0
 foreach_in_collection cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
  set ref [get_attribute $cell ref_name]
  if {$ref eq "**logic_0**" || $ref eq "**logic_1**"} {continue}
  set lib [get_lib_cells -of_objects $cell]
  if {[sizeof_collection $lib]!=1} {error "Unresolved library cell"}
  set area [expr {$area+[get_attribute $lib area]}]
 }
 set slack [get_attribute [get_timing_paths -delay_type max -max_paths 1] slack]
 set f [open metrics.txt w]
 puts $f "area_um2=$area"
 puts $f "setup_slack_ns=$slack"
 close $f
 puts "Q12_DECODER_COMPLETE area=$area slack=$slack"
} message]
if {$rc} {puts "Q12_DECODER_FAILED: $message";puts $errorInfo;exit 2}
exit 0
