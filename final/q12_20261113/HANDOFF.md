# 轻语 Q12 最终候选交接（2026-11-13）

用户已要求停止优化，以当前通过功能回归的版本完成最终评测。后续只收集与审查结果，不修改 RTL、固件或量化配置；发现失败须保留证据并报告。本文是工程交接，不是比赛技术报告或签核结论。

## 1. 当前唯一候选

- 候选 ID：`q12_final_20261113_decoder2_boundedencoder_coredatareset_blockingWAIT_NP3`。
- **Q12 是当前 INT12 方案，不是历史 `opt12_wait`**。保留 bounded encoder、decoder2、rowpair、core data reset、blocking WAIT、真实 E203 与 NP3 loader。
- 数值配置：X12 / W12 / Y13，输出留 1 位余量；具体逐层冻结配置及哈希见 `freeze/precision_audit.json`。
- 冻结清单：`freeze_manifest.json`，158 个选定源文件全部核对一致。不要重写旧 `qingyu/reports/project_manifest.json`。
- 唯一本地基准证据：`output/eda/q12_candidate/loader_master/soc_runner/runs/20261112T161939623706Z/result.json`。
- 该证据 SHA256：`07bc11f0d6301a7570979e70aca022f54845c8bab6468eae58f10ba94aa3a80e`。
- 冻结清单 SHA256：`64ed87a6ad35274828db4eccac79134e94548e99cb7aa3064ad8fd8d99290ea6`。

旧 README、旧 HANDOFF 及历史 opt12/INT8 结果不能代表这个候选。冻结材料的 Windows 绝对路径用于标识原始来源；换机器时以相对源码布局和 SHA256 核对，不盲目沿用盘符。

## 2. 最新证据与边界

| 指标/检查 | 已核实证据 | 限定 |
|---|---|---|
| 本地完整任务吞吐 | 12 层平均 24,907 周期，按 150 MHz 折算 **6,022.4033 层/s**、**0.1660467 ms/层** | 行为 SRAM 仿真，150 MHz 尚未完成最终时序证明 |
| 输出正确性 | 本地 12 个冷启动任务、304,128 个输出核对通过；服务器厂家 SRAM 12 层也已见通过日志，周期与本地一致 | 每任务单独全局复位，不是不中断的完整 encoder 串行运行 |
| 精度 | 历史本地 256 样本 × 12 层；最差逐层 pooled NRMSE **0.12079373%**，最大单任务 **0.15195562%** | 既有记录重汇总，不是组委会 600 样本盲测；探索位宽时已看过这组验证数据，不是新留出集 |
| 面积 | **最终新增面积尚未出具** | 之前约 0.48 mm²（0.45–0.52）只是预算；用户希望 ≤0.5 mm²，尚不能宣布满足 |
| 功耗、能耗 | **当前冻结整机最终结果尚未出具** | 后续是 VCS 活动 + PT PX 的 EDA 分析，不能写成硅片实测；不得套用历史 opt12 数字 |
| 时序、Formality | 当前整机综合/诊断任务已启动，最终结论待取 | 不把仿真周期或模块级通过写成整机 150 MHz 签核 |

完整任务从最早控制/源数据命令提出开始，到最终输出完成标志的真实响应 ACK 结束，包含源数据装载、CPU 调度、仲裁、等待、计算和写回；排除主机文件读取/格式转换以及固件预装、启动。功耗积分使用 SAIF 中精确 ps 起止时刻，不用含首尾拍的周期数替代时间差。

## 3. 总线、存储与赛题待确认项

当前源数据及结果通过官方 E203 下游总线结构和单一逻辑 512 KB 共享 SRAM 入口访问，没有沿用历史六口共享 SRAM 旁路。新增 NP3 仲裁和 shared read-ahead 控制属于自定义硬件，必须计入新增面积。

**严格接口合规仍为 OPEN**：新增公开 `loader_*` 入口能否认定为赛题允许的“平台已有访问接口”，尚无组委会确认。仅证明经过系统总线不足以替代这项确认。详见 `freeze/compliance_limits.json`。

全 SoC 宏清单：30 × RAMSP128X16、6 × RAMSP1024X16、80 × RAMSP4096X16，共 116 个。后者分为固定共享 SRAM 64 个和 CPU TCM 16 个；私有宏为前两类 36 个。

新增面积计入 FIO、计算核心、编解码器、私有 SRAM、传输/邮箱、NP3、共享存储新增缓存及 bank 控制；只在真实边界排除固定共享物理宏、CPU/TCM 和原有平台。最终必须核对实际 leaf cell 求和和库面积单位，避免遗漏或重复相加。

## 4. 服务器现场与继续方式

最后核实状态来自 2026-11-13 上午的服务器终端，不代表持续在线监控：

- Desktop 所在 `/storage2` 曾报 `ENOSPC`，改用私有目录 **`/tmp/q12_final_s4_36usr_20261113`**；当时 `/tmp` 所在本地盘约剩 498 GB。没有删除历史数据。
- 厂家仿真 launcher PID：**245224**，日志：`/tmp/q12_final_s4_36usr_20261113/vendor.log`。12 层功能已完成，随后在转换逐层 SAIF；尚未核实全部活动转换完成标志。
- 整机综合 launcher PID：**250896**，日志：`/tmp/q12_final_s4_36usr_20261113/assessment.log`。已执行 `--phase synth --work-root /tmp/q12_final_s4_36usr_20261113`；实际 DC 当前阶段须读取日志确认。
- `server_progress.json` 已按观察到的启动输出补记综合 PID；这不是实时进程状态。接手时先读现有日志，避免再次启动综合。

先在服务器执行只读检查（登录 shell 为 tcsh，重定向命令用 `sh -c` 包裹）：

```sh
sh -c 'r=/tmp/q12_final_s4_36usr_20261113; tail -n 15 "$r/vendor.log"; tail -n 20 "$r/assessment.log"; find "$r" -path "*/synth/dc.log" -exec tail -n 10 {} \;'
```

实际目录从日志取：厂家任务前缀 `qingyu_q12_final_vendor_*`；综合任务前缀 `qingyu_q12_final_assessment_*`。不要只取“最新目录”或依赖旧 PID 判断是哪一候选。

确认厂家 `result.json` 的全部 12 层 SAIF 成功、综合阶段已完成并保存映射输出后，使用这两个**已经存在的实际目录**继续：

```sh
python3 /tmp/q12_final_s4_36usr_20261113/q12_final_assessment/run_assessment.py --phase post --run-dir "$ASSESSMENT_RUN" --vendor-run "$VENDOR_RUN" --layers 12
```

`ASSESSMENT_RUN`、`VENDOR_RUN` 须先在 `sh` 中设为实际完整路径。`post` 执行 Formality 和同一网表的 12 层 PT PX；可以分别使用 `--phase formal`、`--phase power`，但不得跳过输入哈希、单位或覆盖检查。完成后保存每层原始报告及汇总，及时把小型证据归档到持久存储；`/tmp` 不应作为唯一长期备份。

本次综合用官方 SCC40NLL RVT TT 1.10 V 25 ℃ 与对应 SRAM DB，`compile -map_effort medium`，保存网表/DDC/SDC/SVF。TT、工程 I/O/uncertainty、pre-CTS 理想时钟条件只提供诊断；不代表五角或布局布线后签核。遇到负 slack 或覆盖缺口按实际报告，不做新的设计优化。

## 5. 评测包身份与分发

| 包 | 字节数 | SHA256 |
|---|---:|---|
| `q12_final_vendor.zip` | 2,824,209 | `e0353a0765a9df551f66bdbaf76e562e9aabd0cb3423b24b1bab73b738329ae3` |
| `q12_final_assessment_20261113T011845048986Z.zip` | 552,011 | `e3abe55c2f74d2a0931201dd0c996f0cff51fcdda132e3ded238934d7bd91dc8` |

只使用表中第二个综合包；同目录更早的 545,447 字节草稿不是当前版本。评测脚本说明见 `assessment/README.md`。本地已检查 157 个硬件文件与厂家包的顺序/哈希一致，以及解析器、错误拒绝、Python 3.6 兼容性；这些不替代服务器 EDA。

GitHub 仅保存允许分发的源码、评测脚本、哈希及小型摘要。**不要上传 PDK/厂家模型、私有数据集或其派生向量、密钥、工具链、VCD/SAIF、编译缓存。厂家 vendor ZIP 含测试夹具，不能直接作为公开源码附件。** 空目录不需要占位上传。重新运行需要从授权本地/服务器补齐相应私有输入，并按清单核对，不能宣称公开仓库独立包含完整数据。

## 6. 收尾顺序与时间预算

1. 收取厂家 12 层最终功能/活动汇总，核对和冻结证据一致。
2. 收取新增面积、完整 SoC 面积与时序覆盖；保留失败路径。
3. 对同一映射网表完成 Formality，再逐层做完整窗口功耗/能耗及活动覆盖审查。
4. 汇总实测仿真、EDA 分析、估算和未测项；仍未解决的接口合规、150 MHz 多角时序、官方 600 样本精度明确列出。

此前给用户的总预算是成功启动后约 **2–4 小时**，不是完成承诺；综合许可/收敛、Formality 和活动覆盖可能延长。综合默认超时 3 小时。不要为了汇总重复启动任务或重新优化设计。
