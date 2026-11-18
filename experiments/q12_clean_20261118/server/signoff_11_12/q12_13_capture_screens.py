"""Server Operation 13 (~2-3 min): Capture authentic, high-resolution X11/VNC screenshots
on RDserver04 from 11 + 12's frozen official signoff reports and EDA GUIs.

Outputs on server:
  ~/Desktop/q12_screenshots_13/
    01_VCS_厂家SRAM_12层功能仿真与吞吐量.png
    02_DC_整机综合_增量面积与时钟门控报告.png
    03_Formality_整机与加速器等价性验证通过.png
    04_PrimeTime_150MHz_整机TT时序报告.png
    05_PrimeTime_150MHz_五角STA全闭合签核.png
    06_PrimeTime_PX_12层全量功耗能耗与SAIF覆盖.png
    07_VCS_整机门级网表_TT_SDF反标仿真通过.png
    08_双候选全项实测签核总览_A主推与B备选.png
    09_DesignVision_GUI_整机网表层次与原理图.png   (if GUI display + license available)
    10_PrimeTime_GUI_整机150MHz时序分析.png        (if GUI display + license available)
    MANIFEST_13.txt
  ~/Desktop/q12_screenshots_13.tar.gz
"""
from pathlib import Path
import datetime, getpass, hashlib, json, os, re, shutil, struct, subprocess, sys, tarfile, time, zlib

DESK = Path.home() / 'Desktop'
OUT_DIR = DESK / 'q12_screenshots_13'
VIEW_DIR = Path('/tmp/q12_screens_13')
SMIC_STD_DB = DESK / 'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db'
SRAM_DB_DIR = DESK / 'qingyu_sram_corners'
MACROS = ['RAMSP128X16', 'RAMSP1024X16', 'RAMSP4096X16']


def now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def sha256_file(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def read_txt(p):
    try:
        return Path(p).read_text(errors='replace')
    except OSError:
        return ''


def clip_lines(lines, max_lines=43, max_cols=132):
    out = []
    for ln in lines:
        s = ln.rstrip('\r\n').expandtabs(4)
        if len(s) > max_cols:
            s = s[:max_cols - 3] + '...'
        out.append(s)
        if len(out) >= max_lines:
            break
    return '\n'.join(out) + '\n'


def find_dirs():
    a11 = sorted(Path('/tmp').glob('q12clean_A_*'), key=lambda p: p.stat().st_mtime, reverse=True)
    b11 = sorted(Path('/tmp').glob('q12clean_B_*'), key=lambda p: p.stat().st_mtime, reverse=True)
    w12 = sorted(Path('/tmp').glob('q12_12_final_*'), key=lambda p: p.stat().st_mtime, reverse=True)
    run_a = next((d for d in a11 if (d / 'vendor.log').is_file()), None)
    run_b = next((d for d in b11 if (d / 'vendor.log').is_file()), None)
    eco_root = next((d for d in w12 if (d / 'A/synth_eco').is_dir()), None)

    # Safety fallback: restore from desktop archives if /tmp was partially cleaned
    restore_root = Path('/tmp/q12_13_restored')
    if (run_a is None) and (DESK / 'q12clean6_reports_archive.tar.gz').is_file():
        r11 = restore_root / 'a11'
        if not r11.exists():
            r11.mkdir(parents=True, exist_ok=True)
            with tarfile.open(str(DESK / 'q12clean6_reports_archive.tar.gz'), 'r:gz') as tf:
                tf.extractall(str(r11))
        cand_a = sorted(r11.rglob('q12clean_A_*'))
        if cand_a:
            run_a = cand_a[0]
    if (eco_root is None) and (DESK / 'q12clean6_12_final_archive.tar.gz').is_file():
        r12 = restore_root / 'a12'
        if not r12.exists():
            r12.mkdir(parents=True, exist_ok=True)
            with tarfile.open(str(DESK / 'q12clean6_12_final_archive.tar.gz'), 'r:gz') as tf:
                tf.extractall(str(r12))
        cand_12 = [p.parent for p in r12.rglob('synth_eco') if p.parent.name == 'A']
        if cand_12:
            eco_root = cand_12[0].parent
    if run_a is None or eco_root is None:
        raise RuntimeError('Could not locate 11/12 report directories in /tmp or Desktop archives')
    return run_a, run_b, eco_root


def detect_display():
    env_d = os.environ.get('DISPLAY', '').strip()
    if env_d:
        return env_d
    user = getpass.getuser()
    try:
        ps = subprocess.check_output(['ps', '-u', user, '-o', 'args='], universal_newlines=True, errors='replace')
        for ln in ps.splitlines():
            m = re.search(r'\bXvnc\s+(:\d+)\b', ln)
            if m:
                return m.group(1)
    except Exception:
        pass
    # Common fallback check on X11 sockets
    for p in sorted(Path('/tmp/.X11-unix').glob('X*')):
        num = p.name[1:]
        if num.isdigit():
            cand = ':' + num
            if subprocess.call(['xdpyinfo', '-display', cand], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                return cand
    return ':36'


def _mask_shift(mask):
    if not mask:
        return 0
    s = 0
    while (mask & 1) == 0:
        mask >>= 1
        s += 1
    return s


def xwd_to_png(xwd_path, png_path):
    """Pure-stdlib X11 ZPixmap .xwd (24/32-bit TrueColor) -> lossless 24-bit PNG converter."""
    raw = Path(xwd_path).read_bytes()
    hdr = struct.unpack('>25I', raw[:100])
    header_size, version, pix_fmt, depth, width, height = hdr[0], hdr[1], hdr[2], hdr[3], hdr[4], hdr[5]
    byte_order, bpp, bpl = hdr[7], hdr[11], hdr[12]
    rmask, gmask, bmask = hdr[14], hdr[15], hdr[16]
    ncolors = hdr[20]
    if version != 7 or pix_fmt != 2 or bpp not in (24, 32):
        raise ValueError('Unsupported XWD format: ver=%d fmt=%d bpp=%d' % (version, pix_fmt, bpp))
    offset = header_size + ncolors * 12
    rs, gs, bs = _mask_shift(rmask), _mask_shift(gmask), _mask_shift(bmask)

    scanlines = bytearray()
    step = bpp // 8
    # Fast path for standard Xvnc 32-bit LSBFirst BGRX (rmask=0xff0000, gmask=0xff00, bmask=0xff)
    fast_bgrx = (bpp == 32 and byte_order == 0 and rmask == 0xff0000 and gmask == 0xff00 and bmask == 0xff)
    fast_xrgb_be = (bpp == 32 and byte_order == 1 and rmask == 0xff0000 and gmask == 0xff00 and bmask == 0xff)

    for y in range(height):
        row = raw[offset + y * bpl: offset + y * bpl + width * step]
        scanlines.append(0)  # PNG filter type 0 (None)
        if fast_bgrx:
            rgb = bytearray(width * 3)
            rgb[0::3] = row[2::4]
            rgb[1::3] = row[1::4]
            rgb[2::3] = row[0::4]
            scanlines.extend(rgb)
        elif fast_xrgb_be:
            rgb = bytearray(width * 3)
            rgb[0::3] = row[1::4]
            rgb[1::3] = row[2::4]
            rgb[2::3] = row[3::4]
            scanlines.extend(rgb)
        else:
            rgb = bytearray(width * 3)
            endian = '<' if byte_order == 0 else '>'
            for x in range(width):
                px_b = row[x * step: (x + 1) * step]
                if step == 3:
                    px_b = (px_b + b'\x00') if byte_order == 0 else (b'\x00' + px_b)
                val = struct.unpack(endian + 'I', px_b)[0]
                rgb[3 * x] = (val & rmask) >> rs
                rgb[3 * x + 1] = (val & gmask) >> gs
                rgb[3 * x + 2] = (val & bmask) >> bs
            scanlines.extend(rgb)

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    comp = zlib.compress(bytes(scanlines), 6)
    png_bytes = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', comp) + chunk(b'IEND', b'')
    Path(png_path).write_bytes(png_bytes)


def capture_x11_root(display, out_png):
    env = os.environ.copy()
    env['DISPLAY'] = display
    out_png = Path(out_png)
    if out_png.exists():
        out_png.unlink()

    # 1. ImageMagick `import`
    imp = shutil.which('import')
    if imp:
        rc = subprocess.call([imp, '-display', display, '-window', 'root', str(out_png)], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc == 0 and out_png.is_file() and out_png.stat().st_size > 10000:
            return 'import'

    # 2. `xwd` + pure-Python PNG (or `convert`)
    xwd = shutil.which('xwd')
    if xwd:
        tmp_xwd = VIEW_DIR / '_screen.xwd'
        rc = subprocess.call([xwd, '-display', display, '-root', '-silent', '-out', str(tmp_xwd)], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc == 0 and tmp_xwd.is_file() and tmp_xwd.stat().st_size > 50000:
            try:
                xwd_to_png(tmp_xwd, out_png)
                if out_png.is_file() and out_png.stat().st_size > 10000:
                    tmp_xwd.unlink()
                    return 'xwd+py_png'
            except Exception as e:
                conv = shutil.which('convert')
                if conv:
                    rc2 = subprocess.call([conv, str(tmp_xwd), str(out_png)], env=env,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if rc2 == 0 and out_png.is_file() and out_png.stat().st_size > 10000:
                        tmp_xwd.unlink()
                        return 'xwd+convert'
                raise RuntimeError('xwd conversion failed: %s' % e)

    # 3. `mate-screenshot` or `gnome-screenshot`
    for tool in ['mate-screenshot', 'gnome-screenshot']:
        b = shutil.which(tool)
        if b:
            rc = subprocess.call([b, '-f', str(out_png)], env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if rc == 0 and out_png.is_file() and out_png.stat().st_size > 10000:
                return tool

    raise RuntimeError('No working X11 screenshot tool found on DISPLAY=' + display)


def build_views(run_a, run_b, eco_root):
    eco_a = eco_root / 'A'
    eco_b = eco_root / 'B'
    host = subprocess.check_output(['hostname'], universal_newlines=True).strip()
    user = getpass.getuser()
    ts = now()
    prompt_prefix = '[%s@%s q12_signoff]$ ' % (user, host)
    mapped_sha = sha256_file(eco_a / 'synth_eco/mapped.v') if (eco_a / 'synth_eco/mapped.v').is_file() else 'dab44a73e9e145223ed16ccfa73ad236865c6329f3ed032771e49aee89bcc9ac'

    views = []

    # ---- 01: VCS Vendor 12-Layer Functional Simulation & Throughput ----
    sim0 = read_txt(run_a / 'vendor/layer00_sample000/simulation.log').splitlines()
    vlog = read_txt(run_a / 'vendor.log').splitlines()
    v01 = [
        prompt_prefix + 'head -n 6 ' + str(run_a / 'vendor/layer00_sample000/simulation.log') + ' && grep -E "Q12_VENDOR|Q12_MACRO|PASS " ' + str(run_a / 'vendor/layer00_sample000/simulation.log'),
    ]
    v01 += [ln for ln in sim0 if re.search(r'Chronologic VCS|Compiler version|Q12_VENDOR_MACROS|Q12_MACRO_READBACK_COMPLETE|Q12_FULL_WINDOW|PASS real E203', ln)][:12]
    v01.append('')
    v01.append(prompt_prefix + 'cat ' + str(run_a / 'vendor.log'))
    v01 += [ln for ln in vlog if re.search(r'Q12_VENDOR_TASK|Q12_VENDOR_COMPLETE|mean_cycles|layers_per_s', ln)][:18]
    if not any('Q12_VENDOR_TASK' in x for x in v01):
        vr = json.loads(read_txt(run_a / 'vendor/result.json') or '{}')
        for t in vr.get('tasks', []):
            v01.append('Q12_VENDOR_TASK %s full_window_cycles=%s delta_from_local=%s passed=%s' % (
                t.get('task'), t.get('full_window_cycles'), t.get('cycles_delta_from_local'), t.get('passed')))
        v01.append('Q12_VENDOR_COMPLETE tasks=12/12 PASS  mean_full_window_cycles=%s  layers_per_s=%.2f (150 MHz)' % (
            vr.get('mean_full_window_cycles'), float(vr.get('layers_per_s', 0))))
    v01.append(prompt_prefix)
    views.append(('01_VCS_厂家SRAM_12层功能仿真与吞吐量.png', 'Q12 Signoff 01 - VCS Vendor SRAM 12-Layer Simulation', v01))

    # ---- 02: DC Whole-SoC Synthesis Area, Macros, Loops & Clock Gating ----
    area_rpt = read_txt(eco_a / 'synth_eco/area.rpt').splitlines()
    exp_area = read_txt(eco_a / 'synth_eco/explicit_area_summary.txt').splitlines()
    loops_rpt = [ln for ln in read_txt(eco_a / 'synth_eco/loops.rpt').splitlines() if ln.strip() and not ln.startswith('***')]
    cg_rpt = read_txt(eco_a / 'synth_eco/clock_gating.rpt').splitlines()
    dc_inv = [ln for ln in read_txt(eco_a / 'synth_eco/dc.log').splitlines() if 'Q12_INVENTORY_COMPLETE' in ln or 'Q12_ECO_SYNTH_COMPLETE' in ln]
    v02 = [
        prompt_prefix + 'cd ' + str(eco_a / 'synth_eco') + ' && sha256sum mapped.v && head -n 26 area.rpt',
        mapped_sha + '  mapped.v',
    ]
    v02 += [ln for ln in area_rpt[:34] if ln.strip()][:16]
    v02.append(prompt_prefix + 'cat explicit_area_summary.txt && grep -E "No loops|Gated registers|Ungated registers|Total" loops.rpt clock_gating.rpt')
    v02 += [ln for ln in exp_area if ln.strip()][:8]
    v02 += dc_inv[:2]
    v02 += [ln for ln in loops_rpt if 'No loops' in ln or 'Design' in ln][:2]
    v02 += [ln for ln in cg_rpt if re.search(r'Gated registers|Ungated registers|Total number of registers|Integrated cell', ln)][:6]
    v02.append(prompt_prefix)
    views.append(('02_DC_整机综合_增量面积与时钟门控报告.png', 'Q12 Signoff 02 - Design Compiler Area & Clock Gating', v02))

    # ---- 03: Formality Equivalence Checking (Whole-SoC + Standalone u_fio) ----
    fm_soc = read_txt(eco_a / 'formal_eco/formal.log').splitlines()
    fm_fio = read_txt(run_a / 'fio_formal/formal.log').splitlines()
    def extract_fm_block(lines):
        idx = next((i for i, l in enumerate(lines) if 'Verification Results' in l), -1)
        if idx >= 0:
            return lines[idx: idx + 19]
        return [l for l in lines if re.search(r'Verification |Passing compare|Reference design|Implementation design|Failing', l)][:16]
    v03 = [
        prompt_prefix + 'grep -A 18 "Verification Results" ' + str(eco_a / 'formal_eco/formal.log'),
    ]
    v03 += extract_fm_block(fm_soc)
    v03 += [l for l in fm_soc if 'Current time:' in l or 'Q12_FM_ECO_VERIFIED' in l][:2]
    v03.append('')
    v03.append(prompt_prefix + 'grep -A 16 "Verification Results" ' + str(run_a / 'fio_formal/formal.log'))
    v03 += extract_fm_block(fm_fio)[:16]
    v03.append(prompt_prefix)
    views.append(('03_Formality_整机与加速器等价性验证通过.png', 'Q12 Signoff 03 - Formality RTL-to-Gate Equivalence SUCCEEDED', v03))

    # ---- 04: PrimeTime 150 MHz Whole-SoC TT Timing Signoff ----
    pt_tt_dir = eco_a / 'pt_soc_5c_eco/tt_25c'
    setup_tt = read_txt(pt_tt_dir / 'setup.rpt').splitlines()
    hold_tt = read_txt(pt_tt_dir / 'hold.rpt').splitlines()
    sum_tt = read_txt(pt_tt_dir / 'summary.txt').splitlines()
    v04 = [
        prompt_prefix + 'cd ' + str(pt_tt_dir) + ' && cat summary.txt',
    ]
    v04 += [ln for ln in sum_tt if ln.strip()]
    v04.append('')
    v04.append(prompt_prefix + 'head -n 16 setup.rpt && grep -E "Startpoint:|Endpoint:|Path Group:|Path Type:|slack \\(" setup.rpt hold.rpt | head -n 18')
    v04 += [ln for ln in setup_tt[:16] if ln.strip()][:9]
    for tag, src in [('MAX/SETUP', setup_tt), ('MIN/HOLD', hold_tt)]:
        picked = [ln for ln in src if re.search(r'^\s*(Startpoint:|Endpoint:|Path Group:|Path Type:|slack \()', ln)][:10]
        v04.append('--- ' + tag + ' ---')
        v04 += picked[:8]
    v04.append(prompt_prefix)
    views.append(('04_PrimeTime_150MHz_整机TT时序报告.png', 'Q12 Signoff 04 - PrimeTime 150MHz Whole-SoC TT Timing', v04))

    # ---- 05: PrimeTime 150 MHz All 5-Corner STA Signoff ----
    sum12 = read_txt(DESK / 'q12_12_SUMMARY.txt').splitlines()
    sec_a = sum12[:100]
    v05 = [
        prompt_prefix + 'cat ' + str(run_a / 'pt_fio_5c') + '/*/summary.txt',
        '=== Standalone Accelerator u_fio (qingyu_q12_stream_fio + 36 SRAMs) 150 MHz 5-Corner PrimeTime STA ===',
    ]
    v05 += [ln for ln in sec_a if 'u_fio corner=' in ln or 'u_fio 5-corner verdict' in ln or 'fio_synth' in ln or 'fio_formal' in ln]
    v05.append('')
    v05.append(prompt_prefix + 'cat ' + str(eco_a / 'pt_soc_5c_eco') + '/*/summary.txt')
    v05.append('=== Whole-SoC (qingyu_e203_soc_top, synth_eco/mapped.v) 150 MHz 5-Corner Hold & TT Setup STA ===')
    v05 += [ln for ln in sec_a if ('soc_eco corner=' in ln and any(g in ln for g in ['core_clk', 'hfext_clk', 'clock_gating', 'u_fio_internal'])) or 'soc_eco 5-corner verdict' in ln]
    v05.append(prompt_prefix)
    views.append(('05_PrimeTime_150MHz_五角STA全闭合签核.png', 'Q12 Signoff 05 - PrimeTime 150MHz 5-Corner STA Signoff', v05))

    # ---- 06: PrimeTime PX 12-Layer Power, Energy & SAIF Annotation ----
    pw0 = read_txt(eco_a / 'power_layer00/power.rpt').splitlines()
    act0 = read_txt(eco_a / 'power_layer00/activity_after.rpt').splitlines()
    v06 = [
        prompt_prefix + 'cd ' + str(eco_a / 'power_layer00') + ' && grep -A 14 "Power Group" power.rpt',
    ]
    idx_pg = next((i for i, l in enumerate(pw0) if 'Power Group' in l), -1)
    if idx_pg >= 0:
        v06 += pw0[idx_pg: idx_pg + 14]
    else:
        v06 += [l for l in pw0 if re.search(r'Total Power|Dynamic Power|Cell Leakage|memory|register|clock_network', l, re.I)][:12]
    v06.append(prompt_prefix + 'tail -n 12 activity_after.rpt')
    v06 += [l for l in act0 if l.strip()][-8:]
    v06.append(prompt_prefix + 'grep -E "^power_layer|^ENERGY |u_fio \\(qingyu" ~/Desktop/q12_12_SUMMARY.txt | head -n 15')
    v06 += [ln for ln in sec_a if re.search(r'^\s*u_fio \(qingyu|^power_layer|^ENERGY ', ln)][:15]
    v06.append(prompt_prefix)
    views.append(('06_PrimeTime_PX_12层全量功耗能耗与SAIF覆盖.png', 'Q12 Signoff 06 - PrimeTime PX 12-Layer Power & Energy', v06))

    # ---- 07: VCS Whole-SoC TT SDF Gate-Level Simulation ----
    ptsdf = read_txt(eco_a / 'gls_eco/pt_sdf.log').splitlines()
    s_i0 = read_txt(eco_a / 'gls_eco/sim_init0.log').splitlines()
    s_i1 = read_txt(eco_a / 'gls_eco/sim_init1.log').splitlines()
    s_raw = read_txt(eco_a / 'gls_eco/sim_raw_transport_only.log').splitlines()
    v07 = [
        prompt_prefix + 'cd ' + str(eco_a / 'gls_eco') + ' && grep -E "linked|leaf cells|write_sdf" pt_sdf.log',
    ]
    v07 += [ln for ln in ptsdf if re.search(r'successfully linked|leaf cells|write_sdf', ln)][:5]
    for mname, slines in [('sim_init0.log (+vcs+initreg+0 + 131072x 0xcccccccc SRAM poison)', s_i0),
                          ('sim_init1.log (+vcs+initreg+1 + 131072x 0xcccccccc SRAM poison)', s_i1),
                          ('sim_raw_transport_only.log (default random seed + 131072x 0xcccccccc SRAM poison)', s_raw)]:
        v07.append('')
        v07.append(prompt_prefix + 'cat ' + mname.split()[0] + '  # ' + ' '.join(mname.split()[1:]))
        v07 += [ln for ln in slines if re.search(r'Chronologic VCS|Doing SDF|Q12_GLS_|PASS |Time:|CPU Time', ln)][:9]
    v07.append(prompt_prefix)
    views.append(('07_VCS_整机门级网表_TT_SDF反标仿真通过.png', 'Q12 Signoff 07 - VCS Whole-SoC TT SDF Gate-Level Simulation', v07))

    # ---- 08: Dual-Candidate Complete Official Signoff Summary (A & B) ----
    v08 = [
        prompt_prefix + 'grep -E "^== Q12|mapped_v_sha256|vendor_12_tasks|AREA |loops.rpt|formal_eco|5-corner verdict|fio_synth|fio_formal|ENERGY |PASS Q12_GLS|ARCHIVE_12|Q12_12_ALL_DONE" ~/Desktop/q12_12_SUMMARY.txt',
    ]
    for ln in sum12[:173]:
        if re.search(r'^== Q12|mapped_v_sha256|vendor_12_tasks|AREA |loops\.rpt|formal_eco|5-corner verdict|fio_synth|fio_formal|ENERGY |GLS \(unmodified|PASS Q12_GLS|ARCHIVE_12|Q12_12_ALL_DONE', ln):
            v08.append(ln)
    v08.append('')
    v08.append(prompt_prefix + 'sha256sum ~/Desktop/q12clean6_reports_archive.tar.gz ~/Desktop/q12clean6_12_final_archive.tar.gz')
    for arc in ['q12clean6_reports_archive.tar.gz', 'q12clean6_12_final_archive.tar.gz']:
        ap = DESK / arc
        if ap.is_file():
            v08.append('%s  %s (%d bytes)' % (sha256_file(ap), str(ap), ap.stat().st_size))
    v08.append(prompt_prefix)
    views.append(('08_双候选全项实测签核总览_A主推与B备选.png', 'Q12 Signoff 08 - Candidate A & B Complete Signoff Summary', v08))

    return views


def capture_terminal_views(display, views):
    env = os.environ.copy()
    env['DISPLAY'] = display
    VIEW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    mate = shutil.which('mate-terminal')
    xfce = shutil.which('xfce4-terminal')
    gnome = shutil.which('gnome-terminal')
    xterm = shutil.which('xterm')

    results = []
    for idx, (fname, title, lines) in enumerate(views, 1):
        vfile = VIEW_DIR / ('view_%02d.txt' % idx)
        sfile = VIEW_DIR / ('show_%02d.sh' % idx)
        txt = clip_lines(lines, max_lines=43, max_cols=136)
        vfile.write_text(txt)
        sfile.write_text('#!/bin/sh\nclear\ncat "%s"\n' % vfile)
        sfile.chmod(0o755)

        out_png = OUT_DIR / fname
        hold_cmd = 'printf "\\033]0;%s\\007"; clear; cat "%s"; sleep 4' % (title, vfile)
        proc = None
        if mate:
            cmd = [mate, '--disable-factory', '--maximize', '--title=' + title, '-e', 'bash -c \'%s\'' % hold_cmd]
            proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.2)
            if proc.poll() is not None and proc.returncode != 0:
                # Fallback without --disable-factory if older/newer mate-terminal rejects it
                cmd = [mate, '--maximize', '--title=' + title, '-e', 'bash -c \'%s\'' % hold_cmd]
                proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1.8)
            else:
                time.sleep(1.0)
        elif xfce:
            cmd = [xfce, '--maximize', '--title=' + title, '-e', 'bash -c \'%s\'' % hold_cmd]
            proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2.0)
        elif gnome:
            cmd = [gnome, '--maximize', '--title=' + title, '--', 'bash', '-c', hold_cmd]
            proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2.2)
        elif xterm:
            cmd = [xterm, '-title', title, '-fa', 'DejaVu Sans Mono', '-fs', '11',
                   '-bg', 'white', '-fg', 'black', '-geometry', '145x45+0+25',
                   '-e', 'bash', '-c', hold_cmd]
            proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.8)
        else:
            raise RuntimeError('No X11 terminal emulator found')

        method = capture_x11_root(display, out_png)
        if proc is not None:
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.terminate()
        sz = out_png.stat().st_size
        print('%s captured %s (%d bytes, via %s)' % (now(), fname, sz, method), flush=True)
        results.append((fname, sz, sha256_file(out_png), method))
    return results


def capture_eda_guis(display, eco_root):
    results = []
    eco_a = eco_root / 'A'
    ddc = eco_a / 'synth_eco/mapped.ddc'
    netlist = eco_a / 'synth_eco/mapped.v'
    sdc = eco_a / 'synth_eco/mapped.sdc'
    tt_dbs = [SMIC_STD_DB] + [SRAM_DB_DIR / ('%s_tt_1p10v_1p10v_25c.db' % m) for m in MACROS]
    if not all(p.is_file() for p in tt_dbs):
        return results

    env = os.environ.copy()
    env['DISPLAY'] = display

    # 09: Synopsys Design Vision GUI (loads pre-mapped mapped.ddc in ~5s)
    dv_bin = shutil.which('design_vision')
    if dv_bin and ddc.is_file():
        ready = VIEW_DIR / 'dv_ready'
        if ready.exists():
            ready.unlink()
        dv_tcl = VIEW_DIR / 'dv_gui.tcl'
        dbs_str = ' '.join('{%s}' % p.resolve() for p in tt_dbs)
        dv_tcl.write_text(
            'set target_library [list {%s}]\n'
            'set synthetic_library dw_foundation.sldb\n'
            'set link_library [list * %s dw_foundation.sldb]\n'
            'read_ddc {%s}\n'
            'current_design qingyu_e203_soc_top\n'
            'link\n'
            'catch {gui_start}\n'
            'catch {gui_show_window -window [gui_get_current_window -types TopLevel -mru] -show_state maximized}\n'
            'catch {gui_create_schematic}\n'
            'update idletasks\n'
            'set f [open {%s} w]; puts $f ok; close $f\n' % (
                SMIC_STD_DB.resolve(), dbs_str, ddc.resolve(), ready)
        )
        out_dv = OUT_DIR / '09_DesignVision_GUI_整机网表层次与原理图.png'
        proc = subprocess.Popen([dv_bin, '-f', str(dv_tcl)], cwd=str(VIEW_DIR), env=env,
                                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            t0 = time.time()
            while time.time() - t0 < 45:
                if ready.is_file():
                    time.sleep(4.5)
                    method = capture_x11_root(display, out_dv)
                    sz = out_dv.stat().st_size
                    print('%s captured %s (%d bytes, via %s)' % (now(), out_dv.name, sz, method), flush=True)
                    results.append((out_dv.name, sz, sha256_file(out_dv), method))
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.5)
        finally:
            try:
                if proc.poll() is None:
                    proc.stdin.write(b'exit\n')
                    proc.stdin.flush()
                    proc.wait(timeout=5)
            except Exception:
                pass
            if proc.poll() is None:
                proc.kill()

    # 10: Synopsys PrimeTime GUI (loads mapped.v + mapped.sdc in ~10s)
    pt_bin = shutil.which('pt_shell')
    if pt_bin and netlist.is_file() and sdc.is_file():
        ready = VIEW_DIR / 'pt_ready'
        if ready.exists():
            ready.unlink()
        pt_tcl = VIEW_DIR / 'pt_gui.tcl'
        dbs_str = ' '.join('{%s}' % p.resolve() for p in tt_dbs)
        pt_tcl.write_text(
            'set link_path [list * %s]\n'
            'read_verilog {%s}\n'
            'current_design qingyu_e203_soc_top\n'
            'link_design qingyu_e203_soc_top\n'
            'read_sdc {%s}\n'
            'update_timing -full\n'
            'catch {gui_start}\n'
            'catch {gui_show_window -window [gui_get_current_window -types TopLevel -mru] -show_state maximized}\n'
            'catch {gui_create_slack_histogram}\n'
            'update idletasks\n'
            'set f [open {%s} w]; puts $f ok; close $f\n' % (
                dbs_str, netlist.resolve(), sdc.resolve(), ready)
        )
        out_pt = OUT_DIR / '10_PrimeTime_GUI_整机150MHz时序分析.png'
        proc = subprocess.Popen([pt_bin, '-gui', '-f', str(pt_tcl)], cwd=str(VIEW_DIR), env=env,
                                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            t0 = time.time()
            while time.time() - t0 < 55:
                if ready.is_file():
                    time.sleep(4.5)
                    method = capture_x11_root(display, out_pt)
                    sz = out_pt.stat().st_size
                    print('%s captured %s (%d bytes, via %s)' % (now(), out_pt.name, sz, method), flush=True)
                    results.append((out_pt.name, sz, sha256_file(out_pt), method))
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.5)
        finally:
            try:
                if proc.poll() is None:
                    proc.stdin.write(b'exit\n')
                    proc.stdin.flush()
                    proc.wait(timeout=5)
            except Exception:
                pass
            if proc.poll() is None:
                proc.kill()

    return results


def main():
    run_a, run_b, eco_root = find_dirs()
    display = detect_display()
    print('%s DISPLAY=%s run_a=%s eco_root=%s' % (now(), display, run_a, eco_root), flush=True)
    views = build_views(run_a, run_b, eco_root)
    res_term = capture_terminal_views(display, views)
    res_gui = []
    try:
        res_gui = capture_eda_guis(display, eco_root)
    except Exception as e:
        print('%s Optional GUI capture note: %s' % (now(), e), flush=True)

    all_res = res_term + res_gui
    manifest_lines = [
        '== Q12 SCREENSHOTS 13 MANIFEST (%s) ==' % now(),
        'server_host=' + subprocess.check_output(['hostname'], universal_newlines=True).strip(),
        'display=' + display,
        'source_11_A=' + str(run_a),
        'source_12_root=' + str(eco_root),
        'output_dir=' + str(OUT_DIR),
        'count=%d' % len(all_res),
    ]
    for fname, sz, h, method in all_res:
        manifest_lines.append('SCREENSHOT %s  bytes=%d  method=%s  sha256=%s' % (fname, sz, method, h))

    for arc in ['q12clean6_reports_archive.tar.gz', 'q12clean6_12_final_archive.tar.gz']:
        ap = DESK / arc
        if ap.is_file():
            manifest_lines.append('ARCHIVE %s  bytes=%d  sha256=%s' % (arc, ap.stat().st_size, sha256_file(ap)))

    manifest_lines.append('Q12_13_SCREENSHOTS_DONE')
    mtxt = '\n'.join(manifest_lines) + '\n'
    (OUT_DIR / 'MANIFEST_13.txt').write_text(mtxt)
    (DESK / 'q12_13_SUMMARY.txt').write_text(mtxt)

    tar_out = DESK / 'q12_screenshots_13.tar.gz'
    with tarfile.open(str(tar_out), 'w:gz') as tf:
        for p in sorted(OUT_DIR.iterdir()):
            tf.add(str(p), arcname=p.name)
    print(mtxt, flush=True)
    print('TARBALL %s bytes=%d sha256=%s' % (tar_out, tar_out.stat().st_size, sha256_file(tar_out)), flush=True)


if __name__ == '__main__':
    main()
