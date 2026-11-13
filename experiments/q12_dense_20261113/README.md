# Q12 完整矩阵写回与面积优化

依据《赛题问题答复》第 11 条移除输出 Rice 压缩。当前目录属于实验候选，最终评测尚未完成，原冻结目录保持原样。

逐条要求、已修正项及未闭合事项见 `COMPLIANCE.md`。

约束：原有 System Bus、32 位接口、单一共享 SRAM 入口；输入和权重实际装载计时；全部 99×256 输出值写回后才报告完成；同一冻结候选测吞吐、面积和能耗。目标吞吐不低于 6000 tasks/s，优先保持 6022.40334；新增面积不超过第二版实际综合值 0.448646862835 mm²。150 MHz 必须由同版时序证明。

## 当前实验候选

本轮最新候选为 `candidates/native12_earlycheck/`：断开输出错误检查的 ready/abort 组合反馈，完整 signed12 输出保持不变。厂家 12 任务测得 **6075.99 tasks/s、0.388582 mm²**；12 窗口整机功耗工程估计 **58.36 mW、9.60 µJ/任务**。DC 已报告路径 setup/hold 为 **0 / +0.00070456 ns**，但继承外设未约束端点、严格功耗和独立等价审计、正式精度及 loader 接口验收尚未全部闭合。不可标记为最终合格提交。详细证据见 `PROGRESS.md` 与 `report_2h_20261113/`。

可审阅源码及身份在 `candidates/native12/`，状态为 **EXPERIMENTAL_NOT_PROMOTED**。采用 X12/W10/Y12：原权重和偏置分别做除以 4 的最近偶数舍入，权重饱和至 signed10，输出移位取原移位减 1，结果饱和至 signed12。输出物理尺度为原 Y13 尺度的两倍。没有训练、微调、模型结构变更或针对测试样本拟合参数。不能沿用旧版精度分数；正式 600 样本尚未验证。

完整输出采用固定下标的 signed12 数值数组。16 个 tile，每个 tile 为 99×16 个元素、594 个 32 位字；每个值始终占 12 位，与数值大小和零值数量无关，不做差分或变长编码。第 0 字为 `0x32443151` 完成标志，第 1～16 字为 19008，随后是 16 个 tile。共 9521 字存储，任务共写 9522 字（包括开始时标志失效及结束时提交）。任意矩阵元素可直接按固定比特下标读取，无需压缩解码器。

DMA 只在自己的读写请求之间优先提交已准备的输出写请求，以减少计算结果反压。保留已提出命令的载荷、在途响应归属、错误排空和原 System Bus；不增加 SRAM 访问口或修改下游官方总线。

本地 12 个合成数据完整 E203 任务通过，304128 个输出值及真实总线事务检查通过。原生 12 位输出模块通过随机反压、连续吞吐、复位和非法结束检查；舍入函数通过 2^40 输入组合证明；k6/k7 解码器通过 416 组正常/变异逐周期对照。以上不代表正式数据吞吐、面积或时序通过。服务器实际结果见 `PROGRESS.md`，尚未测出的项目保持空值。

`candidates/native12_compact/` 进一步将私有 W10 权重存储字宽从 384 位降至 320 位，预计减少 4 个 RAMSP128X16，完整宏数由 30/6/80 改为 26/6/80。12 项本地完整任务的输出和周期逐项不变；存储字组合等价与非法输入拒绝检查通过。其面积、能耗及正式时序必须单独测量，不能从宏数直接推断最终成绩。

`candidates/native12_c25/` 再把列修正项与偏置预先合并为 signed25 的 C-bias，元数据从 64 位减至 32 位，预计另减 2 个 RAMSP128X16，同时移除输出路径的一次加法。合法范围的算术等价证明及 12 项本地整机任务通过，输出和周期均不变；服务器 PPA 单独评测。

复跑示例（WSL/Linux，已安装本项目使用的 Verilator、Icarus、Yosys 和 RISC-V GCC）：

```sh
python3 experiments/q12_dense_20261113/check_writer.py --native12
python3 experiments/q12_dense_20261113/run_local.py --cases 12 --storage-bits 12 --weight-bits 10 --write-priority
python3 experiments/q12_dense_20261113/check_requant12.py
python3 experiments/q12_dense_20261113/check_decoder_k7.py
python3 experiments/q12_dense_20261113/server/check_package.py
python3 experiments/q12_dense_20261113/server/package_native.py
python3 experiments/q12_dense_20261113/server/make_full.py
python3 experiments/q12_dense_20261113/run_local.py --cases 12 --storage-bits 12 --weight-bits 10 --write-priority --compact-weights
python3 experiments/q12_dense_20261113/check_compact_weights.py
python3 experiments/q12_dense_20261113/server/package_compact.py
python3 experiments/q12_dense_20261113/server/make_compact_full.py
python3 experiments/q12_dense_20261113/check_compact_metadata.py
python3 experiments/q12_dense_20261113/run_local.py --cases 12 --storage-bits 12 --weight-bits 10 --write-priority --compact-weights --compact-metadata
python3 experiments/q12_dense_20261113/check_compact_weights.py --metadata
python3 experiments/q12_dense_20261113/server/package_compact.py --metadata
python3 experiments/q12_dense_20261113/server/make_compact_full.py --metadata
```

服务器脚本在 `/tmp` 新目录复制哈希匹配的原始包，重新生成私有输入和参考值，并明确保留来源身份。完整评测只接受源码和转换脚本均匹配的新候选：厂家仿真、真实窗口 SAIF、整机官方 TT 库综合、Formality、同版 PT PX。服务器标准库输入转换不依赖 NumPy；官方 PDK、数据、凭据及活动文件不进入公开仓库。启动命令不是评测通过，综合完成也不等于时序通过。

## 初始 16 位槽对照

该对照保持原 X12/W12/Y13 数值，已经排除为最终选择：仅真实输入装载和回读、完整输出写回的理论下界就达到平均 28202.67 周期，超过 6000 tasks/s 所需的 25000 周期预算。

输出格式：基址第 0 字是完成标志 `0x31443151`，第 1～16 字各为固定值 25344，表示每个 tile 的存储位数。随后按 tile、row、column 顺序存储全部结果，每个 tile 为 99×16，16 个 tile 覆盖 256 列。每个有符号 13 位结果符号扩展为独立的 16 位槽，每个 32 位总线字保存两个值，先出现的值占低 16 位。没有差分、Rice、变长编码或零值省略，读取只需要固定下标映射。矩阵为 50688 字节；含标志和头部共 50756 字节。计时包括全部写入和最终完成标志的响应 ACK。

`prepare.py` 仅生成此 16 位槽历史对照及其 `identity.json`；当前候选由 `run_local.py` 派生并由 `freeze_selected.py` 保存。所有 TB 保留加载/读写事务守恒、原总线路由、边界守护、完整 SRAM 读回以及起止计时检查。
