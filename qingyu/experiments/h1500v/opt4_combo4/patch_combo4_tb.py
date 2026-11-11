"""Add a bus/engine profile line to the combo4 performance testbench."""
import sys, pathlib

p = pathlib.Path(sys.argv[1]) / "tb" / "tb_qingyu_soc_performance.sv"
raw = p.read_bytes().decode()
crlf = "\r\n" in raw
s = raw.replace("\r\n", "\n")
pairs = [
    (""" integer accel_busy_cycles=0, fio_cmd_wait=0, fio_rsp_wait=0;
""", """ integer accel_busy_cycles=0, fio_cmd_wait=0, fio_rsp_wait=0;
 // combo4 profile: shared-port idle cycles before the first START and after it,
 // cycle (relative to the window) of first START, last accel-busy, end of staging.
 integer first_busy=-1, last_busy=-1, idle_pre=0, idle_post=0, st_end=-1, st_started=0;
 integer acc_idle_post=0, wl_busy_n=0, cpu_blk_wait=0;
"""),
    ("""   if(fixture.dut.u_fio.u_accel.busy) accel_busy_cycles++;
""", """   if(fixture.dut.u_fio.u_accel.busy) accel_busy_cycles++;
   if(first_busy<0 && fixture.dut.u_fio.u_accel.busy) first_busy=ticks;
   if(fixture.dut.u_fio.u_accel.busy) last_busy=ticks;
   if(!(`MEM.icb_cmd_valid && `MEM.icb_cmd_ready)) begin
    if(first_busy<0) idle_pre++; else idle_post++;
   end
   if(first_busy>=0 && !fixture.dut.u_fio.u_accel.busy) acc_idle_post++;
   if(fixture.dut.u_fio.st_busy) st_started=1;
   if(st_started && st_end<0 && !fixture.dut.u_fio.st_busy) st_end=ticks;
   if(fixture.dut.u_fio.wl_busy) wl_busy_n++;
"""),
    ("""     $display("QINGYU_PERF_END time_ps=%0t",$realtime);
""", """     $display("QINGYU_PROFILE first_start=%0d last_busy=%0d tail=%0d bus_idle_pre=%0d bus_idle_post=%0d accel_idle_post=%0d st_end=%0d wl_busy=%0d",
      first_busy-start_tick,last_busy-start_tick,end_tick-last_busy,idle_pre,idle_post,acc_idle_post,
      st_end<0 ? -1 : st_end-start_tick,wl_busy_n);
     $display("QINGYU_PERF_END time_ps=%0t",$realtime);
"""),
]
for old, new in pairs:
    assert s.count(old) == 1, old[:60]
    s = s.replace(old, new)
if crlf:
    s = s.replace("\n", "\r\n")
p.write_bytes(s.encode())
print("tb patched")
