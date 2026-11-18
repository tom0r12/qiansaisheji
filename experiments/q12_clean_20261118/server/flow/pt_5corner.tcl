# PrimeTime single-corner STA check used across all 5 official corners
# (tt_25c, ss_125c, ss_m40c, ff_125c, ff_m40c) for standalone u_fio and whole-SoC.
set rc [catch {
 set top_mod $env(Q12_TOP_MODULE)
 set corner $env(Q12_CORNER_NAME)
 set link_path [concat [list *] $env(Q12_LIBRARIES)]
 read_verilog $env(Q12_NETLIST)
 current_design $top_mod
 if {![link_design $top_mod]} {error "PT link failed for $top_mod at $corner"}
 set fin [open $env(Q12_SDC) r];set lines [split [read $fin] "\n"];close $fin
 set fout [open clean.sdc w];set skip 0
 foreach ln $lines {
  if {$skip} {set skip [regexp {\\\s*$} $ln];continue}
  if {[regexp {^\s*set_operating_conditions\b} $ln]} {set skip [regexp {\\\s*$} $ln];continue}
  puts $fout $ln
 }
 close $fout
 read_sdc clean.sdc
 update_timing -full
 redirect -file setup.rpt {report_timing -delay_type max -slack_lesser_than 100000 -max_paths 10 -significant_digits 6}
 redirect -file hold.rpt {report_timing -delay_type min -slack_lesser_than 100000 -max_paths 10 -significant_digits 6}
 redirect -file constraints.rpt {report_constraint -all_violators}
 set sf [open summary.txt w]
 foreach_in_collection g [get_path_groups *] {
  set gn [get_object_name $g]
  set smax NA; set smin NA
  catch {
   set pmax [get_timing_paths -group $gn -delay_type max -slack_lesser_than 100000 -max_paths 1]
   if {[sizeof_collection $pmax] > 0} {set smax [format "%.6f" [get_attribute $pmax slack]]}
  }
  catch {
   set pmin [get_timing_paths -group $gn -delay_type min -slack_lesser_than 100000 -max_paths 1]
   if {[sizeof_collection $pmin] > 0} {set smin [format "%.6f" [get_attribute $pmin slack]]}
  }
  if {$smax ne "NA" || $smin ne "NA"} {
   set line "Q12_PT_CORNER top=$top_mod corner=$corner group=$gn setup=$smax hold=$smin"
   puts $line; puts $sf $line
  }
 }
 if {$top_mod eq "qingyu_e203_soc_top"} {
  catch {
   set fio_cells [get_cells -hierarchical -filter {full_name =~ u_fio/* && (is_sequential == true || is_memory_cell == true)}]
   if {[sizeof_collection $fio_cells] > 0} {
    set fmax NA; set fmin NA
    set pfmax [get_timing_paths -from $fio_cells -to $fio_cells -delay_type max -slack_lesser_than 100000 -max_paths 1]
    if {[sizeof_collection $pfmax] > 0} {set fmax [format "%.6f" [get_attribute $pfmax slack]]}
    set pfmin [get_timing_paths -from $fio_cells -to $fio_cells -delay_type min -slack_lesser_than 100000 -max_paths 1]
    if {[sizeof_collection $pfmin] > 0} {set fmin [format "%.6f" [get_attribute $pfmin slack]]}
    set line "Q12_PT_CORNER top=$top_mod corner=$corner group=u_fio_internal setup=$fmax hold=$fmin"
    puts $line; puts $sf $line
   }
  }
 }
 close $sf
 puts "Q12_PT_CORNER_COMPLETE $top_mod $corner"
} message]
if {$rc} {puts "Q12_PT_CORNER_FAILED: $message";puts $errorInfo;exit 2}
exit 0
