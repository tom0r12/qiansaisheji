# Synopsys Design Compiler formal-flow entry point.
# The checked-in behavioral SRAM is intentionally NOT analyzed here.
# Supply QINGYU_SRAM_RTL: a replacement qingyu_sram16 wrapper that instantiates
# the actual allowed macros, and QINGYU_SRAM_LIBS: their .db timing libraries.
# All environment lists use Tcl-list syntax; keep proprietary inputs local.
set project_root [file normalize [file join [file dirname [info script]] ..]]
foreach required {QINGYU_TARGET_LIBS QINGYU_SRAM_LIBS QINGYU_SRAM_RTL QINGYU_INPUT_DELAY_NS QINGYU_OUTPUT_DELAY_NS QINGYU_CLOCK_UNCERTAINTY_NS QINGYU_INPUT_SLEW_NS QINGYU_OUTPUT_LOAD_PF} {
    if {![info exists env($required)] || $env($required) eq ""} {
        error "Missing required environment setting $required"
    }
}
set run_tag formal
if {[info exists env(QINGYU_RUN_TAG)]} { set run_tag $env(QINGYU_RUN_TAG) }
if {![regexp {^[A-Za-z0-9_-]+$} $run_tag]} { error "Invalid QINGYU_RUN_TAG" }
set output_dir [file join $project_root reports synthesis_dc_$run_tag]
file mkdir $output_dir
define_design_lib WORK -path [file join $output_dir work]

set standard_libs $env(QINGYU_TARGET_LIBS)
set sram_libs $env(QINGYU_SRAM_LIBS)
set sram_rtl $env(QINGYU_SRAM_RTL)
foreach input_file [concat $standard_libs $sram_libs $sram_rtl] {
    if {![file isfile $input_file]} { error "Missing library/wrapper file $input_file" }
}
set target_library $standard_libs
set link_library [concat [list *] $standard_libs $sram_libs]
set search_path [concat [list $project_root] $search_path]

analyze -format sverilog $sram_rtl
analyze -format sverilog [file join $project_root rtl qingyu_accel.sv]
elaborate qingyu_accel
current_design qingyu_accel
link
uniquify
redirect -file [file join $output_dir check_design_pre.rpt] { check_design }

set CLOCK_PERIOD_NS 6.666666667
if {[info exists env(QINGYU_CLOCK_PERIOD_NS)]} { set CLOCK_PERIOD_NS $env(QINGYU_CLOCK_PERIOD_NS) }
set INPUT_DELAY_NS $env(QINGYU_INPUT_DELAY_NS)
set OUTPUT_DELAY_NS $env(QINGYU_OUTPUT_DELAY_NS)
set CLOCK_UNCERTAINTY_NS $env(QINGYU_CLOCK_UNCERTAINTY_NS)
set INPUT_SLEW_NS $env(QINGYU_INPUT_SLEW_NS)
set OUTPUT_LOAD_PF $env(QINGYU_OUTPUT_LOAD_PF)
source [file join $project_root constraints accelerator.sdc]

if {[info exists env(QINGYU_USE_ULTRA)] && $env(QINGYU_USE_ULTRA) eq "1"} {
    compile_ultra
} else {
    compile -map_effort high
}
redirect -file [file join $output_dir check_design_post.rpt] { check_design }
redirect -file [file join $output_dir check_timing.rpt] { check_timing }
redirect -file [file join $output_dir timing_max.rpt] { report_timing -delay_type max -max_paths 20 }
redirect -file [file join $output_dir timing_min.rpt] { report_timing -delay_type min -max_paths 20 }
redirect -file [file join $output_dir constraints.rpt] { report_constraint -all_violators }
redirect -file [file join $output_dir area.rpt] { report_area -hierarchy }
redirect -file [file join $output_dir references.rpt] { report_reference -hierarchy }
redirect -file [file join $output_dir clocks.rpt] { report_clock }
redirect -file [file join $output_dir units.rpt] { report_units }
write -format ddc -hierarchy -output [file join $output_dir qingyu_accel.ddc]
write -format verilog -hierarchy -output [file join $output_dir qingyu_accel_mapped.v]
write_sdc [file join $output_dir qingyu_accel.sdc]

# This entry point alone does not establish full-SoC power, SAIF coverage,
# all-corner timing acceptance or pre/post-synthesis functional equivalence.
puts "Synthesis artifacts written to $output_dir. Review violations and unresolved references before claiming acceptance."
