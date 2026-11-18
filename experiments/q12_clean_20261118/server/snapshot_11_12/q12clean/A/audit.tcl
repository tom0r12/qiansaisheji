# Shared inventory gate for DC and PrimeTime. All 116 macros, including TCM.
proc q12_inventory {stage} {
 set counts [dict create RAMSP128X16 0 RAMSP1024X16 0 RAMSP4096X16 0]
 set f [open macros_${stage}.tsv w]
 puts $f "instance\treference\tlibrary_cell"
 foreach_in_collection cell [get_cells -hierarchical] {
  set ref [get_attribute $cell ref_name]
  if {![string match RAM* $ref]} {continue}
  if {![dict exists $counts $ref]} {error "Unexpected memory $ref"}
  set libs [get_lib_cells -quiet -of_objects $cell]
  if {[sizeof_collection $libs]<1} {error "Unresolved SRAM [get_object_name $cell]"}
  set lib [index_collection $libs 0]
  set area [get_attribute $lib area]
  if {![string is double -strict $area] || $area<=0} {error "Unqualified SRAM area $ref"}
  dict incr counts $ref
  puts $f "[get_object_name $cell]\t$ref\t[get_object_name $lib]"
 }
 close $f
 set q12_n128 [expr {[info exists ::env(Q12_EXPECT_128)] ? $::env(Q12_EXPECT_128) : 30}]
 set q12_n4096 [expr {[info exists ::env(Q12_EXPECT_4096)] ? $::env(Q12_EXPECT_4096) : 80}]
 foreach {ref n} [list RAMSP128X16 $q12_n128 RAMSP1024X16 6 RAMSP4096X16 $q12_n4096] {
  if {[dict get $counts $ref]!=$n} {error "Wrong macro inventory $ref=[dict get $counts $ref] expected=$n"}
 }
 set q12_top [get_object_name [current_design]]
 if {$q12_top eq "qingyu_e203_soc_top"} {
  foreach root {u_fio u_gpio_dma u_dma_channels u_e203_subsys_top/u_e203_subsys_main/u_ppi_merge u_e203_subsys_top/u_e203_subsys_main/u_mem_merge u_shared/u_ctrl} {
   if {[sizeof_collection [get_cells -quiet $root]]!=1} {error "Missing preserved hierarchy $root"}
  }
 }
 if {$stage ne "before"} {
  set f [open leaves_${stage}.tsv w]
  puts $f "instance\treference\tlibrary_cell"
  foreach_in_collection cell [get_cells -hierarchical -filter {is_hierarchical == false}] {
   set ref [get_attribute $cell ref_name]
   if {$ref eq "**logic_0**" || $ref eq "**logic_1**"} {continue}
   set libs [get_lib_cells -quiet -of_objects $cell]
   if {[sizeof_collection $libs]<1 || [regexp {^(GTECH_|SEQGEN|DW_)} [string trim $ref *]]} {
    error "Unmapped/blackbox leaf [get_object_name $cell] $ref"
   }
   set lib [index_collection $libs 0]
   puts $f "[get_object_name $cell]\t$ref\t[get_object_name $lib]"
  }
  close $f
 }
 puts "Q12_INVENTORY_COMPLETE $stage $q12_n128 6 $q12_n4096"
}
