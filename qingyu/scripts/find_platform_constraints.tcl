# Read-only bounded search of known shared directories, not other teams' homes.
namespace eval ::qingyu_platform_search {
    variable visited 0
    variable candidates {}
    variable stopped 0
    proc walk {directory depth} {
        variable visited
        variable candidates
        variable stopped
        if {![file isdirectory $directory] || $depth < 0} {return}
        if {[catch {glob -nocomplain -directory $directory *} paths]} {
            puts "UNREADABLE_DIRECTORY: $directory"
            return
        }
        foreach path [lsort $paths] {
            incr visited
            if {$visited > 30000} {set stopped 1; return}
            if {[catch {file type $path} kind] || $kind eq "link"} {continue}
            if {[file isdirectory $path]} {
                if {$depth > 0} {walk $path [expr {$depth-1}]}
                if {$stopped} {return}
            } elseif {[file isfile $path]} {
                set name [string tolower [file tail $path]]
                if {[regexp {\.(sdc|tcl|pdf|docx?|xlsx?|zip|tgz|tar|gz|7z)$} $name]
                    || [string match *readme* $name]} {
                    lappend candidates $path
                }
            }
        }
    }
    set root /storage1/admin_public_dir
    foreach directory {SOC_RTL_2025 Document 2025_Lab SMIC40_2025} {
        set visited 0
        set candidates {}
        set stopped 0
        walk [file join $root $directory] 6
        puts "=== $directory: scanned $visited entries, candidates [llength $candidates], limit_hit=$stopped ==="
        set shown 0
        foreach path $candidates {
            set ext [string tolower [file extension $path]]
            set relevant 0
            set excerpts {}
            if {$ext eq ".sdc"} {set relevant 1}
            if {$ext eq ".tcl" || $ext eq ".sdc"} {
                if {[file size $path] <= 524288 && [file readable $path]} {
                    set stream [open $path r]
                    set data [read $stream]
                    close $stream
                    set line_number 0
                    foreach line [split $data \n] {
                        incr line_number
                        if {[regexp {create_clock|set_input_delay|set_output_delay|set_clock_uncertainty|set_load|set_driving_cell|set_operating_conditions|target_library|link_library} $line]} {
                            set relevant 1
                            if {[llength $excerpts] < 6} {lappend excerpts "$line_number: [string range [string trim $line] 0 240]"}
                        }
                    }
                }
            } elseif {$directory ne "SMIC40_2025" || [regexp -nocase {readme|guide|manual} [file tail $path]]} {
                set relevant 1
            }
            if {$relevant} {
                incr shown
                if {$shown <= 60} {
                    puts "CANDIDATE: $path"
                    foreach excerpt $excerpts {puts "  TEXT: $excerpt"}
                }
            }
        }
        puts "RELEVANT_COUNT: $shown (console capped at 60 per directory)"
    }
    puts "QINGYU_PLATFORM_SEARCH_COMPLETE"
    puts "No scripts executed or archives extracted. Candidate values are not confirmed 2026 contest constraints."
}
