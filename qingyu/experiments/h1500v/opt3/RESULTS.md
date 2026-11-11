# 优化 3：meta 块写 + 校验前置 + wl_busy 放行 batch 释放（opt3）

基线：`experiments/h1500v/wbank2`（12 层平均 **94,085.67** 拍，1,594.29 层/s）。
本实验：`experiments/h1500v/opt3/rtl`（改 `qingyu_accel.sv`、`qingyu_fio.sv`、`qingyu_accel.c`，
新增 `qingyu_accel.h` 副本，改 `soc_perf_main.c`）。`wbank2/`、`outfifo/`、`experiments/h1500v/rtl/`
逐字节未动。

## 结果（12 层，Verilator 全 SoC，官方 304,128 输出逐位比对）

| 项 | wbank2 | **opt3** | 变化 |
|---|---:|---:|---:|
| 平均周期/层 | 94,085.67 | **77,164.92** | **−16,920.75（−17.98%）** |
| 吞吐（150 MHz 假设） | 1,594.29 层/s | **1,943.89 层/s** | +21.93% |
| 每层 ms | 0.627238 | **0.514433** | −0.112805 |
| 12 层输出 | 304,128 | **304,128 全部逐位一致** | — |
| 逐层周期 | 94,115 / 94,083×11 | **77,109（layer00）/ 77,170×11** | — |
| accel_busy（layer01） | 43,885 | **41,920** | −1,965 |
| producer_stall `full_wait` | 1,965 | **0** | −1,965 |
| fio_cmd_wait（layer01） | 2,925 | **531** | −2,394 |
| driver_cycles（layer01） | 65,554 | **53,066** | −12,488 |
| 共享 SRAM 读次数（layer01） | 24,576 | **23,872** | −704 |

`start_cycle` 从 4,654 变成 9,077 是 ② 造成的：全量校验仍在，但挪到了首个 staging 读之前
（`load_cycles=24,148` 不变，说明 staging 装载本身一字未少）。

证据：`build/opt3/result.json`、`build/opt3/layerNN/sim.log`
（含 `PASS real E203 ... 25344 outputs`、`QINGYU_WEIGHT_TRANSFER commands=16 reads=8192 writes=8192`）。

## 三项贡献（12 层实测，累积式，每次只改一个变量）

| 轮次 | 配置 | 平均周期 | 增量 | 层/s |
|---|---|---:|---:|---:|
| 基线 | wbank2 | 94,085.67 | — | 1,594.29 |
| R0 | ① meta 块写 | 84,287.17 | **−9,798.50** | 1,779.63 |
| R3 | ①+② 校验前置 | 79,747.42 | **−4,539.75** | 1,880.94 |
| R2/R4 | ①+②+③ 放行释放 | **77,164.92** | **−2,582.50** | **1,943.89** |

交叉验证（另外两组 A/B，用来确认贡献不是顺序耦合的假象）：

| 对比 | 配置差 | 平均周期差 |
|---|---|---:|
| R0 → R1 | 只加 ③（无 ②） | 84,287.17 → 81,635.92 = **−2,651.25** |
| R1 → R2 | 只加 ②（有 ③） | 81,635.92 → 77,164.92 = **−4,471.00** |

三组独立测量互相吻合（② ≈ 4.5k、③ ≈ 2.6k），且 9,798.50+4,539.75+2,582.50 = 16,920.75
正好等于总差值。证据：`build/opt3/rounds/r{0,1,2,3}/result.json` 与同名 `layer*.sim.log`。

## 设计

### ① meta 块写（FIO gather，−9,798 拍/层）

基线每 tile 由 CPU 写 16 lane × 2 个 32-bit 字（`QINGYU_META_OFFSET+lane*8`），
每 lane 还要 2 次 64-bit bias 读 + 1 次 shift 读；outfifo 报告按 32 次 MMIO × 19.4 拍
估算 9,920 拍/层，本次实测 ① 的净贡献是 9,798.5 拍/层。

本实现：**每层 2 条配置命令 + 每 tile 1 条命令**，共享 SRAM 一个字节都不额外打包。

- `0xf00000a4` = 本层 shift 基址（`job->shift`），`0xf00000a8` = 本层 bias 基址（`job->bias`），每层各 1 次；
- `0xf00000a0` = 本 tile 的列基址（0,16,…,240），每 tile 1 次；
- FIO 新增 meta gather 引擎：按 tile 从共享 SRAM 读 4 个 shift 字 + 32 个 bias 字，
  按 `lane*4+segment` 顺序把 4 个 16-bit 段（bias[15:0]、bias[31:16]、bias[47:32]、{8'b0,shift}）
  写进 accel 的 128×16 metadata RAM（新增 16-bit 块写口，与原有 MMIO 写口复用同一 RAM，不新增宏）；
- **时序语义不变**：tile0 的 meta 必须在 START 之前写完；tile n+1 的 gather 在 START(n) 之后发出，
  在 tile n 计算期间搬完，`meta_busy` 会挡住 START(n+1)，因此"meta 写完 START 才生效"。
  gather 只在 accel 的 `E_META_REQ/E_META_CAP` 之外写 RAM（`meta_read_phase` 握手），
  单口 metadata RAM 不需要双体；
- 非 direct（回调式）或指针不对齐时，驱动自动退回原来的逐 lane MMIO 写，功能语义不变。

旁证（layer01 窗口内共享 SRAM 读次数）：最终 23,872 = 11,936 staging + 3,168 输入 + 8,192 权重
+ **576**（16 tile × 36 个 gather 字），即 meta 通路对共享 SRAM 只增加了 576 次读/层，
而 CPU 原来每层要在窗口内读 768 次 bias/shift（逐列校验）+ 每 tile 48 次 meta 读。

### ② validate_job 前置（−4,540 拍/层）

`validate_job` 对 256 列 bias/shift 的逐列检查约 4,446 拍，且每层只跑一次、job 参数每层不同，
无法"缓存命中"。按题目允许的兜底做法：新增 `qingyu_validate()`（完整执行 validate_device+validate_job）
和 `qingyu_run_prepared()`（保留全部运行时检查，只跳过已证明过的逐列校验）。
性能固件在 **staging 装载之前**调用一次 `qingyu_validate()`，因此全量校验仍然执行，
只是不再落在"首个 staging 读 → 最后一个输出写"的计时窗口内。`qingyu_run()` 的语义完全不变（仍全量校验）。

### ③ wl_busy 放行 batch 释放写（−2,583 拍/层）

基线 `icb_cmd_ready` 非 block 分支为 `(!wl_busy || icb_cmd_read)`，权重预取 512 字期间
CPU 的 batch 释放写（`0x20/0x24`，写值 1）被挡住，accel 在 `E_ROW_INIT` 等 release，
产生 `producer_stall`。放行条件改为只认"释放写"这一种 accel 写：

```verilog
wire batch_release_cmd=!icb_cmd_read && icb_cmd_wmask==4'hf && icb_cmd_wdata==32'd1 &&
                       (icb_cmd_addr==32'hf0000020 || icb_cmd_addr==32'hf0000024);
wire accel_cmd_ok=(!wl_busy || icb_cmd_read || batch_release_cmd) && (!meta_busy || !start_cmd);
```

START / TILE_BASE / 权重 MMIO 等会破坏权重流的写仍然被 `wl_busy` 挡住（不会重现 wbank2 的
`.icb_cmd_valid` 不同步屏蔽死锁：`icb_cmd_ready` 和送到 accel 的 `icb_cmd_valid` 用的是同一个 `accel_cmd_ok`）。

## 与题目建议实现的差异（重要）

**① 没有让 CPU 每层打包 512 个 32-bit 字到 SRAM 临时缓冲区**，而是让 FIO 直接按 tile gather。
原因（实测，`experiments/h1500v/opt3/probe/`）：

| CPU 访问模式（256 列） | 实测拍数 |
|---|---:|
| 512 次 32-bit 共享 SRAM store | 3,085 |
| 512 次 32-bit 共享 SRAM load | 5,259 |
| **完整打包（512 load + 256 byte load + 512 store）** | **8,202** |
| 现有逐列校验循环 | 4,446 |

即：基线 meta 的全部开销只有约 9,920 拍，CPU 打包一遍就要 8,202 拍，
按字面实现净收益只剩 ~1.5k，无法达到 −8~9k 的目标。FIO gather 每 tile 只多 36 次共享 SRAM 读，
gather 完全藏在 tile 计算里，窗口内每个 tile 只多 1 条 MMIO 命令（约 6 拍）。
接口约束仍然满足：每层一次性配置、每 tile 一条命令、FIO 从共享 SRAM 读 meta 写 accel、
写完 START 才生效、非 direct 路径回退到原实现。

**②** 采用题目明确允许的"把可提前的检查移出计时窗口之外"兜底，并在固件里显式调用 `qingyu_validate()`，
检查一条不少；窗口定义本身没有改。

## 证据

| 内容 | 路径 |
|---|---|
| 最终 12 层结果（①②③） | `build/opt3/result.json`、`build/opt3/layerNN/sim.log`、快照 `build/opt3/rounds/r4/` |
| 分项：① / ①+③ / ①② / ①②③ | `build/opt3/rounds/r0`、`r1`、`r3`、`r2` |
| 基线复现（94,085.67） | `build/opt3_baseline_console.log`、`build/wbank2/result.json` |
| meta gather 单元测试（16 tile × 64 字 + START 交叠） | `experiments/h1500v/opt3/probe/tb_meta.sv`（Icarus，PASS 1024 字 + 512 lane） |
| CPU 访问代价探针 | `experiments/h1500v/opt3/probe/probe_main.c`、`build/opt3/ccprobe/` |

## 复现

```powershell
python experiments/h1500v/opt3/measure_opt3.py --layers all --check-weight   # 全量重建 + 12 层
python experiments/h1500v/opt3/measure_opt3.py --layers all --skip-build `
       --main experiments/h1500v/wbank2/rtl/soc_perf_main.c                  # 去掉 ② 的对照
python experiments/h1500v/opt3/probe/probe_run.py 1 0,1,2,3,8                # CPU 访问代价
```

## 限制与风险

1. **面积/时序/Formality/能耗未重跑**。新增逻辑只有 FIO 的 meta gather 状态机（约 10 个触发器 +
   3 个 32-bit 寄存器 + 地址加法/比较）和 accel 侧一个 16-bit 写口 mux，**不新增 SRAM 宏**
   （metadata RAM 仍是原来的 128×16 单口宏），远低于 10k µm² 预算，但没有签核数字。
2. meta gather 与 accel 的 metadata 读共用单口 RAM，靠 `meta_read_phase` 互锁；已用独立
   Icarus TB 覆盖"START 与下一 tile gather 交叠"的场景，并用 12 层 304,128 输出逐位一致兜底。
3. 官方 150 MHz 时序、服务器 VCS/DC 流程都没跑；本报告只有 Verilator 功能/周期证据。
4. 旧的主机驱动单测 `tb/test_driver.c` 是按 4 lane 基线写的，wbank2 驱动同样在
   `weight_words==128` 处断言失败（**既有问题，不是本次回归**）；opt3 驱动与 wbank2 表现一致。
5. 剩余瓶颈（layer01 = 77,170）：staging 装载 24,148（31%）、输出搬运约 25,773（33%）、
   输入拷贝 6,354、MAC 41,920（其中已无 producer_stall）。下一步收益要动 staging/输出通路，
   不在本批范围。
