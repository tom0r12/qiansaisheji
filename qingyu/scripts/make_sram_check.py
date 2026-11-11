"""Make a single-file server DC check, embedding the reviewed macro wrapper."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT.parent / 'output/eda/check_sram_macros.tcl'
wrapper = (ROOT / 'rtl/asic/qingyu_sram16.sv').read_text(encoding='utf-8')
script = r'''# Run in a NEW dc_shell session; no compile or timing acceptance.
if {[sizeof_collection [get_designs -quiet *]] > 0} {
    error "Start a new dc_shell session for this check; existing designs were not modified."
}
set desktop [file dirname [file normalize [info script]]]
set core [file join $desktop qingyu_dc_start rtl qingyu_accel.sv]
if {![file readable $core]} { error "Missing core RTL: $core" }
source [file join $desktop qingyu_stdcell_db load_stdcell.tcl]
source [file join $desktop qingyu_sram_db sram_libs.tcl]
foreach lib $env(QINGYU_SRAM_LIBS) { read_db $lib }
set link_library [concat [list *] $target_library $env(QINGYU_SRAM_LIBS)]
set out [file join $desktop qingyu_sram_check_[clock seconds]_[pid]]
file mkdir $out
set macro_wrapper [file join $out qingyu_sram16.sv]
set stream [open $macro_wrapper w]
puts $stream {
__WRAPPER__
}
close $stream
file mkdir [file join $out work]
define_design_lib WORK -path [file join $out work]
analyze -format sverilog $macro_wrapper
analyze -format sverilog $core
elaborate qingyu_accel
current_design qingyu_accel
if {![link]} { error "Link failed; inspect unresolved references" }
uniquify
redirect -file [file join $out check_design.rpt] { check_design }
check_design
foreach {macro expected} {RAMSP128X16 5 RAMSP1024X16 2 RAMSP4096X16 2} {
    set count [sizeof_collection [get_cells -hierarchical -filter "ref_name == $macro"]]
    puts "QINGYU_MACRO_COUNT: $macro $count (expected $expected)"
    if {$count != $expected} { error "Unexpected SRAM instance count for $macro" }
}
redirect -file [file join $out references.rpt] { report_reference -hierarchy }
write -format verilog -hierarchy -output [file join $out qingyu_accel_linked.v]
puts "QINGYU_SRAM_LINK_CHECK_COMPLETE: 9 macro instances"
puts "REPORT_DIRECTORY: $out"
puts "Review check_design warnings. No compile, macro simulation, timing or power acceptance claimed."
'''
DEST.parent.mkdir(parents=True, exist_ok=True)
DEST.write_text(script.replace('__WRAPPER__', wrapper), encoding='utf-8')
print(DEST)
