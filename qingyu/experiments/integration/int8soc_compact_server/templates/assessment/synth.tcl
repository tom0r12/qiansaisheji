if {[sizeof_collection [get_designs -quiet *]]!=0} {error "Use a fresh Design Compiler session"}
source [file join [file dirname [info script]] common.tcl]
foreach key {WIRE_LOAD_MODE WIRE_LOAD_MODEL WIRE_LOAD_LIBRARY} {if {![info exists $key] || [set $key] eq ""} {error "Missing verified interconnect estimate $key"}}
set search_path [concat $includes $search_path]
foreach library [concat $STD_CELL_LIBS $SRAM_LIBS] {read_db $library}
check_loaded_standard_identity
set target_library $STD_CELL_LIBS
set link_library [concat [list *] $STD_CELL_LIBS $SRAM_LIBS]
file mkdir [file join $work design_work]
define_design_lib WORK -path [file join $work design_work]
set_svf [file join $work qingyu_e203_soc_top.svf]
analyze -format sverilog -define $defines $sources
elaborate qingyu_e203_soc_top
current_design qingyu_e203_soc_top
if {![link]} {error "Full SoC link failed"}
uniquify
set_operating_conditions $OPERATING_CONDITION -library $OPERATING_LIBRARY
set_wire_load_mode $WIRE_LOAD_MODE
set_wire_load_model -name $WIRE_LOAD_MODEL -library $WIRE_LOAD_LIBRARY [current_design]
set hierarchy [get_cells -hierarchical -filter {is_hierarchical == true}]
set_ungroup $hierarchy false
set_boundary_optimization $hierarchy false
foreach macro $REQUIRED_SRAM_MACROS {set_dont_touch [get_cells -hierarchical -filter "ref_name == $macro"] true}
memory_audit precompile
source $PLATFORM_SDC
clock_period_gate
redirect -file [file join $work check_design_pre.rpt] {set design_ok [check_design]}
if {!$design_ok} {error "Precompile check_design failed"}
redirect -file [file join $work units.rpt] {report_units}
redirect -file [file join $work clocks.rpt] {report_clock}
redirect -file [file join $work ports.rpt] {report_port -verbose}
timed_endpoint_gate
redirect -tee -file [file join $work compile.log] {set compiled [compile_ultra -no_autoungroup]}
if {!$compiled} {error "Compilation failed"}
memory_audit postcompile
redirect -file [file join $work check_design_post.rpt] {set design_ok [check_design]}
if {!$design_ok} {error "Mapped design is invalid"}
redirect -file [file join $work area.rpt] {report_area -hierarchy}
redirect -file [file join $work references.rpt] {report_reference -hierarchy}
redirect -file [file join $work timing_max.rpt] {report_timing -delay_type max -max_paths 50 -significant_digits 6}
redirect -file [file join $work timing_min.rpt] {report_timing -delay_type min -max_paths 50 -significant_digits 6}
redirect -file [file join $work constraints.rpt] {report_constraint -all_violators}
set totals [dict create];set count 0
set f [open [file join $work leaf_area.tsv] w]
puts $f "instance\treference\tclass\tlibrary_area\tarea_um2"
foreach_in_collection cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
 set name [get_object_name $cell];set reference [get_attribute $cell ref_name]
 set libcell [get_lib_cells -quiet -of_objects $cell]
 if {[sizeof_collection $libcell]!=1} {error "Unmapped/black-box leaf $name"}
 set area [get_attribute $libcell area]
 if {![string is double -strict $area] || $area<=0} {error "Missing/nonpositive cell area $name"}
 set category [area_class $name $reference]
 if {[dict exists $SRAM_AREA_UM2 $reference]} {set um2 [dict get $SRAM_AREA_UM2 $reference]
 } else {set um2 [expr {$area*$AREA_UNIT_TO_UM2}]}
 if {![dict exists $totals $category]} {dict set totals $category 0.0}
 dict set totals $category [expr {[dict get $totals $category]+$um2}]
 puts $f "$name\t$reference\t$category\t$area\t$um2";incr count
}
close $f
set all_area 0.0;set included 0.0
dict for {category amount} $totals {set all_area [expr {$all_area+$amount}];if {[string match included_* $category]} {set included [expr {$included+$amount}]}}
foreach category {included_new_bus_merges included_compute_logic included_transport_logic included_codec_logic included_reorder_logic included_engine_control_logic included_fio_mmio_logic included_private_macro included_shared_interface_logic excluded_fixed_shared_macro excluded_cpu_tcm_macro excluded_reused_cpu_logic excluded_fixed_bus_peripheral_logic} {
 if {![dict exists $totals $category] || [dict get $totals $category]<=0} {error "Accounting boundary missing: $category"}
}
dict set provenance area_categories_um2 $totals
dict set provenance full_digital_soc_area_um2 $all_area
dict set provenance incremental_score_scope_area_um2 $included
dict set provenance incremental_score_scope_area_mm2 [expr {$included/1000000.0}]
dict set provenance mapped_leaf_count $count
change_names -rules verilog -hierarchy
write -format ddc -hierarchy -output [file join $work qingyu_e203_soc_top.ddc]
write -format verilog -hierarchy -output [file join $work qingyu_e203_soc_top_mapped.v]
write_sdc [file join $work qingyu_e203_soc_top.sdc]
set_svf -off
foreach name {qingyu_e203_soc_top.ddc qingyu_e203_soc_top_mapped.v qingyu_e203_soc_top.sdc qingyu_e203_soc_top.svf} {dict set provenance outputs_sha256 $name [file_sha [file join $work $name]]}
verify_frozen_inputs
dict set provenance status synthesized_pending_STA_Formality_and_activity_review
save_provenance
puts "QINGYU_FULL_BUS_SYNTHESIS_ARTIFACTS $work"
puts "Area excludes only enumerated reused boundaries; full-SoC power must include every boundary."
