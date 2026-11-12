# 隔离式服务器验证包

本包包含 opt13/opt14/opt15 中明确选择的候选源码、SoC 测试平台、完整计时监视器、源文件哈希，以及按参数选择的十二层任务镜像和固件。可通过 `--include-vendor` 同时包含小型公开 E203 RTL 树与 LICENSE；不含工艺库、Speech Commands 音频、TensorFlow 或账户凭据。`manifest.json` 记录实际内容；缺少镜像或固件的源码包会拒绝运行。

## 执行方式

解压到一个新目录。若包内已有 E203，直接运行即可；否则配置现有、只读的上游源码根。厂家模型根默认如下：

```sh
# 仅在未打包公开 E203 时需要：
# export QINGYU_VENDOR_ROOT="$HOME/Desktop/已核验基座/inputs/vendor/e203_hbirdv2"
export QINGYU_SRAM_MODELS=/storage1/admin_public_dir/SRAM_Lib_2025
sh run_vcs.sh --candidate opt15_validate4 --mode macro --preflight
sh run_vcs.sh --candidate opt15_validate4 --mode macro
```

候选名称必须在本包清单中。`s.sh` 是 opt15 厂家宏仿真的短入口。可用 `QINGYU_VCS` 指定 VCS 可执行文件，`QINGYU_RUN_PARENT` 指定已存在的运行父目录。默认在 `~/Desktop` 下以 `qingyu_verify_` 前缀创建全新的随机运行目录，失败也保留日志，不删除或修改历史工程。E203 逐文件哈希不匹配时会停止，不能忽略差异后混用指标。

`--mode behavioral` 使用行为 SRAM，只用于功能和周期交叉检查。`--mode macro` 读取真实 RAMSP128X16、RAMSP1024X16、RAMSP4096X16 模型，经过宏端口加载数据和独立读回全部结果；包中不以替身模型冒充厂家模型。

## 时间和活动窗口

每次任务独立复位，输入/参数先放在共享 SRAM staging 区，CPU 再执行验证、搬运和控制。计时从 **首次任务源区读请求尝试** 开始，包括等待读取的时间；结束于 **最后一个完整输出写响应**。因此包含此前旧指标遗漏的参数扫描和后续调度。初始化 ITCM、测试平台装入 staging 以及首次参数读取前的 CPU 启动不在此窗口内。这仍需与组委会最终装载接口确认。

`--activity` 使 VCD 从同一个完整窗口起点开始、同一个终点结束。转换 SAIF 应使用 `QINGYU_COMPLETE_START`/`QINGYU_COMPLETE_END` 的 `time_ps`，不能使用旧 `QINGYU_PERF_START`。还必须核对实际 timescale、SAIF duration、逻辑与 SRAM 活动覆盖及静态功耗，不能把未标注电路视为零活动。

## 工艺工具与复用线索

以下是历史脚本记录的预期路径，执行前应在服务器核验：

| 工具或输入 | 预期位置 |
|---|---|
| VCS | `/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs` |
| Design Compiler | `/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell` |
| PrimeTime | `/eda/synopsys/prime/prime_2022.03-SP5-1/bin/pt_shell` |
| Formality | `/eda/synopsys/fm/fm_2020.09-SP5/bin/fm_shell` |
| 厂家 SRAM 模型和 Liberty | `/storage1/admin_public_dir/SRAM_Lib_2025` |
| 官方标准单元来源 | `SMIC40_2025/S40.tar.gz` 中的 SCC40NLL_VHSC40_RVT_V0p1 |

旧工程 `qingyu_h1500v_MIkhor`、`qingyu_h1500v_hold3_jcN9MG`、`qingyu_formality_h1500vo_rmzCHu`、`qingyu_h1500v_soc_XqFVPn`、`qingyu_h1500v_energy_q0dAmy` 可以提供流程参考。这些目录的结果属于历史版本。

## 综合、时序、等价和功耗的待接入项

`filelists/*_soc_synth.f` 提供本候选数字 SoC 与 ASIC SRAM 封装源码，外部厂商单元应由真实 `.db` 链接。正式时钟目标为 150 MHz。先核对实际输入/输出延迟、slew、负载、时钟不确定度、库角和单位，禁止用无效例外隐藏违例。

`historical_reference` 仅保留旧脚本供审阅：其中部分只综合四通道 `qingyu_accel`、使用过时 sc9mc 库或硬编码旧网表路径，**不能不修改就作为本候选签核入口**。正确接入顺序是：

1. 用当前候选和官方库生成新的综合网表、SDC、SVF，记录源/库/配置哈希与实际 SRAM 数量。
2. 对同一个冻结网表跑五角 setup/hold 与整机必要时序覆盖；所有新增接口保留在约束范围内。
3. Formality 比较本候选 RTL 与其本网表，使用本次 SVF，不复用旧 opt13 的比较点数字或无依据切点。
4. 基于同一冻结配置和上述完整任务活动窗口计算整机功耗与单任务能耗；报告逻辑、SRAM 活动覆盖率。

新增共享 SRAM 多端口仲裁、响应保持与接口逻辑位于 `u_shared`，不全在 `u_fio` 内。评分面积必须包含这些新增标准单元；只统计 `u_fio` 会漏算。固定 512 KiB SRAM 宏、复用 E203 和固定总线外设可按赛题单列，不代表它们周边新增逻辑也可排除。整机功耗应包含 E203、加速器、互连及全部 SRAM。

| 源结构私有宏 | opt13_row8 | opt14_ybank2 / opt15_validate4 |
|---|---:|---:|
| 128×16（W/Y/metadata） | 41 | 37 |
| 1024×16（X） | 16 | 16 |

共享 SRAM 另外为 64 个 4096×16 宏，TCM 宏按真实配置单列。综合若合并宏必须解释并以实际数量重算面积/活动映射，不应只放宽数量检查。

本包运行成功仅证明对应镜像的功能和周期结果。官方 600 条精度、综合网表、时序、等价、面积和功耗仍需要各自的真实证据。
