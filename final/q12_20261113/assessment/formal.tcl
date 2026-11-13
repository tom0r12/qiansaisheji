# Exact staged whole-SoC RTL versus the same run's mapped.v and mapped.svf.
# This does not prove SRAM internal behavior. No manual boxes, cuts, matches,
# constants or dont_verify exceptions are introduced by this script.
set q12_report_errors 0
proc q12_report {filename command} {
    global q12_report_errors
    puts "Q12_FORMAL_REPORT_BEGIN=$filename"
    if {[catch {redirect -tee -file $filename $command} message]} {
        incr q12_report_errors
        puts "Q12_FORMAL_REPORT_ERROR=$filename: $message"
    }
    puts "Q12_FORMAL_REPORT_END=$filename"
}
set rc [catch {
    set synopsys_auto_setup true
    set hdlin_unresolved_modules error
    source [file join $env(Q12_PACKAGE) hardware sources.tcl]
    set search_path [concat $Q12_INCLUDES $search_path]
    foreach library $env(Q12_LIBRARIES) {
        if {![file readable $library]} {error "Missing official mapping library: $library"}
        read_db $library
    }
    foreach path [list $env(Q12_NETLIST) $env(Q12_SVF)] {
        if {![file readable $path] || [file size $path] == 0} {error "Missing mapped artifact: $path"}
    }
    set_svf $env(Q12_SVF)
    # Translate exactly the mapping-stage defines; no separately maintained list.
    set defines [file normalize defines.v]
    set f [open $defines w]
    foreach definition $Q12_DEFINES {
        if {![regexp {^([A-Za-z_][A-Za-z0-9_]*)(=(.*))?$} $definition dummy name unused value]} {
            error "Unsupported mapping define: $definition"
        }
        puts $f "`define $name $value"
    }
    close $f
    read_sverilog -r -libname WORK [concat [list $defines] $Q12_SOURCES]
    set_top r:/WORK/qingyu_e203_soc_top
    read_verilog -i -libname WORK $env(Q12_NETLIST)
    set_top i:/WORK/qingyu_e203_soc_top
    q12_report blackboxes_reference.rpt {report_black_boxes -r -all}
    q12_report blackboxes_implementation.rpt {report_black_boxes -i -all}
    match
    q12_report matched.rpt {report_matched_points}
    q12_report unmatched.rpt {report_unmatched_points}
    q12_report unmatched_black_boxes.rpt {report_unmatched_points -point_type bbox}
    set verified 0
    set verify_error [catch {set verified [verify]} verify_message]
    if {$verify_error} {puts "Q12_FORMAL_VERIFY_EXCEPTION=$verify_message"}
    # Retain every diagnostic even when verify fails or a report command errors.
    q12_report status.rpt {report_status}
    q12_report failing.rpt {report_failing_points}
    q12_report aborted.rpt {report_aborted_points}
    q12_report unverified.rpt {report_unverified_points}
    q12_report unmatched_after_verify.rpt {report_unmatched_points}
    q12_report unmatched_black_boxes_after_verify.rpt {report_unmatched_points -point_type bbox}
    q12_report guidance.rpt {report_guidance -summary}
    q12_report dont_verify.rpt {report_dont_verify_points}
    q12_report constants.rpt {report_constants}
    q12_report hdlin_mismatches.rpt {report_hdlin_mismatches}
    if {[catch {save_session verification_session} message]} {
        puts "Q12_FORMAL_SESSION_SAVE_ERROR=$message"
    }
    puts "Q12_FORMAL_VERIFY_RETURN=$verified"
    puts "Q12_FORMAL_REPORT_ERRORS=$q12_report_errors"
    puts Q12_FINAL_FORMAL_REPORTS_COMPLETE
    if {$verify_error || !$verified || $q12_report_errors != 0} {error "Formal proof or diagnostic reports incomplete"}
    # Tool completion is distinct from the independent Python scope/report audit.
    puts Q12_FINAL_FORMAL_COMPLETE
} message]
if {$rc} {puts "Q12_FINAL_FORMAL_FAILED: $message";puts $errorInfo;exit 2}
exit 0
