# Incremental Design Compiler entry point; run in a NEW dc_shell session.
# No server execution is initiated by this file's preparation.
#
# QINGYU_SYNTH_CONFIG names a server-local Tcl file defining:
#   STD_CELL_LIBS SRAM_LIBS                       (lists of real .db files)
#   OPERATING_CONDITION OPERATING_LIBRARY        (explicit selected PVT)
#   WIRE_LOAD_MODEL WIRE_LOAD_LIBRARY WIRE_LOAD_MODE
#   LIBRARY_PROVENANCE TIMING_PROVENANCE AREA_UNIT_PROVENANCE
#   AREA_UNIT_TO_UM2                             (verified library area unit)
# and all variables required by constraints/accelerator_explicit_io.sdc:
#   CLOCK_PERIOD_NS INPUT_DELAY_MIN_NS INPUT_DELAY_MAX_NS
#   OUTPUT_DELAY_MIN_NS OUTPUT_DELAY_MAX_NS SETUP_UNCERTAINTY_NS
#   HOLD_UNCERTAINTY_NS INPUT_SLEW_NS CLOCK_SLEW_NS OUTPUT_LOAD_PF
# The existing formal clock requirement is 6.666666667 ns. Set that explicitly
# unless the user's platform contract supplies another value. IO values have
# no defaults: preserve their actual platform provenance, do not guess them.
# Library timing/capacitance units must be ns/pF (inspect units.rpt).
#
# Optional env: QINGYU_PROJECT_ROOT, QINGYU_CANDIDATE (opt15_validate4 default,
# opt13_row8 supported for comparison), QINGYU_RUN_PARENT (existing directory).
# Requires sha256sum to freeze every RTL/config/library input by content.
# Output: fresh directory, mapped netlist/DDC/SDC/SVF, reports, area TSV,
# Tcl-dict provenance. This is NOT full-SoC power or multicorner/LEC signoff.

if {[sizeof_collection [get_designs -quiet *]] != 0} {
    error "Use a fresh dc_shell session; existing designs would contaminate scope"
}
set project_root [file normalize [file join [file dirname [info script]] ..]]
if {[info exists env(QINGYU_PROJECT_ROOT)]} {
    set project_root [file normalize $env(QINGYU_PROJECT_ROOT)]
}
if {![info exists env(QINGYU_SYNTH_CONFIG)]} {error "QINGYU_SYNTH_CONFIG is required"}
set config_path [file normalize $env(QINGYU_SYNTH_CONFIG)]
if {![file isfile $config_path]} {error "Missing config: $config_path"}
source $config_path
foreach required {
    STD_CELL_LIBS SRAM_LIBS OPERATING_CONDITION OPERATING_LIBRARY
    WIRE_LOAD_MODEL WIRE_LOAD_LIBRARY WIRE_LOAD_MODE
    LIBRARY_PROVENANCE TIMING_PROVENANCE AREA_UNIT_PROVENANCE AREA_UNIT_TO_UM2
    CLOCK_PERIOD_NS INPUT_DELAY_MIN_NS INPUT_DELAY_MAX_NS
    OUTPUT_DELAY_MIN_NS OUTPUT_DELAY_MAX_NS SETUP_UNCERTAINTY_NS
    HOLD_UNCERTAINTY_NS INPUT_SLEW_NS CLOCK_SLEW_NS OUTPUT_LOAD_PF
} {
    if {![info exists $required] || [set $required] eq ""} {error "Config must define $required"}
}
if {![string is double -strict $AREA_UNIT_TO_UM2] || $AREA_UNIT_TO_UM2 <= 0} {
    error "AREA_UNIT_TO_UM2 must be a positive verified conversion"
}
set candidate opt15_validate4
if {[info exists env(QINGYU_CANDIDATE)]} {set candidate $env(QINGYU_CANDIDATE)}
switch -- $candidate {
    opt15_validate4 {set expected_private128 37}
    opt13_row8 {set expected_private128 41}
    default {error "Unreviewed candidate: $candidate; audit wrapper wiring and memory counts first"}
}
set candidate_rtl [file join $project_root experiments h1500v $candidate rtl]
set sources [list \
    [file join $project_root rtl asic qingyu_sram16.sv] \
    [file join $project_root rtl asic qingyu_banked_sram.sv] \
    [file join $candidate_rtl asic qingyu_shared_sram_mp.sv] \
    [file join $candidate_rtl qingyu_accel.sv] \
    [file join $candidate_rtl qingyu_fio.sv] \
    [file join $project_root rtl assessment qingyu_score_top.sv]]
set defines {QINGYU_BLOCK_COPY QINGYU_READ_AHEAD QINGYU_FAST_TASK QINGYU_DOUBLE_BUFFER QINGYU_PIPE_MAC QINGYU_OUT16}
set sdc_path [file join $project_root constraints accelerator_explicit_io.sdc]
set script_path [file normalize [info script]]
set input_files [concat $sources $STD_CELL_LIBS $SRAM_LIBS [list $config_path $sdc_path $script_path]]
proc input_sha256 {path} {
    if {![file isfile $path] || ![file readable $path]} {error "Missing/unreadable input: $path"}
    set result [exec sha256sum -- $path]
    if {![regexp {^([0-9a-fA-F]{64})\s} $result -> hash]} {error "Cannot hash $path"}
    return [string tolower $hash]
}
set input_hashes [dict create]
foreach path $input_files {dict set input_hashes [file normalize $path] [input_sha256 $path]}
set run_parent [file join $project_root reports]
if {[info exists env(QINGYU_RUN_PARENT)]} {set run_parent [file normalize $env(QINGYU_RUN_PARENT)]}
if {![file isdirectory $run_parent]} {error "QINGYU_RUN_PARENT must name an existing directory"}
set output_dir [file join $run_parent qingyu_verify_${candidate}_score_[clock seconds]_[pid]]
if {[file exists $output_dir]} {error "Refusing to reuse $output_dir"}
file mkdir [file join $output_dir work]
file copy $config_path [file join $output_dir platform_config.tcl]
set manifest [dict create schema qingyu-incremental-synthesis-v1 candidate $candidate \
    top qingyu_score_top defines $defines source_files $sources input_sha256 $input_hashes \
    library_provenance $LIBRARY_PROVENANCE timing_provenance $TIMING_PROVENANCE \
    area_unit_provenance $AREA_UNIT_PROVENANCE area_unit_to_um2 $AREA_UNIT_TO_UM2 \
    operating_condition $OPERATING_CONDITION operating_library $OPERATING_LIBRARY \
    wire_load_model $WIRE_LOAD_MODEL wire_load_library $WIRE_LOAD_LIBRARY \
    wire_load_mode $WIRE_LOAD_MODE scope {FIO plus private memories plus complete six-port shared arbitration} \
    area_exclusion {Only 64 RAMSP4096X16 leaf instances below u_shared} \
    limitations {No reused E203/fixed peripherals in boundary; not full-SoC power, LEC or multicorner signoff}]
foreach key {CLOCK_PERIOD_NS INPUT_DELAY_MIN_NS INPUT_DELAY_MAX_NS OUTPUT_DELAY_MIN_NS OUTPUT_DELAY_MAX_NS SETUP_UNCERTAINTY_NS HOLD_UNCERTAINTY_NS INPUT_SLEW_NS CLOCK_SLEW_NS OUTPUT_LOAD_PF} {
    dict set manifest timing_parameters $key [set $key]
}
proc save_manifest {} {
    global manifest output_dir
    set stream [open [file join $output_dir provenance.tcl] w]
    puts $stream [list set synthesis_provenance $manifest]
    close $stream
}
dict set manifest state inputs_frozen
save_manifest
puts "QINGYU_SCORE_RUN_DIRECTORY: $output_dir"
set_svf [file join $output_dir qingyu_score_top.svf]
foreach library [concat $STD_CELL_LIBS $SRAM_LIBS] {read_db $library}
set target_library $STD_CELL_LIBS
set link_library [concat [list *] $STD_CELL_LIBS $SRAM_LIBS]
define_design_lib WORK -path [file join $output_dir work]
analyze -format sverilog -define $defines $sources
elaborate qingyu_score_top
current_design qingyu_score_top
if {![link]} {error "Link failed; a memory library or functional module is missing"}
uniquify
set_operating_conditions $OPERATING_CONDITION -library $OPERATING_LIBRARY
set_wire_load_mode $WIRE_LOAD_MODE
set_wire_load_model -name $WIRE_LOAD_MODEL -library $WIRE_LOAD_LIBRARY [current_design]
# Keep accounting boundaries, without disabling synthesis of their logic.
set_ungroup [get_cells {u_fio u_shared}] false
set_boundary_optimization [get_cells {u_fio u_shared}] false
# Preserve source-structure memories for conservative and reproducible area.
# A separately proven memory-merge experiment may be smaller; do not silently
# reinterpret it as this source-preserving run or waive an unexpected count.
foreach macro {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
    set macros [get_cells -hierarchical -filter "ref_name == $macro"]
    if {[sizeof_collection $macros] == 0} {error "No instances of required $macro"}
    set_dont_touch $macros true
}
proc check_memory_scope {stage} {
    global expected_private128 output_dir
    set counts [dict create shared4096 0 private128 0 private1024 0]
    set stream [open [file join $output_dir memories_${stage}.tsv] w]
    puts $stream "instance\treference\tscore_area_class"
    foreach_in_collection cell [get_cells -hierarchical] {
        set reference [get_attribute $cell ref_name]
        if {![string match RAMSP* $reference]} {continue}
        set name [get_object_name $cell]
        if {[string match {u_shared/*} $name] && $reference eq "RAMSP4096X16"} {
            dict incr counts shared4096
            set classification excluded_fixed_shared_macro
        } elseif {[string match {u_fio/*} $name] && $reference eq "RAMSP128X16"} {
            dict incr counts private128
            set classification included_private_macro
        } elseif {[string match {u_fio/*} $name] && $reference eq "RAMSP1024X16"} {
            dict incr counts private1024
            set classification included_private_macro
        } else {error "Unexpected macro scope: $name ($reference)"}
        puts $stream "$name\t$reference\t$classification"
    }
    close $stream
    if {[dict get $counts shared4096] != 64 || [dict get $counts private128] != $expected_private128 || [dict get $counts private1024] != 16} {
        error "Unexpected source-preserving memory counts ($stage): $counts"
    }
    return $counts
}
dict set manifest precompile_memories [check_memory_scope precompile]
source $sdc_path
redirect -file [file join $output_dir check_design_pre.rpt] {set design_ok [check_design]}
if {!$design_ok} {error "Precompile check_design failed"}
redirect -file [file join $output_dir units.rpt] {report_units}
redirect -file [file join $output_dir clocks_pre.rpt] {report_clock}
redirect -file [file join $output_dir ports_pre.rpt] {report_port -verbose}
redirect -file [file join $output_dir check_timing_pre.rpt] {check_timing -verbose}
# Fail on actual unconstrained endpoints, rather than suppressing warnings.
# -include restricts this gate to clock/delay completeness; transition/hold
# optimization is evaluated on the mapped design in the subsequent reports.
redirect -variable timing_coverage {check_timing -include {no_clock no_input_delay unconstrained_endpoints} -verbose}
set coverage_stream [open [file join $output_dir timing_coverage_pre.rpt] w]
puts $coverage_stream $timing_coverage
close $coverage_stream
if {[regexp -nocase {Warning:|Error:|\([1-9][0-9]*\)} $timing_coverage]} {
    error "Unconstrained timing reported; inspect timing_coverage_pre.rpt before compile"
}
dict set manifest state compiling
save_manifest
redirect -tee -file [file join $output_dir compile.log] {set compile_ok [compile_ultra -no_autoungroup]}
if {!$compile_ok} {error "compile_ultra failed; inspect compile.log"}
dict set manifest postcompile_memories [check_memory_scope postcompile]
redirect -file [file join $output_dir check_design_post.rpt] {set design_ok [check_design]}
redirect -file [file join $output_dir check_timing_post.rpt] {check_timing -verbose}
redirect -file [file join $output_dir timing_max.rpt] {report_timing -delay_type max -max_paths 50 -significant_digits 6}
redirect -file [file join $output_dir timing_min.rpt] {report_timing -delay_type min -max_paths 50 -significant_digits 6}
redirect -file [file join $output_dir constraints.rpt] {report_constraint -all_violators}
redirect -file [file join $output_dir area.rpt] {report_area -hierarchy}
redirect -file [file join $output_dir references.rpt] {report_reference -hierarchy}
redirect -file [file join $output_dir ports_post.rpt] {report_port -verbose}

# Enumerate mapped LEAF cells once: hierarchical area would double count.
# Library cells are real physical SRAM/standard cells, never RTL black boxes.
set totals [dict create included_fio_logic 0.0 included_private_macro 0.0 included_shared_logic 0.0 included_boundary_logic 0.0 excluded_fixed_shared_macro 0.0]
set stream [open [file join $output_dir leaf_area.tsv] w]
puts $stream "instance\treference\tlibrary_cell\tclass\tarea_library_units\tarea_um2"
set leaf_count 0
foreach_in_collection cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
    incr leaf_count
    set name [get_object_name $cell]
    set reference [get_attribute $cell ref_name]
    set libcell [get_lib_cells -quiet -of_objects $cell]
    if {[sizeof_collection $libcell] != 1} {error "Unmapped/black-box leaf: $name ($reference)"}
    set area [get_attribute $libcell area]
    if {![string is double -strict $area] || $area <= 0} {error "Missing/nonpositive library area: $name"}
    if {[string match {u_shared/*} $name]} {
        if {$reference eq "RAMSP4096X16"} {set category excluded_fixed_shared_macro} else {set category included_shared_logic}
    } elseif {[string match {u_fio/*} $name]} {
        if {[string match RAMSP* $reference]} {set category included_private_macro} else {set category included_fio_logic}
    } else {set category included_boundary_logic}
    set area_um2 [expr {$area * $AREA_UNIT_TO_UM2}]
    dict set totals $category [expr {[dict get $totals $category] + $area_um2}]
    puts $stream "$name\t$reference\t[get_object_name $libcell]\t$category\t$area\t$area_um2"
}
close $stream
if {$leaf_count == 0 || [dict get $totals included_shared_logic] <= 0 || [dict get $totals included_fio_logic] <= 0} {
    error "Missing mapped accelerator or shared-arbitration logic"
}
set total_um2 0.0
dict for {category value} $totals {set total_um2 [expr {$total_um2 + $value}]}
set score_um2 [expr {$total_um2 - [dict get $totals excluded_fixed_shared_macro]}]
dict set manifest area_categories_um2 $totals
dict set manifest total_boundary_area_um2 $total_um2
dict set manifest score_incremental_area_um2 $score_um2
dict set manifest score_incremental_area_mm2 [expr {$score_um2 / 1000000.0}]
dict set manifest mapped_leaf_count $leaf_count
set stream [open [file join $output_dir area_scope.tsv] w]
puts $stream "category\tarea_um2"
dict for {category value} $totals {puts $stream "$category\t$value"}
puts $stream "total_boundary\t$total_um2"
puts $stream "score_incremental\t$score_um2"
close $stream
foreach kind {max min} {
    set paths [get_timing_paths -delay_type $kind -max_paths 1]
    if {[sizeof_collection $paths] != 1} {error "No timed $kind path"}
    dict set manifest worst_${kind}_slack_ns [get_attribute $paths slack]
}
# Freeze exactly the netlist to be used by subsequent STA and Formality.
change_names -rules verilog -hierarchy
write -format ddc -hierarchy -output [file join $output_dir qingyu_score_top.ddc]
write -format verilog -hierarchy -output [file join $output_dir qingyu_score_top_mapped.v]
write_sdc [file join $output_dir qingyu_score_top.sdc]
set_svf -off
foreach path $input_files {
    if {[input_sha256 $path] ne [dict get $input_hashes [file normalize $path]]} {
        error "Input changed during synthesis: $path"
    }
}
foreach filename {qingyu_score_top.ddc qingyu_score_top_mapped.v qingyu_score_top.sdc qingyu_score_top.svf} {
    dict set manifest output_sha256 $filename [input_sha256 [file join $output_dir $filename]]
}
dict set manifest check_design_pass $design_ok
dict set manifest state synthesized_pending_sta_and_lec
save_manifest
puts "QINGYU_SCORE_INCREMENTAL_AREA_MM2: [dict get $manifest score_incremental_area_mm2]"
puts "QINGYU_SCORE_SYNTHESIS_COMPLETE: $output_dir"
puts "Not signoff: inspect timing coverage/DRCs, verify ns/pF/area units, run all-corner STA and this run's Formality."
puts "Full-SoC energy still includes E203, interconnect and all shared SRAM macros."
if {!$design_ok} {error "Mapped check_design failed; artifacts retained for diagnosis"}
