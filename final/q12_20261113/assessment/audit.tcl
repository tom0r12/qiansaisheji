# Shared inventory gate for DC and PrimeTime. All 116 macros, including TCM.
proc q12_inventory {stage} {
 set counts [dict create RAMSP128X16 0 RAMSP1024X16 0 RAMSP4096X16 0]
 set f [open macros_${stage}.tsv w]
 puts $f "instance\treference\tlibrary_cell"
 foreach_in_collection cell [get_cells -hierarchical] {
  set ref [get_attribute $cell ref_name]
  if {![string match RAM* $ref]} {continue}
  if {![dict exists $counts $ref]} {error "Unexpected memory $ref"}
  set lib [get_lib_cells -quiet -of_objects $cell]
  if {[sizeof_collection $lib]!=1} {error "Unresolved SRAM [get_object_name $cell]"}
  set area [get_attribute $lib area]
  if {![string is double -strict $area] || $area<=0} {error "Unqualified SRAM area $ref"}
  dict incr counts $ref
  puts $f "[get_object_name $cell]\t$ref\t[get_object_name $lib]"
 }
 close $f
 foreach {ref n} {RAMSP128X16 30 RAMSP1024X16 6 RAMSP4096X16 80} {
  if {[dict get $counts $ref]!=$n} {error "Wrong macro inventory $ref=[dict get $counts $ref] expected=$n"}
 }
 foreach root {u_fio u_fio/u_request u_fio/u_engine_fio u_e203_subsys_top/u_e203_subsys_main/u_mem_merge/u_original u_shared/u_cache} {
  if {[sizeof_collection [get_cells -quiet $root]]!=1} {error "Missing preserved hierarchy $root"}
 }
 set f [open leaves_${stage}.tsv w]
 puts $f "instance\treference\tlibrary_cell"
 foreach_in_collection cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
  set ref [get_attribute $cell ref_name]
  if {$stage eq "before"} {continue}
  if {$ref eq "**logic_0**" || $ref eq "**logic_1**"} {continue}
  set lib [get_lib_cells -quiet -of_objects $cell]
  if {[sizeof_collection $lib]!=1 || [regexp {^(GTECH_|SEQGEN|DW_)} [string trim $ref *]]} {
   error "Unmapped/blackbox leaf [get_object_name $cell] $ref"
  }
  puts $f "[get_object_name $cell]\t$ref\t[get_object_name $lib]"
 }
 close $f
 puts "Q12_INVENTORY_COMPLETE $stage 30 6 80"
}
