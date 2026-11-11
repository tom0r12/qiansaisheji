"""Compare LANES=1/4 with frozen integer vectors using isolated native models.

This measures diagnostic compute cycles and a testbench MMIO-host window.
It is not E203 end-to-end performance, physical timing, power or area evidence.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.reference import export_layer_vectors

TB = r'''`timescale 1ns/1ps
module tb_parallelism_study;
 parameter integer LANES=4;
 localparam integer ROWS=99,K=64,N=256,TILES=N/LANES;
 reg clk=0,rst_n=0;
 always #3.333333 clk=~clk;
 reg valid=0,is_read=0;
 reg [15:0] addr=0;
 reg [31:0] data=0;
 wire ready,rvalid,rerror;
 wire [31:0] rdata;
 reg rready=1;
 qingyu_accel #(.ROWS(ROWS),.K(K),.LANES(LANES)) dut(
  .clk(clk),.rst_n(rst_n),.icb_cmd_valid(valid),.icb_cmd_ready(ready),
  .icb_cmd_read(is_read),.icb_cmd_addr(addr),.icb_cmd_wdata(data),.icb_cmd_wmask(4'hf),
  .icb_rsp_valid(rvalid),.icb_rsp_ready(rready),.icb_rsp_rdata(rdata),.icb_rsp_err(rerror));
 reg [31:0] xv[0:ROWS*K/2-1],wv[0:K*N/2-1],mv[0:N*2-1],yv[0:ROWS*N-1];
 string vectors;
 integer tile,index,outputs=0,polls=0;
 longint unsigned cycles=0,compute_sum=0,commands=0,reads=0,writes=0;
 longint unsigned begin_cycle=0,end_cycle=0;
 reg began=0,pending_last_output=0;
 always @(posedge clk) if(rst_n) begin
  cycles<=cycles+1;
  if(valid&&ready) begin
   commands<=commands+1;
   if(is_read) reads<=reads+1; else writes<=writes+1;
   if(!began&&!is_read&&addr==16'h1000) begin began<=1;begin_cycle<=cycles;end
   pending_last_output<=is_read&&(tile==TILES-1)&&(addr==16'h7000+(ROWS*LANES-1)*4);
  end
  if(rvalid&&rready&&pending_last_output) begin end_cycle<=cycles;pending_last_output<=0;end
 end
 task automatic access;
  input rd;
  input [15:0] address;
  input [31:0] value;
  output reg [31:0] result;
  integer ticks;
  begin
   @(negedge clk); valid=1;is_read=rd;addr=address;data=value;
   ticks=0;@(posedge clk);
   while(!ready) begin ticks=ticks+1;if(ticks>1000)$fatal(1,"cmd timeout");@(posedge clk);end
   @(negedge clk);valid=0;ticks=0;
   while(!rvalid) begin ticks=ticks+1;if(ticks>1000)$fatal(1,"rsp timeout");@(negedge clk);end
   if(rerror)$fatal(1,"bus error addr=%h",address);
   result=rdata;@(posedge clk);
  end
 endtask
 task automatic wr;
  input [15:0] address;input [31:0] value;reg [31:0] ignored;
  begin access(0,address,value,ignored);end
 endtask
 task automatic rd;
  input [15:0] address;output reg [31:0] value;
  begin access(1,address,0,value);end
 endtask
 reg [31:0] result,status;
 initial begin
  if(!$value$plusargs("VECTORS=%s",vectors))$fatal(1,"missing vectors");
  $readmemh({vectors,"/x_words.hex"},xv);$readmemh({vectors,"/w_tile_words.hex"},wv);
  $readmemh({vectors,"/meta_words.hex"},mv);$readmemh({vectors,"/y_tile_words.hex"},yv);
  repeat(5)@(posedge clk);@(negedge clk);rst_n=1;
  rd(0,result);if(result!==32'h51590001)$fatal(1,"ID mismatch");
  wr(4,4);wr(16'h000c,11);
  for(index=0;index<ROWS*K/2;index=index+1)wr(16'h1000+index*4,xv[index]);
  for(tile=0;tile<TILES;tile=tile+1)begin
   wr(16'h0010,tile*LANES);
   for(index=0;index<K*LANES/2;index=index+1)wr(16'h5000+index*4,wv[tile*K*LANES/2+index]);
   for(index=0;index<LANES*2;index=index+1)wr(16'h6000+index*4,mv[tile*LANES*2+index]);
   wr(4,3);status=1;
   while(status[0])begin rd(8,status);polls=polls+1;if(polls>2000000)$fatal(1,"compute timeout");end
   if(status!==2)$fatal(1,"bad status=%h",status);
   rd(16'h0018,result);compute_sum=compute_sum+result;
   rd(16'h001c,result);if(result!=ROWS*LANES)$fatal(1,"output count");
   for(index=0;index<ROWS*LANES;index=index+1)begin
    rd(16'h7000+index*4,result);
    if(result!==yv[tile*ROWS*LANES+index])$fatal(1,"mismatch lanes=%0d tile=%0d index=%0d",LANES,tile,index);
    outputs=outputs+1;
   end
  end
  @(negedge clk);
  if(!began||end_cycle<=begin_cycle)$fatal(1,"missing window");
  $display("STUDY_PASS lanes=%0d outputs=%0d tiles=%0d compute_cycles=%0d mmio_window_cycles=%0d commands=%0d reads=%0d writes=%0d status_polls=%0d",LANES,outputs,TILES,compute_sum,end_cycle-begin_cycle+1,commands,reads,writes,polls);
  $finish;
 end
 initial begin #1000000000;$fatal(1,"study watchdog");end
endmodule
'''

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def execute(command, log, env, timeout):
    start=time.monotonic()
    with log.open("w",encoding="utf-8") as stream:
        stream.write("COMMAND: "+" ".join(str(x) for x in command)+"\n");stream.flush()
        process=subprocess.run([str(x) for x in command],cwd=ROOT,env=env,
            stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
    if process.returncode:
        raise RuntimeError(log.read_text(encoding="utf-8",errors="replace")[-5000:])
    return round(time.monotonic()-start,3)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",type=Path,default=ROOT/"model/full_v2_run/validation_vectors/layer11/integer_case.npz")
    parser.add_argument("--skip-build",action="store_true")
    parser.add_argument("--jobs",type=int,default=2)
    parser.add_argument("--timeout",type=int,default=120)
    args=parser.parse_args()
    started=time.monotonic();args.case=args.case.resolve()
    work=ROOT/"build/parallelism_study";work.mkdir(parents=True,exist_ok=True)
    report_path=ROOT/"reports/parallelism_study.json"
    report={"kind":"FROZEN_REAL_VALIDATION_PARALLELISM_STUDY","passed":False,
        "source_case":str(args.case.relative_to(ROOT)),"source_case_sha256":digest(args.case),
        "layer":11,"clock":"same nominal150MHz functional SV clock in both cases",
        "clock_period_ps_effective":6666,"input_bits":16,"weight_bits":16,
        "accumulator_bits":48,"output_bits":32,"recalibration_performed":False,
        "measurements":[],"limits":["One frozen heldout validation sample of one layer",
            "COMPUTE_CYCLES includes accelerator setup, row initialization and output storage, not just MACs",
            "MMIO window uses a deterministic testbench host, not E203 firmware",
            "No physical timing, area, power, energy or official throughput claim",
            "Nominal150MHz is a simulation clock setting, not150MHz STA evidence"]}
    try:
        tb=work/"tb_parallelism_study.sv";tb.write_text(TB,encoding="utf-8")
        source_paths=[ROOT/"rtl/qingyu_sram16.sv",ROOT/"rtl/qingyu_accel.sv",tb]
        report["source_sha256"]={p.relative_to(ROOT).as_posix():digest(p) for p in source_paths}
        config=args.case.parent/"frozen_training_config.json"
        if config.exists():report["frozen_training_config_sha256"]=digest(config)
        provenance=args.case.parents[2]/"reproducibility_manifest.json"
        if provenance.exists():
            provenance_data=json.loads(provenance.read_text(encoding="utf-8"))
            report["provenance_manifest_sha256"]=digest(provenance)
            report["kwt_source_commit"]=provenance_data.get("source_commit")
            report["source_checkpoint_sha256"]=provenance_data.get("checkpoint")
        tools=ROOT/"tools/verilator/mingw64";verilator=tools/"bin/verilator_bin.exe";cxx=tools/"bin/g++.exe"
        make=Path(r"D:\mingw\mingw64\bin\mingw32-make.exe")
        for tool in (verilator,cxx,make):
            if not tool.is_file():raise FileNotFoundError(tool)
        env=os.environ.copy();env["VERILATOR_ROOT"]=(tools/"share/verilator").as_posix()
        env["PATH"]=str(tools/"bin")+os.pathsep+r"D:\Git\usr\bin"+os.pathsep+env.get("PATH","")
        with np.load(args.case,allow_pickle=False) as case:
            values={name:case[name].copy() for name in ("qx","qw","qb","shifts","qy")}
        for lanes in (1,4):
            vectors=work/f"vectors_l{lanes}"
            export=export_layer_vectors(vectors,values["qx"],values["qw"],values["qb"],values["shifts"],values["qy"],lanes=lanes)
            model_dir=work/f"l{lanes}";model_dir.mkdir(exist_ok=True)
            relative=model_dir.relative_to(ROOT).as_posix();prefix=f"Vparallelism{lanes}"
            generate=[verilator,"--cc","--main","--exe","--timing","--autoflush",
                "--timescale-override","1ns/1ps","--top-module","tb_parallelism_study",
                f"-GLANES={lanes}","--prefix",prefix,"--Mdir",relative,"-Wno-fatal",
                "-CFLAGS","-std=gnu++20 -O1","--output-split","10000"]+[p.relative_to(ROOT).as_posix() for p in source_paths]
            manifest=model_dir/"study_build_manifest.json"
            if not args.skip_build:
                execute(generate,ROOT/f"reports/parallelism_study_l{lanes}_generate.log",env,args.timeout)
                command=[make,"-C",relative,"-f",prefix+".mk","-j",str(args.jobs),
                    "CXX="+cxx.as_posix(),"LINK="+cxx.as_posix(),"AR="+(tools/"bin/ar.exe").as_posix(),
                    "PYTHON3="+Path(sys.executable).as_posix(),"PERL=D:/Git/usr/bin/perl.exe",
                    "VERILATOR_ROOT="+env["VERILATOR_ROOT"]]
                execute(command,ROOT/f"reports/parallelism_study_l{lanes}_build.log",env,args.timeout)
                manifest.write_text(json.dumps({"source_sha256":report["source_sha256"],"lanes":lanes,"generate_command":[str(x) for x in generate]},indent=2))
            elif json.loads(manifest.read_text())["source_sha256"]!=report["source_sha256"]:
                raise ValueError("Study source changed; rebuild native study")
            binary=model_dir/(prefix+".exe")
            if not binary.exists():binary=model_dir/prefix
            log=ROOT/f"reports/parallelism_study_l{lanes}_run.log"
            seconds=execute([binary,"+VECTORS="+vectors.as_posix()],log,env,args.timeout)
            text=log.read_text(encoding="utf-8",errors="replace")
            match=re.search(r"STUDY_PASS lanes=(\d+) outputs=(\d+) tiles=(\d+) compute_cycles=(\d+) mmio_window_cycles=(\d+) commands=(\d+) reads=(\d+) writes=(\d+) status_polls=(\d+)",text)
            if not match:raise ValueError("No study PASS marker")
            keys=["lanes","outputs_checked","tiles","compute_cycles","mmio_window_cycles","commands","reads","writes","status_polls"]
            entry=dict(zip(keys,map(int,match.groups())))
            if entry["outputs_checked"]!=25344:raise ValueError("Incomplete matrix")
            entry.update({"passed":True,"run_wall_seconds":seconds,"log":str(log.relative_to(ROOT)),
                "vector_export":export,"compiled_simulation_sha256":digest(binary),
                "expected_row_words_sha256":digest(vectors/"y_row_words.hex")})
            report["measurements"].append(entry)
            report_path.write_text(json.dumps(report,indent=2))
        one,four=report["measurements"]
        if one["expected_row_words_sha256"]!=four["expected_row_words_sha256"]:
            raise ValueError("Comparison expected outputs differ")
        if digest(args.case)!=report["source_case_sha256"]:raise ValueError("Frozen case changed during run")
        if any(digest(p)!=report["source_sha256"][p.relative_to(ROOT).as_posix()] for p in source_paths):
            raise ValueError("Study RTL/TB changed during run")
        if config.exists() and digest(config)!=report["frozen_training_config_sha256"]:
            raise ValueError("Frozen numerical configuration changed during run")
        report["measured_compute_cycle_speedup_4_vs_1"]=one["compute_cycles"]/four["compute_cycles"]
        report["measured_mmio_host_window_speedup_4_vs_1"]=one["mmio_window_cycles"]/four["mmio_window_cycles"]
        report["passed"]=True
    except Exception as exc:report["error"]=f"{type(exc).__name__}: {exc}"
    report["elapsed_wall_seconds"]=round(time.monotonic()-started,3)
    report_path.write_text(json.dumps(report,indent=2))
    print(json.dumps({"passed":report["passed"],"report":str(report_path),"error":report.get("error"),"compute_ratio":report.get("measured_compute_cycle_speedup_4_vs_1"),"elapsed_wall_seconds":report["elapsed_wall_seconds"]},indent=2),flush=True)
    if not report["passed"]:raise SystemExit(1)

if __name__=="__main__":main()
