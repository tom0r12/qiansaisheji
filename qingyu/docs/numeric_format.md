# 数值格式、参考模型及向量

格式版本为 `qingyu-fixed-v1`。此目录已经提供 NumPy 整数参考、训练校准工具、冻结配置转换、传输打包和测试。`tb/vectors` 中数据全部是确定性生成的**合成工程测试向量**，不来自 Speech Commands，不代表 KWT 精度或官方验收结果。

## 实现定义

- 输入、权重采用有符号 INT16，量化编码范围是 `-32767..32767`，对称零点为零。整数模型也支持 INT16 最负数以测试接口边界。
- `s_x=2^e_x` 每层固定；`s_w[j]=2^e_w[j]` 每层每输出通道固定。零权重通道使用尺度 1。
- `q_b[j]=RNE(b[j]/(s_x*s_w[j]))` 为有符号 48 位；先将偏置装入累加器，再逐项执行 64 次乘累加。模型在每次加法后检查有符号 48 位边界，检测暂时溢出，即使最终数学和发生抵消也不能掩盖。
- 输出是 `sat32(RNE(A/2^r[j]))`，`r[j]` 是固定的 0..47 右移值。采用最近偶数舍入，正负数对称；例如右移一位时 `3→2,5→2,-3→-2,-5→-2`。
- 输出越界饱和到 `[-2^31,2^31-1]`；内部累加越界报错。软件模型返回输出饱和数量。
- 解码只计算 `float(q_y[j])*s_x*s_w[j]*2^r[j]`，不补做矩阵运算、偏置或误差修正。

校准只允许显式声明 `training` 的数据；验证和测试转换只能读冻结配置。配置记录权重/偏置的 SHA-256，转换时发现权重更换则拒绝。自动右移先选择训练样本上无输出饱和的最小值，验证样本仍可能发生输出饱和，必须检查转换报告。输入尺度由训练样本范围决定；是否适合真实评测仍需训练校准与验证数据支持。

## 软件 API

`model/reference.py` 提供：

| 接口 | 含义 |
|---|---|
| `round_shift_rne(value,shift)` | Python 整数的精确有符号舍入 |
| `qlinear_int(qx,qw,qb,shifts)` | X[...,K]、W[K,N]、b[N]，返回 output、accumulators、saturation_count |
| `calibrate_layer(X,W,b,layer,role='training')` | 训练范围、幂次尺度、输出移位和偏置上界检查 |
| `encode_layer(X,W,b,config)` | 按冻结配置编码，不重新标定 |
| `decode_layer(q_y,config)` | 按固定尺度解码 |
| `NrmseAccumulator.update(layer,reference,decoded)` | 按层累计平方误差和参考平方值 |
| `export_layer_vectors(...)` | 输出整数 NPZ 及 MMIO 十六进制字 |

NRMSE 按每层全部元素计算：`sqrt(sum(error²)/N)/max(sqrt(sum(reference²)/N),1e-8)`；再取 12 层最大值。不能平均单样本比值。最终完整精度检查使用 `summary(require_all_layers=True)`；单层转换报告只覆盖当前层，不能作为 12 层精度结论。

## 运行方法

在工程 `qingyu` 根目录执行。使用带 NumPy 的 Python；本次使用 Codex 自带 Python 运行整数测试。

```text
python -m unittest discover -s model -p "test_*.py" -v
python model/generate_vectors.py --output tb/vectors --layers 12
python model/prepare_layer.py calibrate --input data/training/layer00.npz --split training --layer 0 --output data/config/layer00.json
python model/prepare_layer.py convert --input data/validation/layer00.npz --split validation --config data/config/layer00.json --output data/converted/layer00
```

浮点输入 NPZ 必须包含 `X[...,64]`、`W[64,256]`、`b[256]`，可包含对应的官方浮点 `Y[...,256]` 和字符串 `split`。不提供 Y 时工具以 float64 `X@W+b` 为本地参考，并在报告中仅标为供应的浮点数据转换。一个样本 X 为 `[99,64]`；多个样本可为 `[S,99,64]`，转换后每个样本有独立向量目录。

## 总线字顺序

每行文本是一个 32 位无符号十六进制总线字。这里的“小端”指低地址半字放在低 16 位，不对十六进制字符串逐字节倒序。

| 文件 | 顺序与数量（99、64、256、4 路） |
|---|---|
| `x_words.hex` | `[t,k]`，相邻两项 INT16 合成一字，共 3168 字 |
| `w_tile_words.hex` | `[tile,k,p]`，tile 0..63、p 0..3，共 8192 字；每块 128 字 |
| `meta_words.hex` | 每输出通道两字，低字在先；共 512 字，每块 8 字 |
| `y_row_words.hex` | `[t,j]` INT32，共 25344 字 |
| `y_tile_words.hex` | `[tile,t,p]` INT32，共 25344 字，每块 396 字 |
| `integer_case.npz` | qx、qw、qb、shifts、qy 原始形状，方便独立复核 |

参数记录为 64 位：低 48 位有符号偏置，48..55 位右移量，56..63 位保留零。完整输入必须先装载；每块加载对应的 128 个权重字和 8 个参数字。独立任务必须重装，不跨任务缓存。所有文件字数、偏移和校验值在 `manifest.json` 中记录。

## 指定 KWT 模型的提取入口

`model/extract_kwt1.py` 要求已经取得 ARM 官方仓库并检出提交 `237e4097`，且有完整 `best_weights` checkpoint 和兼容 TensorFlow/TensorFlow Addons。脚本复用官方模型、预处理层和 Transformer 实例；关闭训练增强、Dropout、随机时间移动，逐层提取第一 Dense 层之前的 PostNorm 输入及 GELU 前输出。每层通过原始 block 调用进入下一层，检查形状、独立矩阵乘法和最终分类 token 一致性。

```text
python model/extract_kwt1.py --repo vendor/keyword-transformer --audio-npz data/official_loader_audio_validation.npz --split validation --output data/float/validation --limit 1
```

输入 `audio[S,16000]` 必须来自指定代码的官方音频归一化/数据选择流程；可附 `sample_ids[S]` 与 `split`。本工具不自行改写音频预处理、不认证样本划分、标签、静音和 unknown 的生成方式。提取输出为 12 个 layer NPZ 和包含提交、权重哈希、样本标识及库版本的 manifest。

另有 `model/prepare_official_audio.py`：在本地已经解压的完整 Speech Commands V2 目录上调用指定版本的 `AudioProcessor`，生成按原始哈希划分和标签映射选取的音频 NPZ。工具关闭数据增强并禁止自动下载整个数据集，记录样本名、源文件哈希、划分、标签及运行环境。取得数据后可执行：

```text
python model/prepare_official_audio.py --repo vendor/keyword-transformer --data-dir data/speech_commands_v0.02 --split training --count 256 --output data/audio_training.npz
python model/prepare_official_audio.py --repo vendor/keyword-transformer --data-dir data/speech_commands_v0.02 --split validation --count 256 --output data/audio_validation.npz
```

模型环境放在工程内 `.venv-model`，建议安装清单为 `model/requirements-model-win-py311.txt`。Windows/Python3.11 对应 TensorFlow2.14.1、Addons0.22.0、NumPy1.26.4；这与原始仓库 TensorFlow2.4.0rc1、NumPy1.19.5 有版本差异，必须记录并检查数值结果。单独的 `--silence-smoke` 入口只生成一条全零音频，用于真实权重恢复、层形状与计算路径检查，输出标为 `functional_smoke`，不属于训练或验证数据，也不能用于正式校准。

```text
.venv-model/Scripts/python model/extract_kwt1.py --repo vendor/keyword-transformer --silence-smoke --output model/smoke_results
```

**真实 KWT 提取与官方数据精度的运行状态以生成的 manifest 和主工程报告为准；合成向量与单元测试的通过不能替代这一步。**

## 已完成的真实数据验证

官方 Speech Commands V2 原始压缩包已完整下载、校验并解压，大小为 2,428,923,189 字节；MD5 为 `6b74f3901214cb2c2934e98196829835`，SHA256 为 `af14739ee7dc311471de98f5f9d2c9191b18aedfe957f4a6ff791c709868ff58`。来源为 Google 官方地址，下载及安全解压程序是 `model/download_speech_commands_v2.py`，支持断点续传并保留进度、校验和解压状态。

已在上述 Windows/Python3.11 环境中成功恢复指定提交的 `best_weights`，并通过原始模型提取十二层实际 FC1 输入与输出。原始 FC1 kernel 为 `[64,256]`，输入 `[99,64]`，输出 `[99,256]`；独立 `X@W+b` 和原始 Dense 输出完成数值交叉检查。

完整运行使用官方数据加载器，从训练划分选择 256 条样本做唯一一次数值标定，从验证划分选择互不重叠的 256 条样本检查精度。两组均覆盖全部 12 个类别，测试划分未用于调参。配置在验证前按层冻结，没有针对验证结果重新拟合范围。校验结果如下：

| 指标 | 本地 256 条验证子集结果 |
|---|---:|
| 训练样本数 / 验证样本数 | 256 / 256 |
| 训练和验证类别覆盖 | 均为 12/12 |
| 非静音源文件样本集合重叠 | 0 |
| 十二层分别汇总后的最大 NRMSE | 0.01564745159167486% |
| 输入量化裁剪数量 | 0 |
| 输出 INT32 饱和数量 | 7 / 77,856,768 个输出 |
| 选出的十二个硬件任务最大 NRMSE | 0.006037098047212616% |

输出饱和计数保留在报告中，没有删除相关样本。十二个硬件对照任务按“第 l 层选择类别 l 的一个验证样本”生成，因此覆盖全部十二类；各任务的准确样本标识、下标、类别与 NRMSE 均记录在报告中。静音样本由官方代码按零波形生成，其标识按划分和序号区分；不把用于静音生成的占位音频文件误判为训练/验证语音泄漏。

本次结果是**本地独立验证子集**结果，不是组委会冻结后选取的 600 条统一评测。TensorFlow 运行版本也与原始仓库的 2.4.0rc1 存在差异，运行环境及校验值已保留。尚不能据此宣称官方精度验收、芯片面积或功耗验收完成。

复现入口：

```text
.venv-model/Scripts/python model/download_speech_commands_v2.py --output data/downloads/speech_commands_v0.02.tar.gz --extract-to data/speech_commands_v0.02
.venv-model/Scripts/python model/run_reference_pipeline.py --repo vendor/keyword-transformer --data-dir data/speech_commands_v0.02 --work model/full_v2_run --training-count 256 --validation-count 256
```

最终数值配置和真实硬件对照向量位于 `model/full_v2_run/validation_vectors/layer00` 至 `layer11`；汇总报告为 `model/full_v2_run/validation_vectors/validation_report.json`，完整阶段日志与状态在 `model/full_v2_run`。早期 `model/smoke_results`、`model/smoke_quantized` 和 `model/real_validation_vectors` 仅保留为阶段性工程检查，后者只覆盖少量 unknown 类样本，不应替代完整本地验证结果。

来源：[指定模型配置](https://github.com/ARM-software/keyword-transformer/blob/237e4097/models_data_v2_12_labels/kwt1/flags.json)、[官方 Transformer 实现](https://github.com/ARM-software/keyword-transformer/blob/237e4097/kws_streaming/models/transformer_utils.py)、[官方模型构建](https://github.com/ARM-software/keyword-transformer/blob/237e4097/kws_streaming/models/kws_transformer.py)。
