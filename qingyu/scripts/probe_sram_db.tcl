# Source in dc_shell. Read-only inventory; does not compile or alter the design.
namespace eval ::qingyu_db_probe {
    variable root /storage1/admin_public_dir/SRAM_Lib_2025
    if {[info exists ::env(QINGYU_SERVER_SRAM_ROOT)]} {
        set root $::env(QINGYU_SERVER_SRAM_ROOT)
    }
    proc walk {directory depth} {
        if {![file isdirectory $directory]} { return {} }
        set result {}
        foreach path [lsort [glob -nocomplain -directory $directory *]] {
            if {[file isfile $path]} {
                if {[regexp -nocase {\.db(\.gz)?$} $path]} { lappend result $path }
            } elseif {$depth > 0 && [file isdirectory $path] && [file type $path] ne "link"} {
                set result [concat $result [walk $path [expr {$depth-1}]]]
            }
        }
        return $result
    }
    puts "QINGYU DB INVENTORY (all corner names, depth <= 4)"
    foreach macro {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
        set directory [file join $root $macro]
        puts "=== $macro ==="
        set paths [walk $directory 4]
        puts "DB_COUNT: [llength $paths]"
        foreach path $paths { puts "DB: $path" }
        puts "DB_DIR_ENTRIES: [glob -nocomplain -directory [file join $directory db] *]"
    }
    puts "=== Library Compiler executable candidates (not started) ==="
    set candidates {}
    if {[info exists ::env(PATH)]} {
        foreach directory [split $::env(PATH) :] {
            if {$directory ne ""} {
                set path [file join $directory lc_shell]
                if {[file isfile $path] && [file executable $path]} { lappend candidates $path }
            }
        }
    }
    foreach path [glob -nocomplain /eda/synopsys/lc/*/bin/lc_shell /eda/synopsys/lc/bin/lc_shell /eda/synopsys/*/*/bin/lc_shell] {
        if {[file isfile $path]} { lappend candidates $path }
    }
    foreach path [lsort -unique $candidates] { puts "LC_SHELL: $path" }
    if {[llength $candidates] == 0} { puts "LC_SHELL: not found in checked locations" }
    puts "PROBE COMPLETE (no library conversion or synthesis performed)"
}
