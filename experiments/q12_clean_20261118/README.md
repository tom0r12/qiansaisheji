# q12_clean_20261118 — 去可疑点后的 Q12 GPIO 候选（本地实验目录）

本目录是 2026-11-18 新建的实验，不修改任何旧冻结证据（q12_final / q12_gpio_burst 等保持原样）。
基线 `base/` 是 `q12_gpio_burst_20261113/runs/20261113T101242124243Z` 的源码快照；`variants/` 中只放覆盖文件。

## 去除的可疑点（相对 q12_gpio_burst）
1. 输入/权重 Rice/差分无损编码 → 固定宽度连续打包（`q12_fixed12_reader.sv`；X signed12，8 值/3 字；
   候选 B 的 W 为 signed10，16 值/5 字）。没有数据相关的字段长度，也没有预测/差分。
2. 共享 SRAM 相邻字预取 readcache → 普通单口同步 SRAM 控制器（`qingyu_shared_ctrl`）：每次架构访问对应恰好一次宏访问；
   写在接收周期提交并在同周期应答（单口 SRAM 写在该时钟沿完成），读延迟 1 拍；cmd_ready 只取决于本地状态。
3. 新增 loader / mailbox / 输出压缩：早已移除（沿用 GPIO 版）；输出仍是 99×256 行优先的完整 Y13 INT16 矩阵。

## 为恢复吞吐所做的合规改动
- GPIO DMA：突发长度上限 64 字（GPIOB[9:2] 计数，GPIOB[1] 翻转请求），上一突发最后一次读发出后立即发出下一次请求；
  16 项 FIFO，溢出时报错；已发出的命令绝不撤回。数据仍经原 GPIOA 同步器/APB 读出，再经原 32 位 System Bus 写入共享 SRAM。
- 引擎按字跟随已应答前缀读取：描述符通过范围检查即可放行，transport 逐字检查读地址是否小于已发布前缀的末尾。
- 硬件前缀发布（v3 起）：输入 DMA 的“已收到写响应”计数直接作为引擎可读前缀，CPU 只负责配置、启动，然后阻塞等待完成。
- PPI 仲裁：输入 DMA 在一次复制期间独占外设总线（CPU 在复制期间不访问外设）。

## 本地结果（Verilator，真实 E203 RTL，12 冷任务，304128 值逐值核对）
| 版本 | 周期/层 | 层/s@150MHz |
|---|---|---|
| v0_base（复现旧版） | 40574.33 | 3696.92 |
| v3_hwpub（候选 A，X12/W12/Y13） | 44166 | 3396.28 |
| v4b_w10c（候选 B，X12/W10/Y13，W 私有 SRAM 由 24 颗减到 20 颗） | 41278 | 3633.90 |

本地 600 条测试样本（按评分口径逐层汇总取最大）：W12 0.1211%，W10 0.2349%（`precision_w10.json`）。

## 验证
- 全部 72 个冻结夹具（12 层 × 6 样本，共 1824768 个输出）逐值通过：A 和 B 均如此。固定宽度格式下每任务周期与数据无关，A 恒为 44166、B 恒为 41278。
- `unit/tb_dma2.sv`：GPIO DMA 四种模式全部通过——正常、长突发、存储错误、外设错误、节奏丢失、忙中改配置被拒、复位后重启。
- `unit/tb_reader.sv`：固定宽度读取器在 X12/W10/W12 三种模式下全部通过——随机输入间隙、输出反压、last 标志、非法配置、提前 last。
- GPIO 时序角：周期 26.614/26.714 ns × 首字 0.5/3.0 ns，在 64 字突发下全部通过。
- 服务器包（`server/`）：已在本地用行为替身 SRAM 跑通厂家测试台（ASIC 封装、物理回读）；这不是厂家模型结果。

## 限制
- 150 MHz 只用于周期折算；面积、时序、Formality、功耗/能耗尚未得到服务器结果。
- 本地数据是 12 个历史任务和本地 600 条测试样本，不是组委会选定的样本。
- GPIO 外部源的固定节奏契约（26.664 ns/字）需要在报告中声明。

## 合规审计（compliance_audit.py，2026-11-18 06:37）
- A、B 均通过：135 个与上游 E203 同名的源文件逐字节一致（含 e203_subsys_mems、sirv_icb1to8_bus、外设、APB GPIO、CPU）；改动只在项目自有文件和 3 个集成文件里。
- 源码中不再有 Rice/readcache/loader/mailbox/输出压缩模块；共享 SRAM 只有一个实例，只接原 sysmem_icb，其他模块不直接访问；位宽 32。
- 原存储总线保持 SPLT_FIFO_OUTS_NUM=1，其拆分器为 ALLOW_0CYCL_RSP=1（原平台支持零周期响应）。
- 运行时证据：72 个夹具的测试台账逐笔核对——每个总线请求都有来源（CPU/计算 DMA/输入 DMA），共享 SRAM 访问都经过原存储总线，每个 GPIO 字都经原 APB 读出。
- 敏感点：若共享 SRAM 写应答强制延迟 1 拍，A 降为 2425 层/s（v3r_regwrite 实验）。

## 2026-11-18 11:20 更新：v5–v8 与服务器结果
| 版本 | 改动 | A 周期/层 | B 周期/层 |
|---|---|---|---|
| v5 | 去掉核心 6 个诊断计数器 | 44166 | 41278 |
| v6 | 主机离线按核心顺序重排，行对缓冲换直通级 | 44129 | 41228 |
| v7 | transport FIFO 8/4、在途 4、GPIO FIFO 8；B 的 W 暂存 320 位 | 44197 | 41258 |
| v8 | 引擎 abort 寄存后再送 transport（消除组合环 datapath_fault→abort_now→soft_abort→wr_word_ready→encoder_in_ready） | 44197 | 41258 |

v8：A/B 72 夹具逐值通过；Verilator UNOPTFLAT 3→0；故障注入（`variants/*_fault`，测试专用 TB 钩子 `patches/fault_tb.py`）坏头字→错误码 02、坏移位元数据→12，与 v7 一致并正常收尾；合规审计通过。

服务器 03（v7，官方 SCC40NLL RVT TT + SRAM_Lib_2025）：
- A：厂家 12 层周期差全 0；增量面积 0.310152 mm²；4 窗口平均能耗 9.074 µJ；Formality 通过。
- B：0.298346 mm²；8.402 µJ；Formality 失败，失败点在 output_packer，由上述组合环引起。
- 时序问题（结果_04～06）及处理：
  - setup −262.8 ns：E203 原版 `inspect_core_clk` 时钟转发到 GPIOA[27]，是伪路径。
  - ITCM −2.94 ns：上面那条伪路径占住了 hfext_clk 组的 WNS，DC 没有去优化这条路径。
  - 两者已在 `server/flow/map.tcl` 中处理：false path（只切这一支）、异步时钟组、`set_fix_hold`，以及仍有违例时的增量编译。
  - 处理后的全流程重跑包为 `q12clean4`（服务器操作 07）。

2026-11-18 13:10 服务器 08 闭合与 09 收尾深审准备（Antigravity /goal 会话）
服务器 08（q12clean5，v8a/v8b，加入 compile -incremental_mapping -only_hold_time）：
- A（v8a，W12，运行目录 /tmp/q12clean_A__31nd3un）：厂家 12 层周期差全 0（44197 拍 = 3393.90 层/s）；增量面积 0.314235 mm2；DC TT setup 全部 MET（core_clk +0.0038 ns，hfext_clk 0.0000 ns），hold 全部 MET（core_clk +0.000346 ns，hfext_clk +0.004173 ns），setup/hold/trans/cap 违例全 0；Formality SUCCEEDED（30974 passing, 0 failing）；4 窗口平均能耗 9.0519 uJ（30.725 mW）。
- B（v8b，W10，运行目录 /tmp/q12clean_B_4z3c40um）：41258 拍 = 3635.66 层/s；增量面积 0.301410 mm2；DC TT setup/hold 全正（+0.0030 / +0.000346 ns），违例全 0；Formality SUCCEEDED（30590 passing, 0 failing）；4 窗口平均能耗 8.4225 uJ（30.625 mW）。
本地补充：v8b 合规审计通过；v8a GPIO 四组时序角（26.614/26.714 ns x 0.5/3.0 ns）通过，40 ns 负例被拦截。
下一步收尾核查（服务器操作 09，output/eda/q12_09_audit.py SHA256=6a0855852eb57a23a33ab9623a63bcef17c73ecebb5439860acd53ca23388a21）：复用 08 目录核查 PT setup/hold、DC loops、FM unverified/blackboxes、面积求和，补齐候选 A 全部 12 层功耗窗口，PT 只读摸底五角 STA（整机与 u_fio），并将 /tmp 报告归档至 ~/Desktop。


## 2026-11-18 16:42 终版全项签核闭环（09～12，v9a / v9b，零跨版本拼接）
详见同目录 `FINAL_SIGNOFF_20261118.md`。
- **v9 改进：** `patches/v9_core_outpipe.py` 将 `q12_task4.sv` 90 级组合输出链切分为两级寄存器；`patches/v9_transport_addr.py` 将 `dma_cmd_addr` 级联加法改为递推寄存器 `rd_next_addr` / `wr_next_addr` / `available_end_o`。
- **主推候选 A（`v9a`，X12/W12/Y13，精度 0.1211%）：**
  - 吞吐：**3,391.36 层/s**（44,230 拍，72 夹具 + 厂家 SRAM 12 层周期差全 0）。
  - 增量面积：**0.316366 mm²**（整机 `synth_eco/mapped.v`，SHA256 `dab44a73…`；独立 `u_fio` **0.314656 mm²**）。
  - 全 12 层平均能耗：**9.1397 µJ**（31.000 mW，9.1103～9.1692 µJ，`Not Annotated = 0.00%`）。
  - 独立 `u_fio` 五角 150 MHz STA：**`tt_25c` / `ss_125c` / `ss_m40c` / `ff_125c` / `ff_m40c` 五角 setup & hold 全正**（最坏 `ss_m40c` setup `+0.000080 ns`，`ff_125c` hold `+0.025025 ns`），`fio_formal` **SUCCEEDED**（14,881 点）。
  - 整机 STA + Formality + 门级仿真：**TT setup 全正**（`core_clk +1.7306 ns`，`hfext_clk 0.0000 ns`），**全部五角 hold 全正**（最坏 `ff_125c` `+0.016796 ns`），`formal_eco` **SUCCEEDED**（31,227 点），TT SDF 门级仿真（`init0` / `init1` / `random` + 131,072 字 `0xcccccccc` SRAM 毒化预装）全部 **PASS**（`full_window_cycles=44230, mismatches=0`）。
- **备选候选 B（`v9b`，X12/W10/Y13，精度 0.2349%）：**
  - **3,634.87 层/s**（41,267 拍）、增量面积 **0.303804 mm²**（`u_fio` **0.302485 mm²**）、4 窗口平均能耗 **8.4931 µJ**；独立 `u_fio` 五角 setup & hold 全正 + 整机 TT setup / 五角 hold 全正 + 双层 Formality **SUCCEEDED**。
- **服务器归档：** `~/Desktop/q12clean6_reports_archive.tar.gz`（SHA256 `c2dd107e158e7496572927de6aaf54a7a8a039c7014962cb12bf4d5999644322`）与 `~/Desktop/q12clean6_12_final_archive.tar.gz`（SHA256 `27f836a1c4f3c29128cb5f12ec459201367c3cd83d06376f0bd655fc63eb32d2`）。
