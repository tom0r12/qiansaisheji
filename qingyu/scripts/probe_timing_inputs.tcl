# Read-only timing-input inventory. Source in dc_shell; no design changes.
namespace eval ::qingyu_timing_probe {
    set shared /storage1/admin_public_dir
    set root [file join $shared SRAM_Lib_2025]
    set common {}
    set first 1
    foreach macro {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
        set corners {}
        foreach path [lsort [glob -nocomplain -directory [file join $root $macro lib] ${macro}_*.lib]] {
            set tail [file rootname [file tail $path]]
            lappend corners [string range $tail [expr {[string length $macro]+1}] end]
        }
        puts "SRAM_LIBRARY_COUNT: $macro [llength $corners]"
        if {$first} {set common $corners; set first 0} else {
            set next {}
            foreach corner $common {if {[lsearch -exact $corners $corner] >= 0} {lappend next $corner}}
            set common $next
        }
    }
    puts "=== CORNERS PRESENT FOR ALL THREE SRAM TYPES ==="
    foreach corner $common {puts "SRAM_COMMON_CORNER: $corner"}
    puts "=== UPLOADED STANDARD CELL DATABASES ==="
    foreach path [lsort [glob -nocomplain -directory [file normalize ~/Desktop/qingyu_stdcell_db/db] *.db]] {
        puts "STDCELL_DB: $path"
    }
    puts "=== SHARED ROOT DIRECTORY NAMES ==="
    foreach path [lsort [glob -nocomplain -directory $shared *]] {
        if {[file isdirectory $path]} {puts "SHARED_DIRECTORY: [file tail $path]"}
    }
    puts "=== SHALLOW SHARED CONSTRAINT / SCRIPT CANDIDATES ==="
    foreach pattern {*.sdc *.tcl */*.sdc */*.tcl} {
        set found [lsort [glob -nocomplain -directory $shared $pattern]]
        foreach path [lrange $found 0 39] {if {[file isfile $path]} {puts "CANDIDATE: $path"}}
        if {[llength $found] > 40} {puts "MORE_CANDIDATES: $pattern [llength $found]"}
    }
    puts "QINGYU_TIMING_INPUT_PROBE_COMPLETE"
    puts "Inventory only. Available corners are not necessarily contest-required corners."
}
