source [file join [file dirname [info script]] common.tcl]
if {![info exists env(QINGYU_MAPPED_RUN)]} {error "Missing frozen mapped run"}
set mapped [file normalize $env(QINGYU_MAPPED_RUN)]
source [file join $mapped assessment_provenance.tcl]
if {[dict get $assessment_provenance bundle_sha256] ne $env(QINGYU_BUNDLE_SHA256)} {error "Mapped run belongs to another bundle"}
foreach filename {qingyu_e203_soc_top_mapped.v qingyu_e203_soc_top.svf} {
 if {[file_sha [file join $mapped $filename]] ne [dict get $assessment_provenance outputs_sha256 $filename]} {error "Mapped input changed: $filename"}
}
set synopsys_auto_setup true
set hdlin_unresolved_modules error
set search_path [concat $includes $search_path]
foreach library [concat $STD_CELL_LIBS $SRAM_LIBS] {read_db $library}
check_loaded_standard_identity
set_svf [file join $mapped qingyu_e203_soc_top.svf]
# Configuration is the same Verilog define file used by the validated VCS
# fixture; no simulation RAM model or alternate numeric RTL is read here.
read_sverilog -r -libname WORK [concat [list [file join $bundle common synth_defines.v]] $sources]
set_top r:/WORK/qingyu_e203_soc_top
read_verilog -i -libname WORK [file join $mapped qingyu_e203_soc_top_mapped.v]
set_top i:/WORK/qingyu_e203_soc_top
redirect -file [file join $work black_boxes_reference.rpt] {report_black_boxes -r -all}
redirect -file [file join $work black_boxes_implementation.rpt] {report_black_boxes -i -all}
match
redirect -file [file join $work matched.rpt] {report_matched_points}
redirect -file [file join $work unmatched.rpt] {report_unmatched_points}
set verified [verify]
redirect -file [file join $work status.rpt] {report_status}
redirect -file [file join $work failing.rpt] {report_failing_points}
redirect -file [file join $work aborted.rpt] {report_aborted_points}
redirect -file [file join $work unverified.rpt] {report_unverified_points}
redirect -file [file join $work guidance.rpt] {report_guidance -summary}
save_session [file join $work verification_session]
dict set provenance verify_return $verified
dict set provenance status formal_reports_pending_blackbox_and_unmatched_review
verify_frozen_inputs;save_provenance
if {!$verified} {error "Full-SoC equivalence did not pass; retained complete diagnostics"}
puts "QINGYU_FORMAL_REPORTS $work"
puts "No arbitrary cut points, dont-verify points, forced matches or historical SVF were applied."
