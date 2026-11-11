# H1500v 最终签核结果（官方库 SCC40NLL RVT，2026-11-08）

冻结候选：`qingyu_h1500v`（相对 h1500：输出 SRAM bank 16→8、换更省面积的舍入器）。
标准单元库：平台 `SMIC40_2025/S40.tar.gz` 中的 **SCC40NLL_VHSC40_RVT_V0p1**（basic / NLDM，5 个角）。
SRAM 宏：平台 `SRAM_Lib_2025`（RAMSP128X16 / 1024X16 / 4096X16）。
SoC 基线：平台 `SOC_RTL_2025` 的 `e203_hbirdv2-master_1013_update_sim.zip`（`e203_defines.v` 哈希已核对）。

本文件只记录结果与证据位置，不替代 `reports/` 下的原始报告。

## 结果总表（官方库）

| 项 | 数值 | 证据 |
|---|---|---|
| 功能（12 层，服务器 VCS + 厂商 SRAM 模型） | 304,128 个输出一致 | `qingyu_h1500v_MIkhor/layer*.log` |
| 吞吐 | **1,504.8481 层/s**（0.664519 ms/层） | 同上 |
| **面积（赛题口径：加速器+FIO+33 私有宏）** | **344,521.855 µm² = 0.344522 mm²** | 三轮 ECO 后 `qingyu_h1500v_hold3_jcN9MG/repair/ff_125c/area.rpt` |
| 五角 STA（三轮 ECO 后） | setup 最紧 **+0.268054 ns**（ss_m40c）；hold 最紧 **+0.030510 ns**（ff_m40c） | `qingyu_h1500v_hold3_jcN9MG/summary.txt` |
| Formality（RTL ↔ 四份 SVF 网表） | **8,825 比较点，0 failing / 0 unmatched / 0 unverified** | `qingyu_formality_h1500vo_rmzCHu/reports/` |
| 整机综合（TT，功耗口径） | 2,700,406.989 µm²（宏 2,341,499.783） | `qingyu_h1500v_soc_XqFVPn/reports/area.rpt` |
| **单任务能耗（12 层平均）** | **21.9878 µJ** | `qingyu_h1500v_energy_q0dAmy/energy_summary.json` |
| 时间加权功耗 | 33.0917 mW | 同上 |
| 活动标注覆盖率 | 宏输出 1808/1808（100%） | `.../layers/layer00/supplement.log` |

12 层逐层能耗（µJ）：22.059、22.259、21.993、21.794、21.927、21.993、21.861、21.927、
21.927、22.060、21.927、22.126；对应周期 99,676 / 99,678。

## 五角明细（三轮 ECO 后）

| 角 | setup (ns) | hold (ns) |
|---|---:|---:|
| tt_25c | +2.77659 | +0.0532199 |
| ss_125c | +0.702176 | +0.0927502 |
| ss_m40c | +0.268054 | +0.0921042 |
| ff_125c | +3.72787 | +0.0305396 |
| ff_m40c | +3.83657 | +0.03051 |

三轮 ECO：第一轮按 ss_m40c（tt/ff 仍有 −0.017～−0.037），第二轮按 ff_m40c（ff_125c 剩 −0.0026），
第三轮按 ff_125c 后五角全正。面积三轮共增加 538 µm²（343,983.68 → 344,521.85）。

## 与历史版本对比

| 版本 | 库 | 吞吐（层/s） | 能耗（µJ/任务） | 面积（mm²） | 五角 | Formal |
|---|---|---:|---:|---:|---|---|
| G | sc9mc | 773.78 | 32.04 | 0.202653 | ✅ | ✅ |
| H | sc9mc | 805.70 | 31.25 | 0.20287 | ✅ | ✅ |
| H1500v（参考） | sc9mc（非官方 PDK） | 1,504.85 | 21.08 | 0.307651 | ✅ | ✅ |
| **H1500v（提交）** | **SCC40NLL RVT** | **1,504.85** | **21.99** | **0.344522** | ✅ | ✅ |

- 相对 H：吞吐 +86.8%，能耗 −29.6%，面积 +69.8%（2.25 上限的 15.3%）；
- 相对 G：吞吐 +94.5%，能耗 −31.4%；
- 能耗×延迟：H 38.8 → H1500v 14.6 µJ·ms，约 2.7 倍改善。

## 口径与限制（写报告必须带上）

1. 能耗是「服务器 EDA 活动功耗分析」（VCS SAIF + PrimeTime PX），**不是芯片实测**；
2. 只做 **TT 1.10 V 25 ℃** 功耗角，没有 ss/ff 功耗；
3. 综合后、pre-layout：理想时钟、线负载模型，不含布线/时钟树/IO pad/PLL 模拟部分；
4. 时序与等价只签到 **FIO 级**（`qingyu_fio`）；整机只在 TT 下做过映射与功能验证；
5. Formality 有 3 个 constant register 未比较；
6. 面积口径 = 加速器 + FIO + 33 私有宏，**不含**复用的 E203、512 KiB 共享 SRAM、总线与外设（赛题规定）；
7. 整机面积 2.700 mm² 仅用于功耗分析，不是评分面积。

## 证据目录（服务器 `~/Desktop/`）

| 阶段 | 目录 |
|---|---|
| VCS 12 层 + DC 面积 + 五角 + Formal（映射后） | `qingyu_h1500v_MIkhor` |
| hold ECO 第 1 轮（ss_m40c） | `qingyu_h1500v_hold_H24ej8` |
| hold ECO 第 2 轮（ff_m40c） | `qingyu_h1500v_hold2_RvCXXe` |
| hold ECO 第 3 轮（ff_125c）+ 最终五角 | `qingyu_h1500v_hold3_jcN9MG` |
| 最终 Formality（四份 SVF） | `qingyu_formality_h1500vo_rmzCHu` |
| 整机综合 | `qingyu_h1500v_soc_XqFVPn` |
| 12 层能耗 | `qingyu_h1500v_energy_q0dAmy` |

## 待办

- `reports/version_selection.json`（as_of 2026-11-04，只列 C/E/F）需按本结果更新；
- `reports/project_manifest.json` 冻结在 11-02，重新冻结需明确同意；
- `README.md`、`docs/设计与验证报告.md` 仍描述 4 通道基线与 11-02 数字，需同步；
- 本地 `qingyu/local_pdk` 的 sc9mc 库为非官方 PDK，仅作历史参考，不再用于提交数据。
