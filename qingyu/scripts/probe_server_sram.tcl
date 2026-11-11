# Run inside the contest DC session:
# source ~/Desktop/probe_server_sram.tcl
# Read metadata in place. No library downloads, synthesis, or DC design changes.
namespace eval ::qingyu_sram_probe {
    variable root /storage1/admin_public_dir/SRAM_Lib_2025
    if {[info exists ::env(QINGYU_SERVER_SRAM_ROOT)]} {
        set root $::env(QINGYU_SERVER_SRAM_ROOT)
    }
    variable report [file join [file dirname [file normalize [info script]]] qingyu_sram_probe.rpt]
    variable output [open $report w]

    proc emit {line} {
        variable output
        puts $line
        puts $output $line
    }
    proc read_text {path} {
        set stream [open $path r]
        set code [catch {read $stream} data]
        close $stream
        if {$code} { error $data }
        return $data
    }
    proc walk {directory depth} {
        if {![file isdirectory $directory]} { return {} }
        set found {}
        foreach path [lsort [glob -nocomplain -directory $directory *]] {
            if {[file isfile $path]} {
                lappend found $path
            } elseif {$depth > 0 && [file isdirectory $path] && [file type $path] ne "link"} {
                set found [concat $found [walk $path [expr {$depth-1}]]]
            }
        }
        return $found
    }
    proc typical_files {directory pattern} {
        set found {}
        foreach path [walk $directory 2] {
            set name [file tail $path]
            if {[string match -nocase $pattern $name]
                && [regexp -nocase {_tt_1p10v_1p10v_25c} $name]} {
                lappend found $path
            }
        }
        return $found
    }

    set code [catch {
        emit "QINGYU SRAM METADATA PROBE"
        emit "Root: $root"
        emit "This report does not establish macro integration or timing/power acceptance."
        foreach macro {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
            emit "\n=== $macro ==="
            set directory [file join $root $macro]
            if {![file isdirectory $directory]} {
                emit "MISSING DIRECTORY: $directory"
                continue
            }
            set model [file join $directory verilog ${macro}.v]
            emit "MODEL: $model"
            if {[file isfile $model]} {
                set text [read_text $model]
                set start [string first "module $macro " $text]
                if {$start < 0} { set start [string first "module $macro(" $text] }
                if {$start >= 0} {
                    # Restrict metadata to this macro's header/declarations.
                    set header [string range $text $start [expr {$start+5500}]]
                    foreach line [split $header \n] {
                        if {[regexp {^[ \t]*(input|output|inout)[ \t]+[^;]+;} $line]} {
                            emit "PORT: [string trim $line]"
                        }
                    }
                } else {
                    emit "MODULE NAME NOT FOUND; inspect the model manually."
                }
            } else {
                emit "MISSING MODEL"
            }
            set dbs [typical_files [file join $directory db] *.db]
            emit "TT_DB_COUNT: [llength $dbs]"
            foreach path $dbs { emit "TT_DB: $path" }
            if {![llength $dbs]} {
                foreach path [walk [file join $directory db] 2] {
                    emit "DB_CANDIDATE: $path"
                }
            }
            set libs [typical_files [file join $directory lib] *.lib]
            emit "TT_LIB_COUNT: [llength $libs]"
            foreach path $libs {
                emit "TT_LIB: $path"
                set text [read_text $path]
                foreach line [split $text \n] {
                    if {[regexp {^[ \t]*(library[ \t]*\(|cell[ \t]*\(|area[ \t]*:|time_unit[ \t]*:|capacitive_load_unit[ \t]*\(|nom_voltage[ \t]*:|nom_temperature[ \t]*:|nom_process[ \t]*:)} $line]} {
                        emit "LIB: [string trim $line]"
                    }
                }
            }
            foreach path [typical_files [file join $directory datasheet] *.ps] {
                emit "TT_DATASHEET: $path"
                set text [read_text $path]
                foreach line [split $text \n] {
                    if {[regexp {EMA[W]?[ \t]*[=:]} $line]} {
                        emit "DATASHEET_SETTING: [string trim $line]"
                    }
                }
            }
        }
        emit "\nProbe completed. Report: $report"
    } message]
    close $output
    if {$code} { error $message }
}
