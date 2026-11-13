# Q12 提交基线：native12 earlycheck

本目录是用户于 2026-11-13 指定保留的提交版本。分支 `q12-submission-20261113`，标签 `q12-submission-20261113-r1`。这是源码冻结与交付选择，不是评测全部通过的声明。

## 实测结果

| 指标 | 数值 | 范围 |
|---|---:|---|
| 吞吐 | 6075.99 tasks/s | 150 MHz，历史冻结 12 个完整任务窗口、官方 SRAM 模型 |
| 增量面积 | 0.388582 mm² | 加速器、私有 SRAM、NP3 仲裁及共享路径新增非宏逻辑 |
| 全 SoC 面积 | 2.730734 mm² | 包含复用 CPU、共享 SRAM 与互连；不作为增量成绩 |
| 整机功耗 | 58.36 mW | 同版网表、12 窗口 RTL-SAIF 工程估计 |
| 每任务能耗 | 9.60 µJ | 同版整机功耗乘完整任务时间，平均 12 窗口 |
| DC setup / hold | 0 / +0.00070456 ns | 已报告路径；不能替代完整约束覆盖检查 |

相比上一版约数 6000 tasks/s、0.48 mm²，吞吐约 +1.3%、面积约 -19%。旧记录 7 µJ 缺同口径报告，本次数值较高，不能宣称能耗改善。

## 目录和使用

- `src/`：从原公开 SoC 源码派生的完整源文件树，已覆盖本版计算、解码、传输、输出模块和测试平台。
- `filelist.json`：编译顺序和 include 目录。`src/q12_vendor/` 是测试平台/宏存在性检查，不能参与综合。
- `firmware/`：本版固件源码及验证过哈希的 `firmware64.hex`。
- `FREEZE_MANIFEST.json`：源码和数据格式的身份。`verify.py` 校验所有冻结源文件，不启动 EDA。
- `report/`：11 页测量报告及原始图；`DELIVERY_SHA256.json` 绑定整个交付目录。
- `evidence/`：有时间和来源标记的测量转录；旧时间点记录保留原状态，最新解释见 `final_report_data.json`。

从仓库根目录执行：

```sh
python3 final/q12_submission_20261113/verify.py
python3 experiments/q12_dense_20261113/run_local.py --cases 12 --storage-bits 12 --weight-bits 10 --write-priority --early-output-check
python3 experiments/q12_dense_20261113/check_output_fault.py
```

第一条仅检查完整性；后两条需要 Linux/WSL 下已安装 Verilator、Icarus、RISC-V GCC 和 NumPy，使用合成数据，不能代替正式 600 样本验收。服务器测量源目录为 `/tmp/q12_earlycheck_full_y0zb5w2z`，功耗复测为 `/tmp/q12_power_recovery_gghtgybp`。服务器原始输入、mapped.v、mapped.sdc、mapped.svf 及工具报告留在原处。网表 SHA-256：`3eb43b4d79bbeb0389f4bb272e93629e7241dc1a6186c4e6c37a8b7bd448b712`。

服务器复现历史过程的脚本位于 `experiments/q12_dense_20261113/server/`；`run_earlycheck_full.py` 和 `run_power_recovery.py` 依赖该服务器已生成的原始包并带本轮时限，**不能在新环境原样启动**。请根据其明确参数恢复同一输入并更新运行目录和时限。公开仓库不包含 PDK、官方 SRAM 模型、私有样本及活动文件；本导出不伪装成无依赖的一键竞赛提交工具。

## 输出和规则

采用 X12/W10/Y12；固定的最近偶数舍入和饱和量化，不训练、不按测试样本拟合。输出完整 99×256 signed12 矩阵，16 个 tile，每 tile 594 个 32 位字；固定宽度、固定下标，无 Rice/差分/变长/零值省略输出。输入解码器仍属于输入传输，不是输出压缩。输出物理尺度变为旧 Y13 的两倍，旧精度分数不可沿用。

保留原 32 位 System Bus 和单一共享 SRAM 入口，完整写回并收到最终响应后才结束计时。新增 `loader_*` 平台接口仍待正式认可。

## 已知未闭合项

1. 150 MHz 已报告路径无负 slack，但 `check_timing` 仍列出官方 UART 锁存器、AON 异步入口等未约束端点；hold 余量仅约 0.70 ps。
2. 功耗首窗口有 215 个 slew 超表、2685 个负载超表和 3 个无函数库单元；活动来源严格审计未闭合，9.60 µJ 是工程估计。
3. Formality 工具显示 35565 个通过点、0 个失败点，但另有 625 个 unread 点、9 个参考侧未匹配点与 RTL 解释告警；严格等价审计不通过。
4. 正式随机 600 样本精度和 loader 接口验收未完成。

冻结版本不再原地改写。后续修改放在 `q12-followup-20261113`，每次更改重新绑定源码、网表、吞吐、面积及功耗证据，不混用不同版本成绩。
