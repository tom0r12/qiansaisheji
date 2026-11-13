# Run after mapping and successful link, with hierarchy retained.
# No synthesis is invoked. Count actual leaf cells once; include real NP3 hardware.
proc q12_report_explicit_area {} {
 set merge_root u_e203_subsys_top/u_e203_subsys_main/u_mem_merge
 foreach path [list u_fio u_fio/u_request u_fio/u_engine_fio $merge_root $merge_root/u_original u_shared u_shared/u_cache] {
  if {[sizeof_collection [get_cells -quiet $path]]!=1} {error "Missing preserved hardware hierarchy $path"}
 }
 foreach pattern {*merge_fixture* *master_bfm* *chunk_loader*} {
  if {[sizeof_collection [get_cells -quiet -hierarchical $pattern]]} {error "Testbench source in hardware: $pattern"}
 }
 set counts [dict create RAMSP128X16 0 RAMSP1024X16 0 RAMSP4096X16 0]
 set fio_area 0.0; set arb_area 0.0; set whole_area 0.0; set mailbox_area 0.0
 set shared_logic_area 0.0; set shared_macro_area 0.0; set cache_area 0.0
 set f [open q12_explicit_area_leaves.tsv w]
 puts $f "instance\treference\tarea\tgroup"
 foreach_in_collection cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
  set name [get_object_name $cell]; set ref [get_attribute $cell ref_name]
  if {$ref eq "**logic_0**" || $ref eq "**logic_1**"} {
   puts $f "$name\t$ref\t0.0\tplatform"
   continue
  }
  set lib [get_lib_cells -quiet -of_objects $cell]
  if {[sizeof_collection $lib]!=1} {error "Unmapped or unresolved leaf: $name $ref"}
  set area [get_attribute $lib area]
  if {![string is double -strict $area] || $area<0} {error "Invalid library area for $name"}
  if {[string match RAM* $ref]} {
   if {![dict exists $counts $ref] || $area<=0} {error "Unexpected/unqualified memory $name $ref"}
   dict incr counts $ref
  }
  set whole_area [expr {$whole_area+$area}]; set group platform
  if {[string match u_fio/* $name]} {set fio_area [expr {$fio_area+$area}]; set group fio}
  if {[string match $merge_root/* $name]} {set arb_area [expr {$arb_area+$area}]; set group arbiter}
  if {[string match u_fio/u_request/* $name]} {set mailbox_area [expr {$mailbox_area+$area}]}
  if {[string match u_shared/* $name]} {
   if {[string match RAM* $ref]} {set shared_macro_area [expr {$shared_macro_area+$area}]; set group fixed_shared_macro
   } else {set shared_logic_area [expr {$shared_logic_area+$area}]; set group shared_interface_logic}
  }
  if {[string match u_shared/u_cache/* $name]} {set cache_area [expr {$cache_area+$area}]}
  puts $f "$name\t$ref\t$area\t$group"
 }
 close $f
 foreach {ref expected} {RAMSP128X16 30 RAMSP1024X16 6 RAMSP4096X16 80} {
  if {[dict get $counts $ref]!=$expected} {error "Wrong macro count $ref=[dict get $counts $ref], expected=$expected"}
 }
 # Shared read-ahead cache/controller is custom project logic, not an official
 # untouched controller. Conservatively count every non-macro shared-side cell.
 set fio_arb [expr {$fio_area+$arb_area}]
 set incremental [expr {$fio_arb+$shared_logic_area}]
 set f [open explicit_area_summary.txt w]
 foreach {key value} [list FULL_SOC_LIBRARY_AREA $whole_area FIO_LIBRARY_AREA $fio_area NP3_ARBITER_LIBRARY_AREA $arb_area MAILBOX_SUBSET_LIBRARY_AREA $mailbox_area FIO_PLUS_NP3_LIBRARY_AREA $fio_arb SHARED_NONMACRO_LIBRARY_AREA $shared_logic_area SHARED_CACHE_SUBSET_LIBRARY_AREA $cache_area FIXED_SHARED_MACRO_LIBRARY_AREA $shared_macro_area INCREMENTAL_LIBRARY_AREA $incremental] {
  puts $f "$key=$value"; puts "$key=$value"
 }
 close $f
 puts "Q12_EXPLICIT_AREA_READY: library units; verify unit scale and scope before reporting mm2"
}
