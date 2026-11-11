# Restore the fixed successful session; do not rerun match/verify or change RTL.
set audit_base [file normalize ~/Desktop/qingyu_formality_margin_20261101_222303_222700]
set session [file join $audit_base verification_session.fss]
if {![file readable $session]} { error "Missing saved session: $session" }
cd $audit_base
restore_session $session
set audit_dir [file join $audit_base audit_[clock seconds]]
file mkdir $audit_dir
set audit_errors 0
foreach {name command} {
    dont_verify.rpt {report_dont_verify_points}
    constants.rpt {report_constants}
    hdlin_mismatches.rpt {report_hdlin_mismatches}
    guidance.rpt {report_guidance -summary}
} {
    puts "QINGYU_AUDIT_BEGIN: $name"
    if {[catch {redirect -file [file join $audit_dir $name] $command} message]} {
        incr audit_errors
        puts "QINGYU_AUDIT_ERROR: $name: $message"
    } else {
        # Limit console output; keep full reports on the server for follow-up.
        set stream [open [file join $audit_dir $name] r]
        set lines [split [read $stream] \n]
        close $stream
        if {$name eq "constants.rpt"} {
            puts "Saved constants report ([llength $lines] lines); review separately."
        } else {
            foreach line [lrange $lines 0 119] { puts $line }
            if {[llength $lines] > 120} { puts "TRUNCATED ON CONSOLE: full report has [llength $lines] lines" }
        }
    }
    puts "QINGYU_AUDIT_END: $name"
}
puts "QINGYU_AUDIT_DIRECTORY: $audit_dir"
puts "QINGYU_AUDIT_REPORT_ERRORS: $audit_errors"
puts "Report extraction only; interpretation audit remains pending."
exit $audit_errors
