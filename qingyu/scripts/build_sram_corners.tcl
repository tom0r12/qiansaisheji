# Engineering corner coverage, not a declaration of official contest conditions.
# Run using Library Compiler. Existing TT databases are left untouched.
set corner_root /storage1/admin_public_dir/SRAM_Lib_2025
set corner_out [file normalize ~/Desktop/qingyu_sram_corners]
set corner_names {
    tt_1p10v_1p10v_25c
    ss_0p99v_0p99v_125c
    ss_0p99v_0p99v_m40c
    ff_1p21v_1p21v_125c
    ff_1p21v_1p21v_m40c
}
set corner_jobs {}
foreach corner $corner_names {
    foreach macro {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
        set name ${macro}_${corner}
        set path [file join $corner_root $macro lib ${name}.lib]
        if {![file readable $path]} {error "Missing corner library $path"}
        lappend corner_jobs [list $name $path]
    }
}
file mkdir $corner_out
set created 0
foreach job $corner_jobs {
    foreach {name path} $job break
    set status [read_lib $path]
    if {$status eq "0"} {error "Failed read_lib: $name"}
    set temporary [file join $corner_out ${name}.[pid].[clock clicks].db]
    set status [write_lib $name -format db -output $temporary]
    if {$status eq "0" || ![file isfile $temporary]} {error "Failed write_lib: $name"}
    if {[file size $temporary] == 0} {error "Empty database: $name"}
    file rename -force $temporary [file join $corner_out ${name}.db]
    incr created
    puts "QINGYU_CORNER_DB_CREATED: $name"
}
puts "QINGYU_SRAM_CORNERS_COMPLETE: $created databases"
puts "OUTPUT_DIRECTORY: $corner_out"
puts "Conversion only; no timing or power acceptance."
