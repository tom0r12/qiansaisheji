"""Server Operation 12 (~10 min): Close the final two whole-SoC extra-verification sub-items
on 11's frozen v9 candidates (/tmp/q12clean_A_wwfomkyb and /tmp/q12clean_B__b0skb4j) with
ZERO cross-configuration splicing:

1. Whole-SoC FF 125C hold ECO (`synth_eco/`):
   - Reads 11's `synth/mapped.ddc` in DC under `bc_wc` (`max = tt_v1p1_25c`, `min = ff_v1p21_125c`)
     with 0.035 ns hold uncertainty to clear the -0.0105 ns RAMSP4096X16 hold slack at FF 125C
     while keeping FF -40C (+0.0258 ns) and TT setup (>= 0) closed.
   - Writes `mapped.v`, clean single-corner `mapped.sdc` (multi-line `set_operating_conditions`
     stripped so PrimeTime has zero SEL-005), `explicit_area_summary.txt`, `loops.rpt`, `qor.rpt`.
2. Whole-SoC Formality (`formal_eco/`):
   - Verifies exact staged v9 RTL against `synth_eco/mapped.v` using `mapped.svf` + `eco_hold.svf`.
3. Whole-SoC 5-Corner PrimeTime STA (`pt_soc_5c_eco/`):
   - Verifies `tt_25c` setup >= 0 AND ALL 5 CORNERS (`tt_25c`, `ss_125c`, `ss_m40c`, `ff_125c`,
     `ff_m40c`) hold >= 0 on `synth_eco/mapped.v` (zero SEL-005).
4. Whole-SoC PrimeTime PX Power (`power_eco_layer*`):
   - Re-evaluates all 12 layers for A (and 4 windows for B) on `synth_eco/mapped.v` using 11's
     exact vendor-SRAM SAIFs so area, timing, Formality, power, and GLS all come from the exact
     same `synth_eco/mapped.v` netlist.
5. Whole-SoC TT SDF Gate-Level Simulation (`gls_eco/`, Candidate A):
   - Generates `mapped_tt.sdf` from `synth_eco/mapped.v` via PrimeTime, compiles with
     `+notimingcheck +transport_path_delays +pulse_r/0 +pulse_e/0 +pulse_int_r/0 +pulse_int_e/0`
     and `+vcs+initreg+random`, and runs `layer00_sample000` cold GPIO task under:
       * `raw` (no initreg override — pure transport SDF delays)
       * `init0` (`+vcs+initreg+0` + 131,072-word `0xcccccccc` SRAM poison preload)
       * `init1` (`+vcs+initreg+1` + 131,072-word `0xcccccccc` SRAM poison preload)
6. Archives all new reports to `~/Desktop/q12clean6_12_final_archive.tar.gz` and writes
   `~/Desktop/q12_12_SUMMARY.txt`.
"""
from pathlib import Path
import datetime, hashlib, json, os, re, shutil, subprocess, sys, tarfile, tempfile

DESK = Path.home() / 'Desktop'
PKG_ROOT = DESK / 'q12clean6/q12clean'
SMIC_ROOT = DESK / 'smic_official/S40'
STD_V = SMIC_ROOT / 'smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/verilog/scc40nll_vhsc40_rvt.v'
STD_DB_DIR = SMIC_ROOT / 'smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v'
SRAM_DB_DIR = DESK / 'qingyu_sram_corners'
SRAM_V_ROOT = Path('/storage1/admin_public_dir/SRAM_Lib_2025')
MACROS = ['RAMSP128X16', 'RAMSP1024X16', 'RAMSP4096X16']
CORNER_SPEC = [
    ('tt_25c',  'scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db',   'tt_1p10v_1p10v_25c'),
    ('ss_125c', 'scc40nll_vhsc40_rvt_ss_v0p99_125c_basic.db', 'ss_0p99v_0p99v_125c'),
    ('ss_m40c', 'scc40nll_vhsc40_rvt_ss_v0p99_-40c_basic.db', 'ss_0p99v_0p99v_m40c'),
    ('ff_125c', 'scc40nll_vhsc40_rvt_ff_v1p21_125c_basic.db', 'ff_1p21v_1p21v_125c'),
    ('ff_m40c', 'scc40nll_vhsc40_rvt_ff_v1p21_-40c_basic.db', 'ff_1p21v_1p21v_m40c'),
]
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
KEEP_EXTS = {'.rpt', '.log', '.txt', '.json', '.sdc', '.tsv'}

DC_ECO_TCL = r'''set rc [catch {
 set package $env(Q12_PACKAGE)
 source [file join $package audit.tcl]
 set tt_dbs [list $env(Q12_STD_DB) $env(Q12_RAM128_DB) $env(Q12_RAM1024_DB) $env(Q12_RAM4096_DB)]
 set ff125_dbs [list $env(Q12_FF125_STD_DB) $env(Q12_FF125_RAM128_DB) $env(Q12_FF125_RAM1024_DB) $env(Q12_FF125_RAM4096_DB)]
 foreach db [concat $tt_dbs $ff125_dbs] {
  if {![file readable $db]} {error "Missing DB: $db"}
  read_db $db
 }
 set target_library [list $env(Q12_STD_DB)]
 set synthetic_library dw_foundation.sldb
 set link_library [concat [list *] $tt_dbs [list dw_foundation.sldb]]
 foreach tdb $tt_dbs fdb $ff125_dbs {set_min_library $tdb -min_version $fdb}
 set_svf eco_hold.svf
 read_ddc $env(Q12_IN_DDC)
 current_design qingyu_e203_soc_top
 if {![link]} {error "DDC link failed"}
 set hierarchy [get_cells -hierarchical -filter {is_hierarchical == true}]
 set_ungroup $hierarchy false
 set_boundary_optimization $hierarchy false
 foreach ref {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
  set_dont_touch [get_cells -hierarchical -filter "ref_name == $ref"] true
 }
 set_operating_conditions -max tt_v1p1_25c -max_library scc40nll_vhsc40_rvt_tt_v1p1_25c_basic -min ff_v1p21_125c -min_library scc40nll_vhsc40_rvt_ff_v1p21_125c_basic
 set_fix_hold [get_clocks {hfext_clk core_clk}]
 set_clock_uncertainty -setup 0.1 [all_clocks]
 set_clock_uncertainty -hold 0.035 [all_clocks]
 puts "Q12_ECO_PRE WNS=[get_attribute -quiet [get_timing_paths -delay_type max -max_paths 1] slack] WHS=[get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]"
 redirect -file pre_eco_min.rpt {report_timing -delay_type min -max_paths 10 -significant_digits 6}
 set ok [compile -incremental_mapping -only_hold_time]
 if {!$ok} {error "ECO hold compile failed"}
 puts "Q12_ECO_POST WNS=[get_attribute -quiet [get_timing_paths -delay_type max -max_paths 1] slack] WHS=[get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]"
 set wns [get_attribute -quiet [get_timing_paths -delay_type max -max_paths 1] slack]
 if {$wns ne "" && [lindex [lsort -real $wns] 0] < 0} {
  set_critical_range 0.3 [current_design]
  compile_ultra -incremental -no_autoungroup -no_boundary_optimization
  set whs [get_attribute -quiet [get_timing_paths -delay_type min -max_paths 1] slack]
  if {$whs ne "" && [lindex [lsort -real $whs] 0] < 0} {
   compile -incremental_mapping -only_hold_time
  }
 }
 set_clock_uncertainty -hold 0.02 [all_clocks]
 if {![link]} {error "Post-ECO link failed"}
 write -format verilog -hierarchy -output mapped.v
 write -format ddc -hierarchy -output mapped.ddc
 write_sdc mapped_raw.sdc
 set_svf -off
 q12_inventory after
 source [file join $package hardware report_explicit_area.tcl]
 q12_report_explicit_area
 redirect -file area.rpt {report_area -hierarchy}
 redirect -file constraints.rpt {report_constraint -all_violators}
 redirect -file qor.rpt {report_qor}
 redirect -file loops.rpt {report_timing -loops}
 redirect -file clock_gating.rpt {report_clock_gating}
 puts Q12_ECO_SYNTH_COMPLETE
} message]
if {$rc} {puts "Q12_ECO_SYNTH_FAILED: $message";puts $errorInfo;exit 2}
exit 0
'''

FM_ECO_TCL = r'''set rc [catch {
 set synopsys_auto_setup true
 set verification_clock_gate_hold_mode any
 set hdlin_unresolved_modules error
 source [file join $env(Q12_PACKAGE) hardware sources.tcl]
 set search_path [concat $Q12_INCLUDES $search_path]
 foreach library $env(Q12_LIBRARIES) {read_db $library}
 set_svf $env(Q12_SVF1)
 set_svf -append $env(Q12_SVF2)
 set defines [file normalize defines.v]
 set f [open $defines w]
 foreach definition $Q12_DEFINES {
  regexp {^([A-Za-z_][A-Za-z0-9_]*)(=(.*))?$} $definition dummy name unused value
  puts $f "`define $name $value"
 }
 close $f
 read_sverilog -r -libname WORK [concat [list $defines] $Q12_SOURCES]
 set_top r:/WORK/qingyu_e203_soc_top
 read_verilog -i -libname WORK $env(Q12_NETLIST)
 set_top i:/WORK/qingyu_e203_soc_top
 match
 set verified [verify]
 redirect -file status.rpt {report_status}
 redirect -file failing.rpt {report_failing_points}
 redirect -file aborted.rpt {report_aborted_points}
 redirect -file unverified.rpt {report_unverified_points}
 redirect -file unmatched_bbox.rpt {report_unmatched_points -point_type bbox}
 puts "Q12_FM_ECO_VERIFIED=$verified"
 if {!$verified} {error "Formality ECO verification failed"}
 puts Q12_FM_ECO_COMPLETE
} message]
if {$rc} {puts "Q12_FM_ECO_FAILED: $message";puts $errorInfo;exit 2}
exit 0
'''

PT_CORNER_TCL = r'''set rc [catch {
 set top_mod $env(Q12_TOP_MODULE)
 set corner $env(Q12_CORNER_NAME)
 set link_path [concat [list *] $env(Q12_LIBRARIES)]
 read_verilog $env(Q12_NETLIST)
 current_design $top_mod
 if {![link_design $top_mod]} {error "PT link failed"}
 read_sdc $env(Q12_SDC)
 update_timing -full
 redirect -file setup.rpt {report_timing -delay_type max -slack_lesser_than 100000 -max_paths 10 -significant_digits 6}
 redirect -file hold.rpt {report_timing -delay_type min -slack_lesser_than 100000 -max_paths 10 -significant_digits 6}
 redirect -file constraints.rpt {report_constraint -all_violators}
 set sf [open summary.txt w]
 foreach_in_collection g [get_path_groups *] {
  set gn [get_object_name $g]; set smax NA; set smin NA
  catch {set p [get_timing_paths -group $gn -delay_type max -slack_lesser_than 100000 -max_paths 1]; if {[sizeof_collection $p]>0} {set smax [format "%.6f" [get_attribute $p slack]]}}
  catch {set p [get_timing_paths -group $gn -delay_type min -slack_lesser_than 100000 -max_paths 1]; if {[sizeof_collection $p]>0} {set smin [format "%.6f" [get_attribute $p slack]]}}
  if {$smax ne "NA" || $smin ne "NA"} {
   set ln "Q12_PT_CORNER top=$top_mod corner=$corner group=$gn setup=$smax hold=$smin"
   puts $ln; puts $sf $ln
  }
 }
 catch {
  set fio_cells [get_cells -hierarchical -filter {full_name =~ u_fio/* && (is_sequential == true || is_memory_cell == true)}]
  if {[sizeof_collection $fio_cells] > 0} {
   set fmax NA; set fmin NA
   set pfmax [get_timing_paths -from $fio_cells -to $fio_cells -delay_type max -slack_lesser_than 100000 -max_paths 1]
   if {[sizeof_collection $pfmax] > 0} {set fmax [format "%.6f" [get_attribute $pfmax slack]]}
   set pfmin [get_timing_paths -from $fio_cells -to $fio_cells -delay_type min -slack_lesser_than 100000 -max_paths 1]
   if {[sizeof_collection $pfmin] > 0} {set fmin [format "%.6f" [get_attribute $pfmin slack]]}
   set ln "Q12_PT_CORNER top=$top_mod corner=$corner group=u_fio_internal setup=$fmax hold=$fmin"
   puts $ln; puts $sf $ln
  }
 }
 close $sf
 puts "Q12_PT_CORNER_COMPLETE $top_mod $corner"
} message]
if {$rc} {puts "Q12_PT_CORNER_FAILED: $message";puts $errorInfo;exit 2}
exit 0
'''


def now(): return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def sha256_file(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def strip_multiline_opcond(sdc_text):
    out = []
    skip_cont = False
    for ln in sdc_text.splitlines():
        if skip_cont:
            skip_cont = ln.rstrip().endswith('\\')
            continue
        if re.match(r'^\s*set_operating_conditions\b', ln):
            skip_cont = ln.rstrip().endswith('\\')
            continue
        out.append(ln)
    return '\n'.join(out) + '\n'


def corner_dbs():
    out = {}
    for cname, std_n, sram_s in CORNER_SPEC:
        out[cname] = [(STD_DB_DIR / std_n).resolve()] + [
            (SRAM_DB_DIR / ('%s_%s.db' % (m, sram_s))).resolve() for m in MACROS]
    return out


def latest_11_run(label):
    cands = sorted(Path('/tmp').glob('q12clean_%s_*' % label), key=lambda p: p.stat().st_mtime, reverse=True)
    for d in cands:
        if (d / 'FLOW_DONE').is_file() and (d / 'synth/mapped.ddc').is_file():
            return d
    raise SystemExit('Cannot find 11 run with mapped.ddc for ' + label)


def process_candidate(label, run11, wroot, corners, do_gls):
    cand_pkg = (PKG_ROOT / label).resolve()
    cj = json.loads((run11 / 'candidate.json').read_text())
    cdir = wroot / label; cdir.mkdir(parents=True, exist_ok=True)
    dc_bin = shutil.which('dc_shell') or 'dc_shell'
    fm_bin = shutil.which('fm_shell') or 'fm_shell'
    pt_bin = shutil.which('pt_shell') or 'pt_shell'
    vcs_bin = shutil.which('vcs') or 'vcs'

    tt_dbs = corners['tt_25c']; ff125_dbs = corners['ff_125c']
    env = os.environ.copy()
    env.update(
        Q12_PACKAGE=str(cand_pkg),
        Q12_EXPECT_128=str(cj['n128']),
        Q12_IN_DDC=str((run11 / 'synth/mapped.ddc').resolve()),
        Q12_LIBRARIES=' '.join(str(p) for p in tt_dbs),
    )
    env.update(dict(zip(['Q12_STD_DB', 'Q12_RAM128_DB', 'Q12_RAM1024_DB', 'Q12_RAM4096_DB'], map(str, tt_dbs))))
    env.update(dict(zip(['Q12_FF125_STD_DB', 'Q12_FF125_RAM128_DB', 'Q12_FF125_RAM1024_DB', 'Q12_FF125_RAM4096_DB'], map(str, ff125_dbs))))

    # 1. DC Hold ECO
    sdir = cdir / 'synth_eco'; sdir.mkdir()
    (sdir / 'eco.tcl').write_text(DC_ECO_TCL)
    print('%s [%s] starting DC FF125 hold ECO on %s' % (now(), label, run11 / 'synth/mapped.ddc'), flush=True)
    with (sdir / 'dc.log').open('w') as f:
        rc = subprocess.call([dc_bin, '-f', str(sdir / 'eco.tcl')], cwd=str(sdir), env=env, stdout=f, stderr=subprocess.STDOUT)
    dclog = (sdir / 'dc.log').read_text(errors='replace')
    if rc != 0 or 'Q12_ECO_SYNTH_COMPLETE' not in dclog or not (sdir / 'mapped.v').is_file():
        raise RuntimeError('%s DC ECO failed rc=%d' % (label, rc))
    clean_sdc = sdir / 'mapped.sdc'
    clean_sdc.write_text(strip_multiline_opcond((sdir / 'mapped_raw.sdc').read_text(errors='replace')))

    # 2. Launch Formality ECO in parallel with PrimeTime 5-corner STA
    fmdir = cdir / 'formal_eco'; fmdir.mkdir()
    (fmdir / 'fm.tcl').write_text(FM_ECO_TCL)
    efm = env.copy()
    efm.update(
        Q12_SVF1=str((run11 / 'synth/mapped.svf').resolve()),
        Q12_SVF2=str((sdir / 'eco_hold.svf').resolve()),
        Q12_NETLIST=str((sdir / 'mapped.v').resolve()),
    )
    fm_log_f = (fmdir / 'formal.log').open('w')
    fm_proc = subprocess.Popen([fm_bin, '-f', str(fmdir / 'fm.tcl')], cwd=str(fmdir), env=efm, stdout=fm_log_f, stderr=subprocess.STDOUT)

    # 3. PrimeTime 5-corner STA on synth_eco/mapped.v
    pt5_root = cdir / 'pt_soc_5c_eco'; pt5_root.mkdir()
    pt_procs = []
    for cname, _, _ in CORNER_SPEC:
        pdir = pt5_root / cname; pdir.mkdir()
        (pdir / 'pt.tcl').write_text(PT_CORNER_TCL)
        ept = env.copy()
        ept.update(
            Q12_TOP_MODULE='qingyu_e203_soc_top',
            Q12_CORNER_NAME=cname,
            Q12_NETLIST=str((sdir / 'mapped.v').resolve()),
            Q12_SDC=str(clean_sdc.resolve()),
            Q12_LIBRARIES=' '.join(str(p) for p in corners[cname]),
        )
        pf = (pdir / 'pt.log').open('w')
        pt_procs.append((cname, pdir, subprocess.Popen([pt_bin, '-f', str(pdir / 'pt.tcl')], cwd=str(pdir), env=ept, stdout=pf, stderr=subprocess.STDOUT)))
    for cname, pdir, p in pt_procs:
        p.wait()
        print('%s [%s] PT 5-corner %s rc=%d' % (now(), label, cname, p.returncode), flush=True)

    # 4. PrimeTime Power on synth_eco/mapped.v using 11's vendor SAIFs
    vr = json.loads((run11 / 'vendor/result.json').read_text())
    wanted = None if label == 'A' else [0, 4, 8, 11]
    tasks_to_run = [(i, t) for i, t in enumerate(vr['tasks']) if wanted is None or i in wanted]
    for b in range(0, len(tasks_to_run), 4):
        batch = []
        for i, t in tasks_to_run[b:b + 4]:
            pdir = cdir / ('power_layer%02d' % i); pdir.mkdir()
            act = t['activity']; saif = (run11 / 'vendor' / act['saif_relpath']).resolve()
            (pdir / 'window.json').write_text(json.dumps({'task': t['task'], 'duration_ps': act['duration_ps'], 'saif': str(saif)}) + '\n')
            epw = env.copy()
            epw.update(
                Q12_NETLIST=str((sdir / 'mapped.v').resolve()),
                Q12_SDC=str(clean_sdc.resolve()),
                Q12_SAIF=str(saif),
            )
            pf = (pdir / 'pt.log').open('w')
            batch.append((pdir.name, subprocess.Popen([pt_bin, '-f', str(PKG_ROOT / 'power.tcl')], cwd=str(pdir), env=epw, stdout=pf, stderr=subprocess.STDOUT)))
        for dname, p in batch:
            p.wait()
            print('%s [%s] PT power %s rc=%d' % (now(), label, dname, p.returncode), flush=True)

    # 5. TT SDF Gate-Level Simulation on synth_eco/mapped.v (Candidate A)
    gls_lines = []
    if do_gls:
        sys.path.insert(0, str(PKG_ROOT))
        import run_gls
        gdir = cdir / 'gls_eco'; gdir.mkdir()
        sdf = gdir / 'mapped_tt.sdf'
        wsdf_tcl = gdir / 'write_sdf.tcl'
        wsdf_tcl.write_text(
            'set link_path [list * %s]\n'
            'read_verilog {%s}\n'
            'current_design qingyu_e203_soc_top\n'
            'link_design qingyu_e203_soc_top\n'
            'read_sdc {%s}\n'
            'update_timing\n'
            'write_sdf -version 3.0 -context verilog {%s}\n'
            'exit 0\n' % (' '.join(str(p) for p in tt_dbs), str((sdir / 'mapped.v').resolve()),
                          str(clean_sdc.resolve()), str(sdf))
        )
        with (gdir / 'pt_sdf.log').open('w') as f:
            rc = subprocess.call([pt_bin, '-f', str(wsdf_tcl)], cwd=str(gdir), stdout=f, stderr=subprocess.STDOUT)
        sdf_bytes = sdf.stat().st_size if sdf.is_file() else 0
        gls_lines.append('PT write_sdf rc=%d sdf_bytes=%d' % (rc, sdf_bytes))
        if rc != 0 or sdf_bytes < 100000:
            raise RuntimeError('PT write_sdf failed')
        (gdir / 'tb_gls.sv').write_text(run_gls.TB_GLS)
        sram_vs = [SRAM_V_ROOT / m / 'verilog' / (m + '.v') for m in MACROS]
        simv = gdir / 'simv_gls'
        cmd_comp = [
            vcs_bin, '-full64', '-sverilog', '-timescale=1ns/1ps', '+define+ARM_UD_MODEL',
            '+vcs+initreg+random',
            '+transport_path_delays', '+pulse_r/0', '+pulse_e/0', '+pulse_int_r/0', '+pulse_int_e/0',
            '-v', str(STD_V.resolve()), *[str(x.resolve()) for x in sram_vs],
            str((sdir / 'mapped.v').resolve()), str(gdir / 'tb_gls.sv'),
            '-sdf', 'typ:tb_gls.dut:' + str(sdf), '+neg_tchk', '+notimingcheck',
            '+warn=noSDFCOM_UHICD,noSDFCOM_ANICD',
            '-top', 'tb_gls', '-Mdir=' + str(gdir / 'csrc'), '-o', str(simv),
        ]
        with (gdir / 'compile.log').open('w') as f:
            rc = subprocess.call(cmd_comp, cwd=str(gdir), stdout=f, stderr=subprocess.STDOUT)
        gls_lines.append('VCS GLS compile rc=%d' % rc)
        if rc != 0 or not simv.is_file():
            raise RuntimeError('VCS GLS compile failed')
        t0 = json.loads((cand_pkg / 'vendor/manifest.json').read_text())['tasks'][0]
        case_src = cand_pkg / 'vendor/tasks' / t0['directory']
        for n in ['input.hex', 'expected.hex', 'dense.hex']:
            shutil.copy2(str(case_src / n), str(gdir / n))
        shutil.copy2(str(cand_pkg / 'vendor/firmware64.hex'), str(gdir / 'firmware64.hex'))

        for mode_name, extra_arg in [('init0', ['+vcs+initreg+0']), ('init1', ['+vcs+initreg+1']), ('raw_transport_only', [])]:
            slog = gdir / ('sim_%s.log' % mode_name)
            cmd_run = [
                str(simv), *extra_arg,
                '+FIRMWARE=firmware64.hex', '+INPUT=input.hex', '+EXPECTED=expected.hex',
                '+OUTPUT_DUMP=observed_%s.hex' % mode_name,
                '+INPUT_WORDS=' + str(t0['input_words']), '+OUTPUT_WORDS=12690',
            ]
            with slog.open('w') as f:
                rc = subprocess.call(cmd_run, cwd=str(gdir), stdout=f, stderr=subprocess.STDOUT)
            stxt = slog.read_text(errors='replace')
            gls_lines.append('GLS (unmodified stdcell lib) mode=%s rc=%d' % (mode_name, rc))
            for ln in stxt.splitlines():
                if re.search(r'Doing SDF|Q12_GLS_|PASS |Fatal|Error', ln):
                    gls_lines.append('  ' + ln)

        # If VCS +vcs+initreg+0 did not initialize sequential UDPs in -v stdcell library,
        # also run binary power-on UDP initialization (both 0 and 1 polarities) on exact same netlist+SDF.
        init0_txt = (gdir / 'sim_init0.log').read_text(errors='replace')
        if 'PASS Q12_GLS_COMPLETE' not in init0_txt:
            raw_std = STD_V.read_text(errors='replace')
            for bit in ['0', '1']:
                def _add_udp_init(m):
                    hdr, out_sig, body = m.group(1), m.group(2), m.group(3)
                    if re.search(r'\binitial\b', body):
                        return m.group(0)
                    return "%s\n  initial %s = 1'b%s;\n%s" % (hdr, out_sig, bit, body)
                patched_std = re.sub(
                    r'(primitive\s+\w+\s*\(\s*(\w+)\s*,[^;]+;\s*(?:output\s+[^;]+;\s*|input\s+[^;]+;\s*|reg\s+\2\s*;\s*)+?\breg\b[^;]*;)(\s*table\b)',
                    _add_udp_init, raw_std, flags=re.S)
                if 'initial ' not in patched_std:
                    patched_std = re.sub(
                        r'(\breg\s+(\w+)\s*;)(\s*table\b)',
                        lambda m: "%s\n  initial %s = 1'b%s;%s" % (m.group(1), m.group(2), bit, m.group(3)),
                        raw_std)
                std_p = gdir / ('std_udp_init%s.v' % bit)
                std_p.write_text(patched_std)
                simv_u = gdir / ('simv_udp%s' % bit)
                c_u = [
                    vcs_bin, '-full64', '-sverilog', '-timescale=1ns/1ps', '+define+ARM_UD_MODEL',
                    '+vcs+initreg+random',
                    '+transport_path_delays', '+pulse_r/0', '+pulse_e/0', '+pulse_int_r/0', '+pulse_int_e/0',
                    '-v', str(std_p), *[str(x.resolve()) for x in sram_vs],
                    str((sdir / 'mapped.v').resolve()), str(gdir / 'tb_gls.sv'),
                    '-sdf', 'typ:tb_gls.dut:' + str(sdf), '+neg_tchk', '+notimingcheck',
                    '+warn=noSDFCOM_UHICD,noSDFCOM_ANICD',
                    '-top', 'tb_gls', '-Mdir=' + str(gdir / ('csrc_u' + bit)), '-o', str(simv_u),
                ]
                with (gdir / ('compile_udp%s.log' % bit)).open('w') as f:
                    rc_c = subprocess.call(c_u, cwd=str(gdir), stdout=f, stderr=subprocess.STDOUT)
                if rc_c == 0 and simv_u.is_file():
                    slog = gdir / ('sim_udp_init%s.log' % bit)
                    with slog.open('w') as f:
                        rc_s = subprocess.call([
                            str(simv_u), '+vcs+initreg+' + bit,
                            '+FIRMWARE=firmware64.hex', '+INPUT=input.hex', '+EXPECTED=expected.hex',
                            '+OUTPUT_DUMP=observed_udp%s.hex' % bit,
                            '+INPUT_WORDS=' + str(t0['input_words']), '+OUTPUT_WORDS=12690',
                        ], cwd=str(gdir), stdout=f, stderr=subprocess.STDOUT)
                    stxt = slog.read_text(errors='replace')
                    gls_lines.append('GLS (UDP+reg binary power-on=%s, SRAMs poisoned 0xcccccccc) rc=%d' % (bit, rc_s))
                    for ln in stxt.splitlines():
                        if re.search(r'Doing SDF|Q12_GLS_|PASS |Fatal|Error', ln):
                            gls_lines.append('  ' + ln)
                for p in [std_p, simv_u]:
                    if p.is_file(): p.unlink()
                shutil.rmtree(str(gdir / ('csrc_u' + bit)), ignore_errors=True)
                shutil.rmtree(str(gdir / ('simv_udp%s.daidir' % bit)), ignore_errors=True)
        for p in [sdf, simv]:
            if p.is_file(): p.unlink()
        shutil.rmtree(str(gdir / 'csrc'), ignore_errors=True)
        shutil.rmtree(str(gdir / 'simv_gls.daidir'), ignore_errors=True)

    fm_proc.wait()
    print('%s [%s] Formality ECO rc=%d' % (now(), label, fm_proc.returncode), flush=True)

    # Summarize candidate
    lines = [
        '== Q12 12-FINAL %s (%s, %s) %s' % (label, cj['variant'], cj['fmt'], now()),
        'base_11_run=' + str(run11),
        'eco_work=' + str(cdir),
        'eco_mapped_v_sha256=' + sha256_file(sdir / 'mapped.v'),
        'vendor_12_tasks: passed=%s mean_cycles=%s layers/s=%s deltas=%s' % (
            vr['passed'], vr['mean_full_window_cycles'], vr['layers_per_s'],
            ','.join(str(t['cycles_delta_from_local']) for t in vr['tasks'])),
    ]
    area = dict(re.findall(r'^([A-Z0-9_]+)=(' + NUMBER + r')$', (sdir / 'explicit_area_summary.txt').read_text(), re.M))
    inc = float(area['INCREMENTAL_LIBRARY_AREA'])
    lines.append('AREA (synth_eco TT+FF125-bcwc-hold) incremental=%.1f um2 = %.6f mm2  [fio=%s transport=%s shared_ctrl=%s] full_soc=%s' % (
        inc, inc / 1e6, area['FIO_LIBRARY_AREA'], area['NEW_TRANSPORT_LIBRARY_AREA'], area['SHARED_NONMACRO_LIBRARY_AREA'], area['FULL_SOC_LIBRARY_AREA']))
    for m in re.findall(r'^(Q12_ECO_(?:PRE|POST).*)$', dclog, re.M):
        lines.append('  dc_eco: ' + m)
    lines.append('  loops.rpt: ' + ('No loops.' if 'No loops.' in (sdir / 'loops.rpt').read_text(errors='replace') else 'CHECK'))
    fmlog = (fmdir / 'formal.log').read_text(errors='replace')
    fm_ok = 'Verification SUCCEEDED' in fmlog and 'Q12_FM_ECO_COMPLETE' in fmlog
    pts = ' '.join(re.findall(r'(\d+ Passing compare points|\d+ Failing compare points)', fmlog)[:2])
    lines.append('formal_eco (whole-SoC): %s %s' % ('SUCCEEDED' if fm_ok else 'FAILED', pts))

    lines.append('--- PrimeTime 5-Corner STA on synth_eco/mapped.v (SEL-005 count checked) ---')
    hold_all_met = True; tt_setup_met = True
    for cname, _, _ in CORNER_SPEC:
        ptlog = (pt5_root / cname / 'pt.log').read_text(errors='replace')
        sel005 = ptlog.count('SEL-005')
        for m in re.finditer(r'^Q12_PT_CORNER top=(\S+) corner=(\S+) group=(\S+) setup=(\S+) hold=(\S+)', (pt5_root / cname / 'summary.txt').read_text(errors='replace'), re.M):
            _, cn, gn, smax, smin = m.groups()
            lines.append('  soc_eco corner=%-8s group=%-24s setup=%s ns  hold=%s ns  (SEL005=%d)' % (cn, gn, smax, smin, sel005))
            if smin != 'NA' and float(smin) < 0: hold_all_met = False
            if cn == 'tt_25c' and smax != 'NA' and float(smax) < 0: tt_setup_met = False
    lines.append('  soc_eco 5-corner verdict: TT_setup=%s  ALL_5_CORNER_HOLD=%s' % (
        'MET' if tt_setup_met else 'VIOLATED', 'MET' if hold_all_met else 'VIOLATED'))

    # Reference 11's standalone u_fio 5-corner result (same frozen RTL)
    lines.append('--- Standalone u_fio (from 11 same frozen RTL) ---')
    for ln in (run11 / 'SUMMARY.txt').read_text(errors='replace').splitlines():
        if ln.startswith('fio_synth') or ln.startswith('fio_formal') or ln.strip().startswith('u_fio '):
            lines.append(ln)

    pw = []
    for d in sorted(cdir.glob('power_layer*')):
        rep = (d / 'power.rpt').read_text(errors='replace'); meta = json.loads((d / 'window.json').read_text())
        m = re.search(r'^\s*Total Power\s*=\s*(' + NUMBER + r')\s*([munp]?W)?', rep, re.M)
        if m:
            scale = {'W': 1, 'mW': 1e-3, 'uW': 1e-6, 'nW': 1e-9, 'pW': 1e-12}.get(m.group(2) or 'W', 1)
            w = float(m.group(1)) * scale
            pw.append((d.name, w, w * meta['duration_ps'] * 1e-6))
    for n, w, e in pw:
        lines.append('%s: power=%.3f mW energy=%.4f uJ' % (n, w * 1e3, e))
    if pw:
        es = [x[2] for x in pw]
        lines.append('ENERGY (synth_eco) mean=%.4f uJ (min=%.4f max=%.4f) over %d windows; mean power=%.3f mW' % (
            sum(es) / len(es), min(es), max(es), len(pw), 1e3 * sum(x[1] for x in pw) / len(pw)))
        act_txt = (sorted(cdir.glob('power_layer*'))[0] / 'activity_after.rpt').read_text(errors='replace')
        for ln in act_txt.splitlines():
            if 'Total' in ln or 'Not Annotated' in ln:
                lines.append('  activity_check: ' + ln.strip())

    if gls_lines:
        lines.append('--- TT SDF Gate-Level Simulation on synth_eco/mapped.v ---')
        lines += gls_lines

    out = '\n'.join(lines) + '\n'
    (cdir / 'SUMMARY.txt').write_text(out)
    return out


def main():
    corners = corner_dbs()
    A11 = latest_11_run('A')
    B11 = latest_11_run('B')
    wroot = Path(tempfile.mkdtemp(prefix='q12_12_final_', dir='/tmp'))
    print('Q12_12_WORK_ROOT=' + str(wroot), flush=True)
    sA = process_candidate('A', A11, wroot, corners, do_gls=True)
    sB = process_candidate('B', B11, wroot, corners, do_gls=False)
    arc = DESK / 'q12clean6_12_final_archive.tar.gz'
    cnt = 0
    with tarfile.open(str(arc), 'w:gz') as tf:
        for p in sorted(wroot.rglob('*')):
            if p.is_file() and p.suffix.lower() in KEEP_EXTS and p.stat().st_size <= 25_000_000:
                tf.add(str(p), arcname=p.relative_to(wroot).as_posix()); cnt += 1
    arc_line = '== ARCHIVE_12: path=%s files=%d bytes=%d sha256=%s\n' % (arc, cnt, arc.stat().st_size, sha256_file(arc))
    full = sA + '\n' + sB + '\n' + arc_line + 'Q12_12_ALL_DONE\n'
    (DESK / 'q12_12_SUMMARY.txt').write_text(full)
    print(full, flush=True)


if __name__ == '__main__':
    main()
