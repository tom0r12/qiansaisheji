# 轻语 · E203 前馈线性加速器

当前指定提交基线为 **Q12 native12 earlycheck（2026-11-13）**，入口在 [final/q12_submission_20261113](final/q12_submission_20261113/README.md)。分支 `q12-submission-20261113`，冻结标签 `q12-submission-20261113-r1`。实测约 **6076 tasks/s、增量面积 0.3886 mm²**；整机功耗工程估计 **58.36 mW、9.60 µJ/任务**。150 MHz 全约束时序、严格功耗及等价审计、正式精度和 loader 接口验收仍有未闭合项，不能宣称已全部合格。

[测量报告](final/q12_submission_20261113/report/q12_measurement_report.pdf)包含对比、方法和原始截图。当前版本已冻结，后续修复在 `q12-followup-20261113` 分支进行。旧的 [final/q12_20261113](final/q12_20261113/README.md) 是历史压缩输出基线，不能直接替代本次提交版本。

完整的[技术报告](reports/q12_template_20261113/qingyu_technical_report.pdf)包含两页快速预览、设计原理、数据通路、测试分析和原始截图。[报告源码与编译说明](reports/q12_template_20261113/README.md)位于报告目录；队伍编号和参赛队名在封面配置中填写。

公开仓库不包含 PDK、厂家 SRAM 模型、私有任务向量、语音数据集、工具链和大体积波形。目录内保存了缺项说明及 SHA-256，复现需在授权环境恢复依赖。

以下入口保留历史版本，不能用于描述当前候选：

主工程在 qingyu/。当前版本、外部依赖和复现步骤见 [交接说明](HANDOFF.md)。基础 RTL 在 qingyu/rtl，opt12 和 opt13 的实际 RTL、固件、测试平台分别在 qingyu/experiments/h1500v/opt12_wait 和 opt13_row8。
