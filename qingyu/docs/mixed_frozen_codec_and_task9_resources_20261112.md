# 冻结码流混合比较与 task9 资源账

2026-11-12，只读研究，不修改任何冻结 RTL、码表或数值配置。结论：**没有足够收益支持现在转向 Huffman。更值得先检查 task9 的 X 宏配置，以及不改变接口周期的小规模状态收窄。** 本文所有 bit/宏数都是结构量，不是实测 mm² 或 µJ。

## 训练冻结的混合格式

仅使用原 `build/global_codec_budget_20261112/frozen_global_codecs.json` 中的 global Rice 与 canonical Huffman。两者预测器相同：X 逐行差分宽64、W无差分、Y逐行差分宽16。没有重新拟合或逐层/逐样本选格式。

新 `build/mixed_frozen_codec_budget_20261112/run/preregistration.json` 先列出八种组合，顺序固定 X/W/Y，R=Rice，H=Huffman；选择规则是训练集 `mean(2I+O)` 最小，同分优先更少 H 再字典序。在读取旧 validation Huffman tiled 统计前，保存 `training_selection.json`，选中 **HHH**。该选择使用原 training 的3072个任务，并完成104640条训练流实际编解码/逐元素逆变换；验证直接复用旧冻结 tiled 研究全部3072任务的实际无损往返证据。每层唯一W实际检验一次，费用则在所有任务重复计入。

I保留202词头部和数值参数；O保留18次写操作（invalidate+16length+finalmagic），每条流独立32bit尾对齐。不传每任务码表，通用固定ROM成本另计；没有免费跨任务权重复用。

| X/W/Y组合 | 训练 mean2I+O | 验证 meanI | 验证 meanO | 验证 mean2I+O | 相对RRR少的服务拍 |
| --- | ---: | ---: | ---: | ---: | ---: |
| RRR | 13682.823 | 4798.979 | 4108.358 | 13706.317 | 0 |
| RRH | 13652.174 | 4798.979 | 4082.490 | 13680.449 | 25.868 |
| RHR | 13642.490 | 4778.813 | 4108.358 | 13665.984 | 40.333 |
| RHH | 13611.841 | 4778.813 | 4082.490 | 13640.115 | 66.202 |
| HRR | 13659.416 | 4786.887 | 4108.358 | 13682.132 | 24.185 |
| HRH | 13628.767 | 4786.887 | 4082.490 | 13656.264 | 50.053 |
| HHR | 13619.082 | 4766.720 | 4108.358 | 13641.799 | 64.518 |
| HHH | 13588.434 | 4766.720 | 4082.490 | 13615.930 | 90.387 |

单独Y Huffman只省25.868词/理想服务拍，约0.189%的严格aggregate服务量。全HHH也仅省90.387拍（0.659%）。各流改变在该流量模型里线性相加，没有混合后额外隐藏的流量收益；不同硬件实现的气泡和重叠必须重新实测，不能从这张表推算。

HHH验证 `2I+O` 的P95/P99/最大为14266.9/14641.61/15512，RRR为14369/14811.38/15787。RRH最大仍15720。完整JSON保存每个组合、每个split的I/O、X/W/Y分别词数及分位数。初始loader串行时仍是`Cloader+Cengine`；本表不是新engine周期或完整吞吐。

## Huffman硬件与通用容量代价

| 流 | 最长码 | 一份直接code+5bit length表 | 通用最坏单流容量 | 本验证集最大实际bits |
| --- | ---: | ---: | ---: | ---: |
| X6336字节 | 24bit | 7424bit | 4752词 | 36855 |
| W每组2048字节 | 16bit | 5376bit | 1024词 | 15183 |
| Y每tile1584字节 | 21bit | 6656bit | 1040词 | 11567 |

原冻结Huffman没有raw escape，所以不能用观测到的最大码长总和给通用接口定容量。Y需要允许`ceil(1584×21/32)=1040`词/tile，原Rice的398词slot、prefix398上限及12722bit检查不能直接沿用；16个slot加17头词为16657词。X/W也分别超过原50886/16448bit通用输入上限。这是地址/容量范围变化，即使所有当前样本恰好落在旧上限内，也不能说无改动可替换。

Y只需要编码，四符号一拍可以做四次code/length查表，再求四个前缀长度和拼接；最坏一拍84bit，必须有足够reservoir及背压。6656bit是一份最直接表的逻辑内容，并不代表单口ROM能提供四次查表，复制、组合译码或多端口实现成本不能忽略。

X/W解码更困难：四个码字边界依赖前一码长，简单实现会串联四次prefix译码/移位。前缀小表+二级表、跨拍流水或并行边界预判都需要明确面积和时序；不能因软件可快速decode就假设四字节每拍或150MHz通过。不能把`2^21/2^24`完整表当作廉价电路，也不能从固定表内容bit数直接推导标准单元面积。

因此不建议为了Y约26拍或全部约90拍预算收益，优先引入新码流格式、容量变化、ROM与译码链。当前bounded Rice减少状态且维持原位流，风险更小。

## task9相对prefetch8：源码与XML实数

`build/mixed_frozen_codec_budget_20261112/audit_resources.py` 解析各自通过回归时保存的Verilator XML，核对结果中的XML哈希和实际SV源码哈希。时序状态通过`assigndly`目的变量识别，展开数组；不把组合中间量、输出alias、行为SRAM的数组/Q重复计为逻辑FF。该方法是声明/展开结构账，不是综合后的FF数量或门面积。

| 项目 | prefetch8 | task9 | 增量 |
| --- | ---: | ---: | ---: |
| X1024×16宏 | 8 | 9 | +1 |
| W/R/metadata128×16宏 | 21 | 21 | 0 |
| 私有宏总数 | 29 | 30 | +1 |
| 私有宏分配bits | 174080 | 190464 | +16384 |
| rawPE数量 | 128 | 144 | +16 |
| rawPE状态，45bit/PE | 5760 | 6480 | +720 |
| 顶层实际时序变量bits | 6739 | 7159 | +420 |
| 合计逻辑声明状态bits | 12499 | 13639 | **+1140** |
| 已测无背压private周期 | 9931 | 9355 | −576 |

顶层420bit增量精确为snapshot raw +368、snapshot R +21、active R +21、store_row索引+1、R读索引+1、两个X bank/group计数器+8。snapshot合计3121→3510，W burst数据/地址789bit不变且已包含在顶层账内，不再重复相加。另有16个9×9乘法器及对应加法/控制、144路结果选择、9bank装载选择和地址逻辑的组合成本，不能用FF数代替。

不要删除不同epoch的有效副本：active R供当前DOT，snapshot R供前一组输出；active C/meta供当前tile，load C/bias/shift供下一pair，四W slots保存当前/下一pair。它们不是无用途的shadow。21bit R/C和23bit pair sum对完整signed8范围必要：R最大`32×16384=524288`，pair sum最大`32×65536=2097152`，再收窄一位会丢正极值。

## 优先检查的节省候选（尚未实施）

1. **移位寄存器8→6bit**：合法shift仅0…47。`shift_load_q[32]`和`active_shift_q[16]`可合计少96个声明bit，保持8bit外部字段及原先对每个完整字节的`>47`检查；不能截断后再判断合法性。内部metadata记录仍需三只16bit宏，不能宣称因此省宏。预期不增加协议周期，错误路径、RNE和综合时序仍要验证。
2. **有序C完成bitmap的证明收窄**：当前32bit `c_complete_q` 标记所有列。W/product严格有序且不丢握手时，最后Kpair的col30/31成功product commit可作为1bit完成标志，理论少31bit。必须先证明此前所有列均已完成、错误/BEGIN/new_pair清epoch与最后product/metadata并发边界；尚不能无条件删除原防护。
3. **X宏深度浪费**：task9每个bank仅用352/1024词，9bank真正有效数据共50688bit，容量利用率34.375%。每bank用3只128×16宏可覆盖384词：27只小宏替9只大宏，整体变为48只128×16、总98304bit（从190464少92160bit）。这不是面积减少的证明。需官方实库满足`3×A128 + 每bank选择/门控成本 < A1024`，并核对读后16bit mux的STA/能耗。同步读选择器可共用，因为9个DOT bank读同一row-group；加载时仍须各bank正确选择submacro及处理bank8→bank0跨组写。保持同步一拍接口在功能上可行，但若新增mux破坏时序就不能声称不损性能。

W的16×128×16宏由四slot全部占满，不能只因当前算一个tile就删下一pair存储。R两个128×16宏有宽度/深度余量，metadata三个宏只用64个45bit记录，但R读取与下一pair metadata写可真实并发；按总bit数把它们合并成同一单口存储会引入仲裁，不能作为零周期代价的直接替换。

上述资源改善必须在新候选中实施和回归；此研究不修改冻结task9/prefetch8。官方库面积/功耗、完整SoC时序和loader窗口仍待实际测量。

## 证据

- 混合码流结果：`build/mixed_frozen_codec_budget_20261112/run/result.json`，SHA256 `39bb5fd9da9187106b4bdd1d3c34d0adeba585a4a7f740f09fb82070d0d0a232`。
- 训练选择：`training_selection.json`，SHA256 `72758d3fe0bd9f29a3beb3e67471dc8789cd9a58337fc6618bb189e3596af1df`，先于读取验证Huffman统计写出。
- XML资源逐项表：`build/mixed_frozen_codec_budget_20261112/task9_resources.json`；可复跑脚本为同目录`audit_resources.py`。
- prefetch8完整回归：`build/winograd_task8_prefetch/20261111T172625810973Z/result.json`。
- task9完整回归：`build/winograd_task9/20261111T173951031071Z/result.json`。

资源解析器初次误把旧结果的aggregate字段当作`passed`，已保留`audit_parser_failure.json`；修正后检查`completed`、三个seed各自`passed`及XML哈希。这是审计脚本schema问题，没有修改或判失败任何RTL。旧Yosys前端产生的异常小codec库存属于另一个独立审计，不用于本资源账或任何面积结论。
