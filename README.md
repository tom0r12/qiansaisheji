# 轻语 · E203 前馈线性加速器

## 2026-11-18 最终合规清理版冻结基线（`q12clean6`：`v9a` 主推 / `v9b` 备选）

本分支（`q12clean6-20261118`，冻结标签 `q12clean6-submission-20261118-r2`）保存已完成全部赛题必测项与额外签核项（150 MHz 五角 STA + 双层 Formality + 整机 TT SDF 反标门级仿真）并正式冻结的双候选工程：

- **冻结签核总报告与校验清单**：[final/q12_clean_submission_20261118/README.md](final/q12_clean_submission_20261118/README.md) · [FROZEN_MANIFEST_20261118.json](final/q12_clean_submission_20261118/FROZEN_MANIFEST_20261118.json)
- **11+12 号冻结服务器包源码（已脱敏私有向量）**：[experiments/q12_clean_20261118/server/snapshot_11_12/README.md](experiments/q12_clean_20261118/server/snapshot_11_12/README.md)
- **服务器 VNC / EDA GUI 实测截图与双候选对比图集**：[截图_13（含 Design Vision & PrimeTime GUI）](final/q12_clean_submission_20261118/screenshots/截图_13/) · [报告截图_v9_AB（10 张分项对比与索引）](final/q12_clean_submission_20261118/screenshots/报告截图_v9_AB/截图索引.md)
- **官方服务器实测原始汇总日志（11~13 号）**：[experiments/q12_clean_20261118/server/signoff_11_12/](experiments/q12_clean_20261118/server/signoff_11_12/)
- **完整迭代与合规自检工程**：[experiments/q12_clean_20261118/README.md](experiments/q12_clean_20261118/README.md)

| 实测指标（同冻结配置、零跨版本拼接） | 赛题/目标门槛 | 候选 A（`v9a`，W12 默认主推） | 候选 B（`v9b`，W10 高吞吐备选） |
|---|---:|---:|---:|
| 合规自检（135 份上游 E203 零改动、零熵编码、零共享读缓存、原平台 GPIO+System Bus、稠密输出） | 全部通过 | **PASS** | **PASS** |
| 厂家 `SRAM_Lib_2025` 12 层周期 / 150 MHz 吞吐量 | ≥ 3,000 layers/s | **44,230 拍 / 3,391.36 layers/s** | **41,267 拍 / 3,634.87 layers/s** |
| 本地 72 夹具全量回归（1,824,768 个输出逐元素比对） | 100% 一致 | **72/72 PASS** | **72/72 PASS** |
| 600 样本 12 层最大 NRMSE（Y13 定点输出） | ≤ 3.00% | **0.1211%**（9.60/10 分） | **0.2349%**（9.22/10 分） |
| 官方 SCC40NLL RVT 整机新增加速器增量面积 | < 0.40 mm²（上限 2.25） | **0.316366 mm²** | **0.303804 mm²** |
| Formality 等价性（整机 `qingyu_e203_soc_top` / 独立 `u_fio`） | SUCCEEDED | **31,227 / 14,881 PASS** | **30,843 / 14,497 PASS** |
| PrimeTime 150 MHz 独立加速器 `u_fio` 全五角（TT/SS125/SS−40/FF125/FF−40） | Setup & Hold ≥ 0 | **五角全 MET**（最差 `+0.00008 ns`） | **五角全 MET**（最差 `+0.00015 ns`） |
| PrimeTime 150 MHz 整机 TT Setup & 全五角 Hold | 全部 ≥ 0 | **TT Setup MET + 五角 Hold 全 MET** | **TT Setup MET + 五角 Hold 全 MET** |
| PrimeTime PX 平均功耗 / 单任务平均能耗（`Not Annotated = 0.00%`） | < 10.00 µJ | **31.000 mW / 9.1397 µJ**（12 层） | **30.875 mW / 8.4931 µJ**（4 窗） |
| 整机 `synth_eco/mapped.v` + TT SDF 反标门级仿真（含 131,072 字毒化预装） | 0 失配 | **PASS（44,230 拍，mismatches=0）** | — |

公开仓库不包含 PDK、厂家 SRAM 模型、私有任务向量、语音数据集、工具链和大体积波形。目录内保存了缺项说明及 SHA-256，复现需在授权环境恢复依赖。

---

### 历史版本入口（仅供回溯，不代表当前冻结提交配置）

- 11 月 13 日旧基线：[final/q12_submission_20261113](final/q12_submission_20261113/README.md)（分支 `q12-submission-20261113`）
- 早期主工程与交接记录：`qingyu/` 及 [HANDOFF.md](HANDOFF.md)
