#!/bin/sh
# Isolated FPGA-free fast16 engineering run on the contest server.
set -eu
run=$(mktemp -d "$HOME/Desktop/qingyu_fast16_XXXXXX")
echo "QINGYU_FAST16_DIRECTORY: $run"
trap 'rc=$?; if [ "$rc" -ne 0 ]; then echo "QINGYU_FAST16_STOPPED: $run"; fi' EXIT
cd "$run"
# PAYLOAD
baseline="$HOME/Desktop/qingyu_soc_macro_GRZ25R"
dc=/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell
pt=/eda/synopsys/prime/prime_2022.03-SP5-1/bin
(cd "$baseline/inputs" && sha256sum -c baseline.sha256 && sha256sum -c macro_inputs.sha256) > reference.log
cp -R "$baseline/inputs" inputs
cp "$baseline/vendor_models.sha256" .
sha256sum -c vendor_models.sha256 >> reference.log
cd inputs
sha256sum -c ../data.sha256 > ../data_check.log
cp ../rtl/*.sv rtl/
for dir in layer??; do cp "../$dir/firmware64.hex" "$dir/firmware64.hex"; done
sed -i 's/PASS real E203 + 89 SRAM macros/PASS real E203 + 103 SRAM macros/' macro/tb_qingyu_soc_macros.sv
find rtl macro generated vendor layer?? tb -type f -print | sort | xargs sha256sum > fast.sha256
echo 'QINGYU_FAST16: checking 12 cold tasks with vendor SRAM'
models=/storage1/admin_public_dir/SRAM_Lib_2025
includes=+incdir+vendor/e203_hbirdv2/rtl/e203/core+vendor/e203_hbirdv2/rtl/e203/perips+vendor/e203_hbirdv2/rtl/e203/perips/apb_i2c
vcs -full64 -sverilog -timescale=1ns/1ps +define+ARM_UD_MODEL +define+DISABLE_SV_ASSERTION=1 "$includes" -top tb_qingyu_soc_performance -f sources_macro.f "$models/RAMSP128X16/verilog/RAMSP128X16.v" "$models/RAMSP1024X16/verilog/RAMSP1024X16.v" "$models/RAMSP4096X16/verilog/RAMSP4096X16.v" -o "$run/simv" > ../compile.log 2>&1 || { tail -20 ../compile.log; exit 1; }
for layer in layer??; do
 "$run/simv" +FIRMWARE="$layer/firmware64.hex" +SHARED="$layer/shared.hex" +EXPECTED="$layer/expected.hex" > "../$layer.log" 2>&1
 grep -q 'PASS real E203 + 103 SRAM macros: 25344 physical readback outputs' "../$layer.log" || { tail -20 "../$layer.log"; exit 1; }
 grep -q 'load_words=11936 outputs=25344 ' "../$layer.log"
 sed -n "s/^QINGYU_PERF_WINDOW cycles=\([0-9]*\) .*/$layer \1/p" "../$layer.log" >> ../cycles.tsv
done
cd "$run"
awk 'NF!=2 || $2<=0 {exit 1} {s+=$2} END{if(NR!=12 || s<=0)exit 1; printf "QINGYU_FAST16_AVG_MS=%.6f TASKS_PER_SECOND=%.4f\n",s/12/150000,150000000*12/s}' cycles.tsv
awk '$1=="layer00"{print $2}' cycles.tsv > cycles.txt
mkdir area
echo 'QINGYU_FAST16: mapping FIO and 23 private macros at SS -40C'
(cd area && "$dc" -f ../area.tcl > dc.log 2>&1)
grep -q '^QINGYU_FIO_AREA_REPORTS_READY' area/dc.log || { tail -30 area/dc.log; exit 1; }
awk '/Total cell area:/ {print "QINGYU_FAST16_AREA_LIBRARY_UNITS=" $NF; found=1; if($NF>=300000)exit 1} END{if(!found)exit 1}' area/area.rpt
grep -m1 'slack (' area/timing_max.rpt
echo 'QINGYU_FAST16: mapping digital SoC with frozen fast16 FIO'
"$dc" -f soc.tcl > dc_soc.log 2>&1
grep -q '^QINGYU_SOC_SYNTH_REPORTS_READY' dc_soc.log || { tail -20 dc_soc.log; exit 1; }
cd inputs
vcs -full64 -sverilog -timescale=1ns/1ps -debug_access+all +define+DISABLE_SV_ASSERTION=1 "$includes" -top tb_qingyu_soc_performance -f sources.f -Mdir="$run/logic_csrc" -o "$run/logic_sim" > ../logic_compile.log 2>&1 || { tail -20 ../logic_compile.log; exit 1; }
echo 'QINGYU_FAST16: capturing layer00 logic activity'
"$run/logic_sim" +FIRMWARE=layer00/firmware64.hex +SHARED=layer00/shared.hex +EXPECTED=layer00/expected.hex +ACTIVITY=../logic.vcd > ../logic.log 2>&1
cd "$run"
grep -q 'PASS real E203' logic.log
grep -q "^QINGYU_PERF_WINDOW cycles=$(cat cycles.txt) " logic.log
start=$(sed -n 's/^QINGYU_PERF_START .*time_ps=\([0-9]*\)$/\1/p' logic.log)
stop=$(sed -n 's/^QINGYU_PERF_END time_ps=\([0-9]*\)$/\1/p' logic.log)
test "$((stop-start))" -eq "$(awk '{printf "%.0f",$1*6666}' cycles.txt)"
scale=$(awk '/\$timescale/{s=1} s{printf "%s ",$0} s && /\$end/{exit}' logic.vcd | tr -d '[:space:]')
test "$scale" = '$timescale1ps$end'
"$pt/vcd2saif" -64 -input logic.vcd -output layer00.saif -time "$start" "$stop" > conversion.log 2>&1
test -s layer00.saif
awk '/\(TIMESCALE /{gsub(/[()]/,""); scale=$2;unit=$3} /\(DURATION /{gsub(/[()]/,"");duration=$2} END{factor=(unit=="ps"?1:unit=="ns"?1000:0);delta=scale*factor*duration-want;if(!factor || delta>1 || delta < -1)exit 1}' want="$((stop-start))" layer00.saif
sha256sum qingyu_soc_mapped.v qingyu_soc_engineering.sdc layer00.saif > inputs.sha256
"$pt/pt_shell" -f pre.tcl > pre.log 2>&1
grep -q '^QINGYU_SOC_POWER_INPUT_REPORTS_READY' pre.log || { tail -20 pre.log; exit 1; }
cp pre.tcl run.tcl
sh supplement.sh "$run"
