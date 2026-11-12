# 轻语 E203 前馈线性加速器

本工程实现 `Y[99,256] = X[99,64] × W[64,256] + b[256]`。共享 SRAM 访问经 E203 平台原系统总线；INT8 实验同样保留原 fabric 和总线参数，没有为加速器增加共享 SRAM 直连通路。

## 当前状态

主候选仍是 [opt30_fusedpipe4](experiments/h1500v/opt30_fusedpipe4/README.md)，选择记录见 [current_candidate.json](current_candidate.json)。另有一条较新的 INT8 整机实验：固定验证集的 256 条记录 × 12 层，共 **3072 个真实 E203 任务全部通过**。其计时从 CPU 参数配置写到最终输出 ACK，平均 10,557.79 拍；输入源预装在计时窗外。按尚未签核的 150 MHz 换算约 14,207 tasks/s，只代表这个工程窗口。

如果把理想串行输入装载也加到该窗口，报告中的平均值为 15,356.77 拍，按 150 MHz 换算约 9,768 tasks/s。因此官方 loader 口径下是否达到 10,450 tasks/s 尚未证明。指定工艺增量面积和整机任务能耗也没有实测，不能据此宣称通过 0.5 mm² 或 6.3 µJ 门槛。完整说明与证据入口见 [当前评估报告](docs/int8_soc_candidate_review_20261112.md)。

## 架构与验证边界

E203 通过原 memory fabric 访问共享 SRAM；CPU、加速器与共享存储的命令和响应均纳入整机监视。INT8 结果覆盖完整矩阵输出、未写输出槽、源数据和 guard 区。每个任务使用独立的任务数据与参数状态，不以跨任务缓存来减少计时工作。

3072 项回归使用冻结验证数据，不是组委会最终 600 条评测。当前窗口排除了源包初始装载；150 MHz 只是换算假设。厂家 SRAM 模型仿真、指定库综合、Formality、150 MHz STA、全 SoC SAIF 功耗和官方 loader 时窗仍须单独完成。

## 目录

| 路径 | 内容 |
|---|---|
| `experiments/h1500v/` | INT16 系统总线候选和同口径比较 |
| `experiments/arithmetic/` | INT8 计算核候选、契约和回归入口 |
| `experiments/codec/` | 无损 Rice 编解码器候选 |
| `experiments/integration/` | E203、系统总线、共享 SRAM 和服务器验证包 |
| `experiments/memory/` | 私有 SRAM 映射实验 |
| `model/` | 整数参考、量化和验证数据转换脚本 |
| `rtl/`, `sw/`, `tb/`, `scripts/` | RTL、驱动、测试平台和本地流程 |
| `docs/evidence/` | 可随仓库复核的结果摘要与哈希 |
| `build/`, `reports/`, `experiments/**/runs/` | 本地产物和原始回归输出，不作为源码分发 |

## 本地环境

从 `qingyu/` 目录运行 PowerShell：

```powershell
.\scripts\setup_local.ps1 -CheckOnly
.\scripts\local.ps1 model-tests
.\scripts\local.ps1 soc-queue --candidate opt30_fusedpipe4 --layers 12 --images build/model_headroom1_20261111/soc_images_out16 --data-kind KWT_VALIDATION
```

没有传入真实 `--images` 时使用的合成工程向量只能检查功能，不能作为 KWT 数值精度证据。本地环境细节见[环境与验证说明](docs/local_environment_and_validation.md)。
