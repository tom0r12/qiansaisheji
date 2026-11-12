# Shared, fail-closed setup for the full official-bus digital SoC.
foreach key {QINGYU_BUNDLE QINGYU_WORK QINGYU_PLATFORM_CONFIG QINGYU_BUNDLE_SHA256} {
 if {![info exists env($key)]} {error "Missing $key; use run_bus_server.py"}
}
set bundle [file normalize $env(QINGYU_BUNDLE)]
set work [file normalize $env(QINGYU_WORK)]
set config [file normalize $env(QINGYU_PLATFORM_CONFIG)]
source $config
foreach key {STD_CELL_FAMILY STD_CELL_LIBS SRAM_LIBS PLATFORM_SDC SYSTEM_CLOCK_NAME AON_CLOCK_NAME OPERATING_CONDITION OPERATING_LIBRARY LIBRARY_PROVENANCE LIBRARY_IDENTITY_FILE TIMING_PROVENANCE AREA_UNIT_PROVENANCE AREA_UNIT_TO_UM2 SRAM_AREA_UM2 SRAM_AREA_PROVENANCE} {
 if {![info exists $key] || [set $key] eq ""} {error "Configuration must explicitly define $key"}
}
if {$STD_CELL_FAMILY ne "SCC40NLL_VHSC40_RVT_V0p1"} {error "Only official SCC40NLL_VHSC40_RVT_V0p1 is accepted"}
if {![string is double -strict $AREA_UNIT_TO_UM2] || $AREA_UNIT_TO_UM2<=0} {error "Verify standard-cell area units against official physical views"}
foreach macro {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
 if {![dict exists $SRAM_AREA_UM2 $macro] || ![string is double -strict [dict get $SRAM_AREA_UM2 $macro]] || [dict get $SRAM_AREA_UM2 $macro]<=0} {error "Missing official area for $macro"}
}
foreach p $STD_CELL_LIBS {
 if {[regexp -nocase {sc9mc|A9TR40} $p]} {error "Historical non-official library rejected: $p"}
}
proc file_sha {path} {
 if {![file isfile $path] || ![file readable $path]} {error "Missing input: $path"}
 set answer [exec sha256sum -- $path]
 if {![regexp {^([a-fA-F0-9]{64})\s} $answer -> hash]} {error "Cannot hash $path"}
 return [string tolower $hash]
}
source $LIBRARY_IDENTITY_FILE
if {![info exists official_library_identity]} {error "Official library identity manifest is missing"}
foreach key {family archive_path archive_sha256 review files} {
 if {![dict exists $official_library_identity $key] || [dict get $official_library_identity $key] eq ""} {error "Incomplete reviewed library identity: $key"}
}
if {[dict get $official_library_identity family] ne $STD_CELL_FAMILY || [dict get $official_library_identity review] ne "accepted"} {error "Official archive-to-DB identity has not been reviewed"}
set official_archive [file normalize [dict get $official_library_identity archive_path]]
if {[file_sha $official_archive] ne [dict get $official_library_identity archive_sha256]} {error "Official source archive hash differs"}
foreach path $STD_CELL_LIBS {
 set p [file normalize $path]
 if {![dict exists $official_library_identity files $p]} {error "Unapproved standard-cell database $p"}
 set entry [dict get $official_library_identity files $p]
 foreach key {sha256 library_name cell_count archive_member conversion_provenance} {
  if {![dict exists $entry $key] || [dict get $entry $key] eq ""} {error "Missing DB identity $key for $p"}
 }
 if {[file_sha $p] ne [dict get $entry sha256]} {error "Standard-cell DB hash differs from approved manifest"}
 if {![string match "*SCC40NLL_VHSC40_RVT_V0p1/*" [dict get $entry archive_member]]} {error "DB source is outside the required official family"}
}
proc check_loaded_standard_identity {} {
 global STD_CELL_LIBS official_library_identity
 foreach path $STD_CELL_LIBS {
  set entry [dict get $official_library_identity files [file normalize $path]]
  set library [dict get $entry library_name]
  if {[sizeof_collection [get_libs -quiet $library]]!=1} {error "Approved target library is not loaded: $library"}
  if {[sizeof_collection [get_lib_cells -quiet "${library}/*"]]!=[dict get $entry cell_count]} {error "Loaded library cell inventory differs: $library"}
 }
}
set sources {}
set f [open [file join $bundle filelists soc_synth.f] r]
foreach line [split [read $f] \n] {if {[string trim $line] ne ""} {lappend sources [file join $bundle $line]}}
close $f
set defines {DISABLE_SV_ASSERTION=1}
set includes {}
foreach d {core perips perips/apb_i2c} {lappend includes [file join $bundle vendor e203_hbirdv2 rtl e203 $d]}
set include_headers {}
set f [open [file join $bundle filelists includes.f] r]
foreach line [split [read $f] \n] {if {[string trim $line] ne ""} {lappend include_headers [file join $bundle $line]}}
close $f
set frozen_inputs [dict create]
foreach p [concat $sources $include_headers $STD_CELL_LIBS $SRAM_LIBS [list $config $PLATFORM_SDC $LIBRARY_IDENTITY_FILE]] {
 dict set frozen_inputs [file normalize $p] [file_sha $p]
}
set provenance [dict create schema qingyu-full-official-bus-assessment-v1 bundle_sha256 $env(QINGYU_BUNDLE_SHA256) \
 top qingyu_e203_soc_top inputs_sha256 $frozen_inputs stdcell_family $STD_CELL_FAMILY \
 library_provenance $LIBRARY_PROVENANCE timing_provenance $TIMING_PROVENANCE \
 area_unit_provenance $AREA_UNIT_PROVENANCE sram_area_provenance $SRAM_AREA_PROVENANCE \
 official_archive_sha256 [dict get $official_library_identity archive_sha256] official_library_identity $official_library_identity \
 standard_area_unit_to_um2 $AREA_UNIT_TO_UM2 official_macro_area_um2 $SRAM_AREA_UM2 \
 clock_requirement_hz 150000000 status pending_tool_reports]
proc save_provenance {} {
 global provenance work
 set f [open [file join $work assessment_provenance.tcl] w]
 puts $f [list set assessment_provenance $provenance];close $f
}
proc verify_frozen_inputs {} {
 global frozen_inputs
 dict for {path expected} $frozen_inputs {if {[file_sha $path] ne $expected} {error "Input changed during run: $path"}}
}
save_provenance

# Preserve explicit accounting boundaries; never subtract the parent subsystem
# because it contains the newly added CPU/DMA merge.
set fixed_cpu_prefix u_e203_subsys_top/u_e203_subsys_main/u_e203_cpu_top
set fixed_prefixes {
 u_e203_subsys_top/u_e203_subsys_main/u_e203_subsys_mems
 u_e203_subsys_top/u_e203_subsys_main/u_e203_subsys_hclkgen
 u_e203_subsys_top/u_e203_subsys_main/u_main_ResetCatchAndSync_2_1
 u_e203_subsys_top/u_e203_subsys_main/u_e203_subsys_plic
 u_e203_subsys_top/u_e203_subsys_main/u_e203_subsys_clint
 u_e203_subsys_top/u_e203_subsys_main/u_e203_subsys_perips
 u_e203_subsys_top/u_sirv_debug_module
 u_e203_subsys_top/u_sirv_aon_top
}
proc below {name prefix} {expr {$name eq $prefix || [string match "${prefix}/*" $name]}}
proc area_class {name reference} {
 global fixed_cpu_prefix fixed_prefixes
 if {[below $name u_fio]} {
  if {[string match RAMSP* $reference]} {return included_private_macro}
  if {[below $name u_fio/engine/compute]} {return included_compute_logic}
  if {[below $name u_fio/engine/transport]} {return included_transport_logic}
  if {[below $name u_fio/engine/decoder] || [below $name u_fio/engine/encoder]} {return included_codec_logic}
  if {[below $name u_fio/engine/reorder]} {return included_reorder_logic}
  if {[below $name u_fio/engine]} {return included_engine_control_logic}
  return included_fio_mmio_logic
 }
 if {[below $name u_dma_merge] || [below $name u_e203_subsys_top/u_e203_subsys_main/u_mem_merge]} {return included_new_bus_merges}
 if {[below $name u_shared]} {
  if {$reference eq "RAMSP4096X16"} {return excluded_fixed_shared_macro}
  return included_shared_interface_logic
 }
 if {[below $name $fixed_cpu_prefix]} {
  if {[string match RAMSP* $reference]} {return excluded_cpu_tcm_macro}
  return excluded_reused_cpu_logic
 }
 foreach prefix $fixed_prefixes {if {[below $name $prefix]} {return excluded_fixed_bus_peripheral_logic}}
 return included_adapter_or_boundary_logic
}
proc memory_audit {stage} {
 global bundle work provenance
 source [file join $bundle assessment_expected.tcl]
 set counts [dict create private128 0 private1024 0 shared4096 0 cpu4096 0]
 set out [open [file join $work memories_${stage}.tsv] w]
 puts $out "instance\treference\tclass"
 foreach_in_collection cell [get_cells -hierarchical] {
  set reference [get_attribute $cell ref_name]
  if {![string match RAMSP* $reference]} {continue}
  set name [get_object_name $cell];set kind [area_class $name $reference]
  if {$kind eq "included_private_macro" && $reference eq "RAMSP128X16"} {dict incr counts private128
  } elseif {$kind eq "included_private_macro" && $reference eq "RAMSP1024X16"} {dict incr counts private1024
  } elseif {$kind eq "excluded_fixed_shared_macro"} {dict incr counts shared4096
  } elseif {$kind eq "excluded_cpu_tcm_macro" && $reference eq "RAMSP4096X16"} {dict incr counts cpu4096
  } else {error "Unexpected macro scope $name $reference"}
  puts $out "$name\t$reference\t$kind"
 }
 close $out
 foreach key {private128 private1024 shared4096 cpu4096} {
  set expected [set EXPECTED_[string toupper $key]]
  if {[dict get $counts $key]!=$expected} {error "Macro count changed: $key actual=[dict get $counts $key] expected=$expected"}
 }
 dict set provenance memories_$stage $counts
}
proc timed_endpoint_gate {} {
 global work
 redirect -variable coverage {check_timing -include {no_clock no_input_delay unconstrained_endpoints} -verbose}
 set f [open [file join $work timing_coverage.rpt] w];puts $f $coverage;close $f
 if {[regexp -nocase {Warning:|Error:|\([1-9][0-9]*\)} $coverage]} {error "Unconstrained timing; review full-SoC clocks and I/O, do not waive to continue"}
}
proc clock_period_gate {} {
 global SYSTEM_CLOCK_NAME AON_CLOCK_NAME
 foreach {name expected} [list $SYSTEM_CLOCK_NAME 6.666666667 $AON_CLOCK_NAME 30517.578125] {
  set clocks [get_clocks -quiet $name]
  if {[sizeof_collection $clocks]!=1} {error "Missing/ambiguous required clock $name"}
  if {abs([get_attribute $clocks period]-$expected)>0.000001} {error "Required clock period mismatch: $name"}
 }
}
