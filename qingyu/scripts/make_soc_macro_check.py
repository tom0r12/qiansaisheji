"""Build a small server runner; existing firmware/images stay on the server."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / 'output/eda/run_soc_macro_check.sh'


def main():
    payloads = {
        'qingyu_banked_sram.sv': ROOT/'rtl/asic/qingyu_banked_sram.sv',
        'qingyu_shared_sram.sv': ROOT/'rtl/asic/qingyu_shared_sram.sv',
        'qingyu_sram16.sv': ROOT/'rtl/asic/qingyu_sram16.sv',
        'sirv_gnrl_ram.v': ROOT/'rtl/asic/sirv_gnrl_ram.v',
        'tb_qingyu_soc_macros.sv': ROOT/'tb/tb_qingyu_soc_macros.sv',
        'tb_qingyu_soc_macro_performance.sv': ROOT/'tb/tb_qingyu_soc_macro_performance.sv',
    }
    script = '''#!/bin/sh
set -eu
base="$HOME/Desktop/qingyu_soc_busfix_LrreQ6/qingyu_soc_performance"
if [ "$#" -gt 0 ]; then base=$1; fi
run=$(mktemp -d "$HOME/Desktop/qingyu_soc_macro_XXXXXX")
echo "QINGYU_MACRO_SOC_DIRECTORY: $run"
mkdir "$run/inputs"
cd "$base"
sha256sum -c inputs.sha256 > "$run/baseline_check.log"
cp inputs.sha256 "$run/inputs/baseline.sha256"
while read -r digest name; do
 name=${name#\\*}
 case "$name" in /*|*..*) echo "Unexpected manifest path: $name"; exit 1;; esac
 mkdir -p "$run/inputs/$(dirname "$name")"
 cp "$name" "$run/inputs/$name"
done < inputs.sha256
cd "$run/inputs"
sha256sum -c baseline.sha256 > "$run/snapshot_check.log"
mkdir macro
'''
    for name, path in payloads.items():
        script += f"cat > macro/{name} <<'QINGYU_MACRO_FILE_END'\n"
        script += path.read_text(encoding='utf-8').rstrip() + '\nQINGYU_MACRO_FILE_END\n'
    script += '''tr -d '\\r' < sources.f | awk '
$0!="vendor/e203_hbirdv2/rtl/e203/general/sirv_gnrl_ram.v" &&
$0!="vendor/e203_hbirdv2/rtl/e203/general/sirv_sim_ram.v" &&
$0!="rtl/qingyu_shared_sram.sv" && $0!="rtl/qingyu_sram16.sv" &&
$0!="tb/tb_qingyu_soc.sv" && $0!="tb/tb_qingyu_soc_performance.sv" {print}
' > sources_macro.f
cat >> sources_macro.f <<'LIST'
macro/qingyu_banked_sram.sv
macro/qingyu_shared_sram.sv
macro/qingyu_sram16.sv
macro/sirv_gnrl_ram.v
macro/tb_qingyu_soc_macros.sv
macro/tb_qingyu_soc_macro_performance.sv
LIST
sha256sum macro/* sources_macro.f > macro_inputs.sha256
modelroot=/storage1/admin_public_dir/SRAM_Lib_2025
for ram in RAMSP128X16 RAMSP1024X16 RAMSP4096X16; do
 test -s "$modelroot/$ram/verilog/$ram.v"
 sha256sum "$modelroot/$ram/verilog/$ram.v"
done > "$run/vendor_models.sha256"
echo 'QINGYU_MACRO_SOC_COMPILING: 9 accelerator + 64 shared + 8 ITCM + 8 DTCM macro instances expected'
vcs -full64 -sverilog -timescale=1ns/1ps +define+ARM_UD_MODEL +define+DISABLE_SV_ASSERTION=1 \\
 +incdir+vendor/e203_hbirdv2/rtl/e203/core+vendor/e203_hbirdv2/rtl/e203/perips+vendor/e203_hbirdv2/rtl/e203/perips/apb_i2c \\
 -top tb_qingyu_soc_performance -f sources_macro.f \\
 "$modelroot/RAMSP128X16/verilog/RAMSP128X16.v" \\
 "$modelroot/RAMSP1024X16/verilog/RAMSP1024X16.v" \\
 "$modelroot/RAMSP4096X16/verilog/RAMSP4096X16.v" \\
 -Mdir="$run/csrc" -o "$run/simv" > "$run/compile.log" 2>&1 || { tail -n 40 "$run/compile.log"; exit 1; }
for layer in layer00 layer01 layer02 layer03 layer04 layer05 layer06 layer07 layer08 layer09 layer10 layer11; do
 echo "QINGYU_MACRO_SOC_RUNNING: $layer"
 "$run/simv" +FIRMWARE="$layer/firmware64.hex" +SHARED="$layer/shared.hex" +EXPECTED="$layer/expected.hex" > "$run/$layer.log" 2>&1 || { tail -n 30 "$run/$layer.log"; exit 1; }
 if grep -Eiq 'Fatal:|Error-' "$run/$layer.log"; then tail -n 30 "$run/$layer.log"; exit 1; fi
 if ! grep -q 'PASS real E203 + 89 SRAM macros' "$run/$layer.log"; then tail -n 30 "$run/$layer.log"; exit 1; fi
 grep -q 'load_words=11936 outputs=25344 ' "$run/$layer.log"
 expected=2605596
 if [ "$layer" = layer00 ]; then expected=2614748; fi
 if ! grep -q "QINGYU_PERF_WINDOW cycles=$expected " "$run/$layer.log"; then
  echo 'QINGYU_MACRO_PERFORMANCE_CHANGED: review timing contract before reporting results'
  tail -n 30 "$run/$layer.log"; exit 1
 fi
 grep -E 'QINGYU_PERF_WINDOW|QINGYU_MACRO_MAILBOX|PASS real E203' "$run/$layer.log"
done
sha256sum -c baseline.sha256 > "$run/baseline_recheck.log"
sha256sum -c macro_inputs.sha256 > "$run/macro_recheck.log"
echo "QINGYU_MACRO_SOC_FUNCTIONAL_COMPLETE: $run"
echo 'Functional macro mode only; not a timing or power result. Program/shared data and zeroed DTCM were loaded through macro ports before CPU boot.'
echo 'Task window and physical output readback verified; no new activity waveform generated.'
'''
    OUTPUT.write_text(script, encoding='utf-8', newline='\n')
    print(f'SERVER_MACRO_CHECK: {OUTPUT} ({OUTPUT.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
