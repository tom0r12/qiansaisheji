# Q12 冻结工程公开源码导出（2026-11-13）

本目录为用户指定停止优化后的 **Q12 INT12 最终候选**，不等同于历史 opt12。RTL、固件和测量脚本逐字节保留冻结内容；设计签核仍待服务器报告。当前交接说明见 [HANDOFF.md](HANDOFF.md)。

## 目录

- `assessment/`：完整 157 个硬件源文件、官方库综合、面积、Formality、活动覆盖审查和功耗脚本。源文件哈希见 `assessment/hardware/manifest.json`。不含工艺库。
- `vendor/`：厂家 SRAM 回归测试台、冻结固件及测量程序。**故意不发布 tasks/ 下的 36 个真实输入/权重/参考结果文件。** 原始 manifest.json、inputs.sha256 原样保留，以便私下恢复数据后校验。
- `freeze_snapshot/`：冻结来源中源码、驱动、参考模型及程序镜像副本，保持原有目录以便定位来源；绝对路径清单是溯源信息，不表示克隆后已配置本机工具。
- `evidence/`：冻结清单、既有精度证据及合规待核事项。吞吐按 150 MHz 名义频率折算，不能替代时序签核。
- `EXCLUDED_PRIVATE_FILES.json`：未发布的任务文件及 SHA-256；除此之外，工艺库、厂家模型、语音数据集、权重数据及工具链亦须自行在获授权环境配置。
- `PUBLIC_EXPORT_MANIFEST.json`：本导出校验清单；`VERIFY_PUBLIC_EXPORT.py` 只检查公开内容完整性，不替代厂家仿真或功耗验证。

## 接手顺序

1. 运行 `python VERIFY_PUBLIC_EXPORT.py`，验证公开文件一致性。
2. 阅读交接说明及 `evidence/compliance_limits.json`。此版本增加独立 loader_* 硬件入口，严格平台接口符合性仍为 OPEN；不可仅凭总线验证宣称组委会最终接受。
3. 在授权服务器恢复原始私有任务文件，逐项匹配 EXCLUDED_PRIVATE_FILES.json。厂家 SRAM 模型及 SCC40NLL RVT 库从服务器合法位置读取，不上传 GitHub。
4. 阅读 `vendor/README.txt`、`assessment/README.md`，优先续跑服务器已有冻结任务。不要因为 clone 后缺少私有输入而绕过 manifest 校验，也不要重复启动整机综合。

仅克隆本仓库不能直接完成 12 层数值复验：私有向量和 EDA/PDK 必须另行配齐。GitHub 上的公开导出与服务器原始 ZIP 哈希不同是因为故意剔除了私有文件；原始冻结源码字节未改。

交接说明中的本机 `freeze/precision_audit.json`、`freeze/compliance_limits.json`、`freeze_manifest.json` 在公开目录分别位于 `evidence/`；服务器现状记录在 `evidence/server_progress.json`。服务器任务已启动，PID 仅为当时观察值，不保证当前仍存在。
