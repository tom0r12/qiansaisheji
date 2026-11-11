# Run only through run_formality_margin.sh in its frozen working directory.
# Shared DB libraries are read by Formality for both reference and implementation.
set synopsys_auto_setup true
set hdlin_unresolved_modules error
set fm_report_errors 0
proc fm_report {filename command} {
    global fm_report_errors
    puts "QINGYU_REPORT_BEGIN: $filename"
    if {[catch {redirect -tee -file [file join reports $filename] $command} message]} {
        incr fm_report_errors
        puts "QINGYU_REPORT_ERROR: $filename: $message"
    }
    puts "QINGYU_REPORT_END: $filename"
}
file mkdir reports
set_svf {inputs/qingyu_accel.svf inputs/hold_fix_1.svf inputs/hold_fix_2.svf}
set dbroot [file normalize ~/Desktop]
set standard [file join $dbroot qingyu_stdcell_db db sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_m40c.db]
set libraries [list $standard]
foreach macro {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
    lappend libraries [file join $dbroot qingyu_sram_corners ${macro}_ss_0p99v_0p99v_m40c.db]
}
foreach library $libraries {
    if {![file readable $library]} { error "Missing library: $library" }
    read_db $library
}
# Do not load the behavioral SRAM or the non-synthesizable vendor simulation model.
read_sverilog -r -libname WORK [list inputs/qingyu_sram16.sv inputs/qingyu_accel.sv]
set_top r:/WORK/qingyu_accel
read_verilog -i -libname WORK inputs/qingyu_accel_mapped.v
set_top i:/WORK/qingyu_accel
fm_report black_boxes_reference.rpt {report_black_boxes -r -all}
fm_report black_boxes_implementation.rpt {report_black_boxes -i -all}
# No set_dont_verify_points, manual cut points or forced matches are applied.
match
fm_report matched.rpt {report_matched_points}
fm_report unmatched.rpt {report_unmatched_points}
fm_report unmatched_black_boxes.rpt {report_unmatched_points -point_type bbox}
set fm_verified [verify]
fm_report status.rpt {report_status}
fm_report failing.rpt {report_failing_points}
fm_report aborted.rpt {report_aborted_points}
fm_report unverified.rpt {report_unverified_points}
fm_report unmatched_after_verify.rpt {report_unmatched_points}
fm_report guidance.rpt {report_guidance -summary}
fm_report dont_verify.rpt {report_dont_verify_points}
fm_report constants.rpt {report_constants}
fm_report hdlin_mismatches.rpt {report_hdlin_mismatches}
if {[catch {save_session verification_session} message]} {
    puts "QINGYU_SESSION_SAVE_ERROR: $message"
}
puts "QINGYU_VERIFY_RETURN: $fm_verified"
puts "QINGYU_REPORT_ERRORS: $fm_report_errors"
puts "QINGYU_FORMALITY_REPORTS_READY: [pwd]/reports"
puts "MANUAL AUDIT REQUIRED: both sides must have only the intended matching SRAM boundaries, with no unexpected unresolved/empty logic."
puts "Review all unmatched, failing, aborted, unverified points and SVF guidance. Tool success alone is not project acceptance."
if {!$fm_verified || $fm_report_errors != 0} { exit 2 }
exit 0
