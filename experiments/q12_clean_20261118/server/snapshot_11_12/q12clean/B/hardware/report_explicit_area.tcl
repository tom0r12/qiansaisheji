# Count every new datapath/transport/interface leaf exactly once.
proc q12_report_explicit_area {} {
 set fio 0.0;set transport 0.0;set shared_logic 0.0;set shared_macro 0.0;set whole 0.0
 set f [open q12_explicit_area_leaves.tsv w];puts $f "instance\treference\tarea\tgroup"
 foreach_in_collection c [get_cells -hierarchical -filter {is_hierarchical == false}] {
  set n [get_object_name $c];set ref [get_attribute $c ref_name];set a 0.0
  if {$ref ne "**logic_0**" && $ref ne "**logic_1**"} {
   set libs [get_lib_cells -quiet -of_objects $c]
   if {[sizeof_collection $libs]<1} {error "Unresolved leaf $n $ref"}
   set lib [index_collection $libs 0]
   set a [get_attribute $lib area]
   if {![string is double -strict $a] || $a<0} {error "Invalid area $n"}
  }
  set group platform;set whole [expr {$whole+$a}]
  if {[string match u_fio/* $n]} {
   set group fio;set fio [expr {$fio+$a}]
  } elseif {[string match u_shared/* $n]} {
   if {[string match RAMSP* $ref]} {set group fixed_shared_macro;set shared_macro [expr {$shared_macro+$a}]
   } else {set group shared_interface;set shared_logic [expr {$shared_logic+$a}]}
  } elseif {[string match u_gpio_dma/* $n] || [string match u_dma_channels/* $n] ||
            [string match u_e203_subsys_top/u_e203_subsys_main/u_mem_merge/* $n] ||
            [string match u_e203_subsys_top/u_e203_subsys_main/u_ppi_merge/* $n] ||
            [string first / $n]<0} {
   set group new_transport;set transport [expr {$transport+$a}]
  }
  puts $f "$n\t$ref\t$a\t$group"
 }
 close $f
 set inc [expr {$fio+$transport+$shared_logic}]
 set f [open explicit_area_summary.txt w]
 foreach {k v} [list FULL_SOC_LIBRARY_AREA $whole FIO_LIBRARY_AREA $fio NEW_TRANSPORT_LIBRARY_AREA $transport SHARED_NONMACRO_LIBRARY_AREA $shared_logic FIXED_SHARED_MACRO_LIBRARY_AREA $shared_macro INCREMENTAL_LIBRARY_AREA $inc] {puts $f "$k=$v";puts "$k=$v"}
 close $f
 puts "Q12_EXPLICIT_AREA_READY: new GPIO DMA, FIFO, both arbiters, top configuration logic and custom shared control counted; confirm library units"
}
