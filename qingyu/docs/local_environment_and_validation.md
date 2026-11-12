# 本地环境与验证

本文记录 2026-11-11 的本地环境和验证入口。当前候选结论以[主工程 README](../README.md)和[INT8 系统总线评估](int8_soc_candidate_review_20261112.md)为准；以下 PowerShell 命令均从主工程 qingyu 目录执行。

随仓库保留的 [本地验证摘要](evidence/20261111_local_validation.json) 汇总真实 SoC、三个组件候选、驱动边界检查、环境和限制；[冻结校准与验证摘要](evidence/20261111_model_calibration_validation.json) 保留训练/验证身份哈希、逐层配置哈希和数值统计。build/ 与 reports/ 的完整生成物默认忽略，须从原工作区恢复或按本文重跑；摘要不会替代原始输入、日志或正式签核报告。

## 当前系统总线入口（优先使用）

2026-11-11 后续审计发现 opt12～15 的额外 DMA 通路绕过了原平台总线。下文保留这些旧结果供复现，不能作为当前提交路线。新版本的全部共享访问经过原 E203 memory fabric，原 vendor RTL 和总线参数不变。

```powershell
# 下列命令从 qingyu 目录执行
.\scripts\local.ps1 soc --candidate opt25_fused4 --layers 12
.\scripts\local.ps1 soc-queue --candidate opt30_fusedpipe4 --layers 12 --images build/model_headroom1_20261111/soc_images_out16 --data-kind KWT_VALIDATION
.\scripts\local.ps1 fio-faults --candidate opt30_fusedpipe4 --fused
```

新 runner 的基础源清单固定在 scripts/fixtures/e203_soc_sources.f，不依赖被忽略的 build/dual_row_study。构建复用核对解析源顺序、文件哈希、宏与工具参数。两个入口分别使用单笔与排队协议的独立监视器，逐笔核对 CPU/DMA、官方 fabric 和 SRAM 请求/响应、source/live 地址与值、私有 X/W 以及全部输出。排队监视器记录已接受请求的 owner FIFO，不以“命令数相同”代替正确路由。

当前结果见 [系统总线证据](evidence/20261111_official_fabric_validation.json) 和 [主工程 README](../README.md)。工程时窗从第一次参数源读取请求到原 DMA 接收最后输出写响应；外部 source staging 初始加载在窗口外。只有接入官方 loader 后才能核算官方完整任务时间。不得把旧旁路周期、150 MHz 假设或历史功耗拼接到新候选。

错误恢复测试另有 scripts/run_fio_queue_fault_checks.py、run_fused_wait_checks.py 和 run_fused_pipe_checks.py，均支持 --candidate。WAIT watchdog 单位是总线时钟，默认 1,000,000 周期；永久下游失联时控制能够返回超时，旧事务仍需真实接受/响应才能排空，不能强行清除后重启。

旧 qingyu_validation_20261111.zip/qy 包含 opt13/15，已过时且未执行。新系统总线包由 scripts/prepare_bus_server_bundle.py 产生；以新包 manifest、包内 README.md 和实际服务器日志确认状态，准备包不代表 EDA 作业完成。

## 环境配置

RTL 和 SoC 运行在 WSL Ubuntu，模型提取运行在 Windows 独立虚拟环境。两条路径共享项目文件，不修改全局 PATH。新机器需先初始化 WSL Ubuntu 并安装 Git；Windows 模型脚本另需 uv。setup_local.ps1 配置已有发行版中的工具，不代替 Windows/WSL 安装。

| 用途 | 本机已验证环境 |
|---|---|
| RTL 四态回归 | WSL Icarus Verilog 12.0；Windows G:\iverilog\bin 版本也已完成组件测试 |
| SoC 仿真及 lint | WSL Verilator 5.020、G++ 13.3.0、Make 4.3 |
| E203 固件 | WSL RISC-V GCC 13.2.0，RV32IMAC / ILP32，使用 -misa-spec=2.2 |
| 整数模型及镜像 | WSL Python 3.12.3、NumPy 1.26.4 |
| KWT 提取 | Windows Python 3.11.15、TensorFlow 2.14.1、Addons 0.22.0、NumPy 1.26.4 |
| 模型依赖锁定 | model/requirements-model-win-py311.resolved.lock.txt |

~~~powershell
# 仅缺项时安装 Ubuntu 包，恢复固定 E203 提交的缺失文件
.\scripts\setup_local.ps1

# 实际编译、仿真、源文件校验；不安装或修改 vendor
.\scripts\setup_local.ps1 -CheckOnly

# Windows 模型环境和权重提取 smoke
.\scripts\setup_model.ps1

# 校验完整语音数据并生成新的 256/256 校准与验证目录
.\scripts\setup_model.ps1 -PrepareReference
~~~

setup_local.ps1 写入 tool-config.local.json、reports/environment.json 和 reports/e203-source-manifest.json。E203 固定为 9f3e34f337f5d0a1236a285871ffa2032491617a，本机已验证 137/137 文件。普通恢复只填充缺失或空文件；非空文件若与固定提交不同会保留并报告失败。CRLF 差异按规范 Git blob 核对并单独记录，不重写原文件。

首次 CheckOnly 若尚无参考 Git 对象，可传 -E203Reference 指向该提交的官方克隆；正常 setup 会自行准备缓存。参考目录只用于校验与恢复，不替代提交源码。

setup_model.ps1 使用固定 Python 及包锁文件，保留已有不兼容环境并报错。KWT 源码固定为 237e4097afd4f6851e0b82f0a8d65c2dfe8eae30。为规避 TF 2.14 Windows 文件枚举对中文父路径的限制，脚本可自动建立同盘 ASCII junction；原始数据仍在 data/speech_commands_v0.02。

## 组件与驱动测试

~~~powershell
.\scripts\local.ps1 model-tests

.\scripts\local.ps1 candidate-checks --cases 12 --seed 20261112 --candidate experiments/h1500v/opt13_row8/rtl --candidate experiments/h1500v/opt14_ybank2/rtl

.\scripts\local.ps1 candidate-fast --cases 12 --seed 20261112 --candidate experiments/h1500v/opt13_row8/rtl --candidate experiments/h1500v/opt14_ybank2/rtl
~~~

组件测试使用 99×64×16 生产参数，OUT16、流水 MAC、双缓冲、读取预取均启用。独立 Python 整数算法生成参考输出；覆盖符号、极值、舍入、饱和、尾三行、随机背压、索引读取、满槽软复位、运行中硬复位和驻留权重重启。candidate-fast 去掉人为消费暂停及索引探测，用于同条件组件周期比较，不能代替完整 E203 任务周期。

opt15 的独立 C 边界测试在 WSL 中运行：

~~~powershell
$linuxProject = (wsl.exe -d Ubuntu --exec wslpath -a -u (Get-Location).Path).Trim()
wsl.exe -d Ubuntu --cd $linuxProject --exec python3 scripts/run_validate4_checks.py
wsl.exe -d Ubuntu --cd $linuxProject --exec python3 scripts/run_validate4_checks.py --sanitize
~~~

普通及 ASan/UBSan 模式各已通过 283,446 项检查，包括所有 shift 字节值和列位置、四种对齐、bias 边界、结构错误优先级、guard page 和验证阶段不访问 MMIO。各轮回归写入新目录，不覆盖历史日志。

## 历史旁路 SoC 测试（opt13～15）

默认使用合成工程数据：

~~~powershell
.\scripts\local.ps1 soc-legacy --candidate opt14_ybank2 --layers 12
.\scripts\local.ps1 soc-legacy --candidate opt15_validate4 --layers 12
~~~

run_candidate_soc.py 构建真实 E203、FIO、候选加速器和共享 SRAM 行为模型，运行相应 C 固件，每任务检查全部 25,344 个结果。完整窗口从首次参数源读取请求至最后输出写回，包含参数合法性验证、搬运、总线等待及调度；同时保留历史装载窗口。

输出为 `build/soc_<candidate>_<UTC timestamp>/result.json`，逐层目录含固件、输入、预期输出及日志。复用编译产物应使用 --reuse-build 校验入口；不要手工复制旧可执行文件来替代源码、配置和监视器检查。

复用时还核对 Verilator 的构建参数：只归一化运行目录和并行任务数，时序、宏定义、include 搜索路径等必须相同。旧报告没有参数字段时必须从原构建的 Vcandidate__verFiles.dat 验证迁移，缺失或不匹配就要求重建。本轮已用两组现有真实 build 验证迁移，并验证修改 timescale 会被拒绝，原始结果未改。

## 真实模型与数据

完整 Speech Commands V2 已校验并解压。压缩包大小 2,428,923,189 字节，MD5 为 6b74f3901214cb2c2934e98196829835，SHA-256 为 af14739ee7dc311471de98f5f9d2c9191b18aedfe957f4a6ff791c709868ff58。解压目录有 105,841 个文件、105,835 个 WAV。

本轮完成目录为 build/model_reference_20261111_201956_613。

| 相对目录 | 含义 |
|---|---|
| float_training/、float_validation/ | 指定模型提取的十二层浮点输入与参数 |
| validation_vectors/validation_report.json | INT32 输出格式的本轮数值对照 |
| validation_vectors_out16/validation_report.json | OUT16 训练冻结配置及独立验证结果 |
| validation_vectors_out16/layerNN/ | 冻结层配置及选中的硬件对照任务 |
| soc_images_out16/images_manifest.json | 十二个 SoC 任务的身份、配置及校验信息 |
| soc_images_out16/layerNN/ | shared.hex、expected.hex 和配置 |

两组各 256 条样本，均覆盖十二类，训练/验证样本身份不重叠。OUT16 最大层 NRMSE 为 0.0621691551%，输入裁剪为零，输出饱和 488 / 77,856,768；十二个选中硬件任务最大 NRMSE 为 0.0079919162%。饱和计数完整保留，没有删除相关样本。INT32 对照最大层 NRMSE 为 0.0129004074%。

INT16 报告 SHA-256 为 65f74a513cd0156320ab38c20de942f38fa8132640359c29337f6f696cb77170；镜像 manifest SHA-256 为 589ac306074f1398f62724aaa8e2e9574279deaf7a556893d28d77c55011a1cd。重跑会生成新的目录及记录，以实际报告和哈希为准。

真实镜像接入 SoC：

~~~powershell
$modelRecord = Get-Content build/model_environment.json -Raw | ConvertFrom-Json
$imagesWindows = Join-Path $modelRecord.reference_pipeline 'soc_images_out16'
$imagesLinux = (wsl.exe -d Ubuntu --exec wslpath -a -u $imagesWindows).Trim()
.\scripts\local.ps1 soc-legacy --candidate opt15_validate4 --layers 12 --images $imagesLinux --data-kind KWT_VALIDATION
~~~

该轮与合成回归分开记录。原 OUT16 真实镜像 opt13/opt15 各十二层、304,128 输出已通过，逐层输入与预期输出哈希相同。完整周期平均 24,432.75 → 21,680.75，减少 11.26357%，同频吞吐提高 12.69329%；详见 [原配置对照摘要](../reports/opt13_opt15_real_comparison.json) 和 [交接说明](../../HANDOFF.md)。

TensorFlow 2.14.1 与上游原始 2.4.0rc1 不同，运行环境保存在 build/model_environment.json 及依赖锁文件。后续量化候选应使用独立目录，不覆盖当前冻结基线。

## 固定输出余量候选

build/model_headroom1_20261111 保存统一增加一位输出移位的独立实验。所有层和通道采用同一策略，仍只使用训练集拟合基础尺度，原 OUT16 基线没有被覆盖。RTL 与每任务 50,688 字节输出大小不变。

256 条独立验证上的最大层 NRMSE 从 0.0621691551% 降到 0.0106038061%，输出饱和从 488 个降到零。训练集最大层 NRMSE 从 0.0075400482% 上升到 0.0106507730%，体现舍入精度与动态范围的交换。十二个选中任务最大 NRMSE 为 0.0113211733%。完整逐层证据位于 headroom_comparison.json。

复现到独立的新目录：

~~~powershell
$headroomRun = 'build/model_headroom1_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff')
.\.venv-model\Scripts\python.exe model/study_output_headroom.py --reference-run build/model_reference_20261111_201956_613 --output $headroomRun
~~~

新镜像目录为 build/model_headroom1_20261111/soc_images_out16，manifest SHA-256 为 afffd63fc5326dd9cb1c040c8e155b7c92feee127a5fa44977374e01a5103179。这些新镜像已分别在 opt13 与 opt15 完成十二层、各 304,128 输出逐位核对；平均完整周期仍为 24,432.75 → 21,680.75，见 [历史旁路配置对照摘要](../reports/opt13_opt15_headroom1_real_comparison.json)。复现硬件回归应明确选择这组镜像：

~~~powershell
$headroomImagesWindows = (Resolve-Path 'build/model_headroom1_20261111/soc_images_out16').Path
$headroomImagesLinux = (wsl.exe -d Ubuntu --exec wslpath -a -u $headroomImagesWindows).Trim()
.\scripts\local.ps1 soc-legacy --candidate opt13_row8 --layers 12 --images $headroomImagesLinux --data-kind KWT_VALIDATION
.\scripts\local.ps1 soc-legacy --candidate opt15_validate4 --layers 12 --images $headroomImagesLinux --data-kind KWT_VALIDATION
~~~

新配置数值报告 SHA-256 为 366ae4838bb3ce8f2828bc4453bd5590b8f530af85715fd71916115924327ba9。原冻结配置的精度和 SoC 结果仍独立保留。赛题采用按比例扣分，不能把通过 3% 门槛直接写成数值精度满分。

## 证据范围

| 数据或检查 | 能支持的结论 | 不能替代的结论 |
|---|---|---|
| 合成工程向量 | 覆盖用例的位准确性、协议行为及同条件周期 | KWT 精度、官方样本成绩 |
| Silence smoke | 固定权重恢复、模型结构和提取路径可执行 | 训练校准、独立验证精度 |
| 本地 256/256 官方来源子集 | 冻结数值格式在独立验证子集上的误差 | 组委会 600 条评测结果 |
| 真实镜像 SoC 回归 | 选中任务的 RTL/软件逐位一致性及系统周期 | 全部验证样本的 RTL 穷举、正式芯片 PPA |
| 生产配置 Verilator lint | 指定配置的结构检查及记录的告警判读 | 商业 CDC/RDC、综合、STA、Formality |
| 假定 150 MHz 的换算 | 按该时钟假设换算时间 | 150 MHz 时序收敛 |
| 历史 opt14 输出 SRAM 八宏降至四宏 | 源结构所用宏数量减少 | 正式总面积或功耗减少百分比 |

正式面积应包含加速器、接口和内部 SRAM；功耗与能耗须使用最终同一网表、规定库与工况、完整窗口及充分活动覆盖。本轮不把历史 opt12/13 的面积、功耗或 Formality 结果归给新候选。

## 服务器评估

当前服务器包哈希、已执行步骤和未完成的宏仿真/综合/STA/功耗项目，集中记录在[服务器 EDA 状态](eda_server.md)。本页不复制登录过程、临时文件操作或旧包交付日志。
