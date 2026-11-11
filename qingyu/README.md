# 轻语：E203 前馈线性加速器

面向 2026 年嵌入式芯片与系统设计竞赛本科生组的工程实现。
默认计算 `Y[99,256] = X[99,64] @ W[64,256] + b[256]`，4 通道并行，
输入/权重 INT16、偏置/累加 INT48、输出 INT32，支持固定右移、最近偶数舍入和饱和。
E203 负责 64 个输出通道块的调度与数据搬运，数值计算由加速器执行。

当前已验证真实 KWT 权重和语音数据、十二层独立核心、整数参考模型及真实 E203 执行 C 驱动的整层计算。
已完成用户工艺库的标准单元映射，并通过采样的综合前后功能对照。综合流程保留源码状态编码，修正过程和原始失败证据均已记录。
本地验证子集不代表官方 600 条评测集的精度成绩，行为存储模型不代表正式 SRAM 宏。

本地结果：256 条训练校准与 256 条独立验证均覆盖全部 12 类，最差层 NRMSE 为
**0.01564745%**；十二层 RTL 共 **304,128 个输出**逐位一致；真实 E203 对验证集中的
第 11 层任务完成全部 **25,344 个输出**对照。具体来源、版本和测试日志在下述报告中。

## 运行

需要 Python 3.10+ 与 NumPy、Icarus Verilog 12（iverilog/vvp）、主机 GCC。
SoC 固件另需支持 RV32IMAC/ILP32 的 RISC-V GCC。
在本机可使用 Codex 随附的 Python，硬件和 RISC-V 编译工具已经找到。

在本目录执行：

```powershell
# 数值模型、驱动、RTL 快速回归
python scripts/run_checks.py

# 推荐：原生编译仿真，十二层真实验证向量的完整矩阵回归
python scripts/run_soc_verilator.py --rtl-only --all-layers --vectors model/full_v2_run/validation_vectors

# 推荐：真实 E203 固件、共享 SRAM、完整 SoC 与实际语音验证向量联调
python scripts/run_soc_verilator.py --layer 11 --vectors model/full_v2_run/validation_vectors

# 独立的四态 Icarus 全矩阵检查，需要数分钟
python scripts/run_checks.py --full-rtl --layer 0

# Icarus 完整 SoC 流程保留作交叉检查，当前本机速度较慢
python scripts/run_soc.py --build-only

# 仅构建，或指定其他 RISC-V GCC
python scripts/run_soc.py --build-only
python scripts/run_soc.py --gcc '你的工具链路径/riscv-none-embed-gcc.exe'

# 使用本地标准单元库作初步逻辑映射，SRAM 保留为黑盒
python scripts/run_synthesis.py

# 综合网表功能对照：396 个输出，保留实际 PDK 单元模型
python scripts/run_gate_smoke.py
```

如系统 `python` 未安装 NumPy，可设置或直接使用本机随附运行时：

```powershell
& 'C:\Users\zyx316\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/run_checks.py
```

## 目录

| 目录 | 内容 |
|---|---|
| `rtl/` | 可综合加速器、同步存储封装、共享存储功能模型、FIO 接口 |
| `model/` | 整数模型、训练校准/验证转换、模型提取、工程向量 |
| `sw/` | C 驱动、启动汇编、链接脚本、真实 E203 联调固件 |
| `tb/` | RTL 边界/背压测试、驱动测试、SoC 测试、合成向量 |
| `scripts/` | 可复现的构建、测试、综合和 PDK 检查入口 |
| `constraints/` | 150 MHz 目标约束；正式 I/O 条件需明确配置 |
| `reports/` | 验证结果、PDK 清单、初步综合结果 |
| `vendor/` | 固定版本官方 E203 与 KWT 源码 |
| `generated/` | 从官方源码生成的项目适配层及原文件校验值 |
| `local_pdk/` | 私有工艺文件，不加入公开代码分发 |

## 关键接口

加速器内存映射详见 [统一接口约定](docs/engineering_contract.md) 和
[驱动说明](docs/driver.md)。本工程集成地址为：

- ITCM 固件：`0x80000000`，启动适配层明确配置复位向量。
- 512 KiB 共享 SRAM：`0xA0000000..0xA007FFFF`。
- 加速器：`0xF0000000..0xF000FFFF`。
- 仿真完成通知：`0xF0010000`。

这些是基于上游地址分发选择的项目地址，需与最终评测工程核对。
官方 CPU、外设及原始源码保留；适配层生成规则与校验值可审阅。

## 验证范围与剩余验收

| 项目 | 已有工作 | 仍需完成 |
|---|---|---|
| 计算正确性 | 真实 KWT 参数与验证输入的十二层、304,128 个输出逐位匹配 | 官方冻结评测集复核 |
| 数值处理 | 11 项单元检查；训练集冻结尺度、独立验证各层 NRMSE | 保持冻结配置，接受官方评测 |
| 驱动 | RV32 编译、64 块调度、异常恢复及真实 E203 整层对照通过 | 与最终官方参数装载环境核对 |
| 存储 | 规定尺寸的九个封装，合计 21.25 KiB；共享 SRAM 功能模型 | 指定 SRAM 宏的时序、功耗、面积及替换 |
| 综合 | 用户本地 SMIC40 标准单元库逻辑映射，396 个综合网表输出对照通过；逻辑面积约 0.0183605 mm² | 含 SRAM 与接口的正式面积、150 MHz STA 及规定条件功耗 |
| 功耗 | 保留活动信息生成和正式工具流程的接入位置 | 同一冻结版本的完整活动覆盖及功耗/任务能耗 |

不能把在仿真中设置 150 MHz 周期当作时序通过，也不能把标准单元逻辑面积
当作包含全部 SRAM 的加速器总面积。最终评测需要统一输入、冻结配置及规定的计时窗口。

详细资料：[数值格式](docs/numeric_format.md)、[RTL 说明](docs/rtl_design.md)、
[综合流程](docs/synthesis.md)、[来源与贡献记录](docs/source_origins.md)。
综合对照过程见 [综合网表验证说明](docs/gate_verification.md)。
设计、数据及验收范围的集中说明见 [功能版设计与验证报告](docs/设计与验证报告.md)，
并行度实验见 [同条件创新对照](docs/innovation.md)。

完整结果入口：

- [训练校准及独立验证报告](model/full_v2_run/validation_vectors/validation_report.json)
- [十二层 RTL 逐位对照](reports/rtl_verilator_result.json)
- [真实 E203 与 C 驱动整层对照](reports/soc_verilator_result.json)
- [逻辑综合结果](reports/synthesis_summary.json)与[面积单位核对](reports/synthesis_area_units.json)
- [综合前后对照状态](reports/gate_smoke.json)
- [单路/四路同条件对照](reports/parallelism_study.json)
- [项目验证汇总](reports/verification_summary.json)

真实模型的复现使用 `.venv-model/Scripts/python.exe`，版本记录为 TensorFlow 2.14.1 /
Addons 0.22.0 / NumPy 1.26.4；原仓库参考环境为 TensorFlow 2.4.0rc1，这一差异已记录。
完整模型流程可重新生成到新的工作目录，避免覆盖冻结产物：

```powershell
.venv-model/Scripts/python.exe model/run_reference_pipeline.py --repo vendor/keyword-transformer --data-dir data/speech_commands_v0.02 --work model/reproduced_run
```

源码、冻结向量和结果的校验清单位于 `reports/project_manifest.json`。
核对现有基线使用 `python scripts/freeze_manifest.py --check`；修改后需要重新验证，
再有意更新清单，不能把改动后的指标与旧报告混合使用。
