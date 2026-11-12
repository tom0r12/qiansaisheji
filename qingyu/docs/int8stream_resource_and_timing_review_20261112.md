# INT8 streaming 资源、协议与完整时窗审查

日期：2026-11-12，Asia/Singapore。只读审查；没有修改 engine、core、codec、transport 或冻结候选。此文记录源码状态及局部验证证据，**不是综合面积、150 MHz STA、能耗或官方成绩**。

## 结论与优先级

1. 冻结串行 task8 核完整实测 **21,827 拍**，仅核本身已超过 `150,000,000 / 10,450 = 14,354.066985645934` 拍预算。系统还有包头、编解码填充、总线等待、输出收尾和 E203 调度。目标要求的是同一实现的吞吐、面积、能耗三项同时通过。
2. snapshot 加当前组 R 与 DOT 并行读取，可以改变真实串行依赖。审查后追加的独立原型已通过完整三种种子回归，实测 **13,891 核周期**；只剩约 **463.07 拍**系统余量。随后真实 E203 首层完整工程窗口为 **14,469 拍**，仍超过目标；详见末尾追加证据。不能把仅原始乘法 6,656 steps 当完整任务周期，也不能简单将所有 codec 周期再串行相加。
3. 如果严格窗口要求“整包先写入共享 SRAM，然后才 START”，即使 13,891 理想核周期实现，当前 12 包平均仍至少 `4,547.8333 + 13,891 = 18,438.8333` 拍。充分重叠假设下的 `2I+O` 总线服务下界，不适用于这种串行 loader 控制流程。
4. 已发现并向 root 报告下一 tile 合法 pre-offer 被误判为输出错误的问题。root 已把输入限定为 `output_index < 396`，身份检查改成真正握手才检查；静态复审通过。持续写背压测试仍须验证修正后的完整实现。
5. 声明级资源清单为私有 SRAM **174,080 bits**、当前新引擎层级约 **18,766 retained state bits**，另有共享 read-ahead 的 121 bits 和 bank 选择 5 bits。它们不能换算成已测 mm²/µJ；大量乘法、加法、选择器、512-bit 移位/解析逻辑不在状态位数内。

## 审查版本及证据

| 对象 | 本次读取的身份/结果 |
|---|---|
| `experiments/integration/int8stream/qingyu_int8stream_engine.sv` | SHA-256 `3e7e790894ef20a1f798ca77ce7c58ff81fa05a7d8d4014944c017c52b4247b8`，开发中的快照，非冻结版本 |
| `experiments/integration/int8stream/contract.json` | `6ac8b4a35f1c44876d5754333d6c570e3f039ae88830bb0303c6b8f02d7a1c80`，包含开始时清 marker 的新增写事务 |
| `experiments/arithmetic/winograd_task8/winograd_int8_task8.sv` | `b94868d460ef57ed4f878b2e6c683f01430298485fc981c4b6d337f86a268ac3`；完整 SOURCE 清单 `48b0f3e70b4ab0fd18b45d28b497cedf9ac7d7da6fab71b23b7dd90a1cf34ece` |
| task8 全量验证 | `build/winograd_task8/20261111T170054752807Z/result.json`，`3f7d4521b53b00797e56b7629efbfa64bba238290e1007869fc44bb4dc14570b`；12 原始验证层 + 10 合成全任务、三种种子通过；无背压均 21,827 拍 |
| task8 四态首层 | `build/winograd_task8_four_state_smoke/sim.log`，21,827 拍、6,336 输出词、R99/C256 和 25,344 个舍入前累加值通过 |
| 独立 overlap 核追加结果 | `build/winograd_task8_overlap/20261111T170956926062Z/result.json`，`58ab63d20042bc87ef6374008d9a63b3edbb5d2e4495fb0d385cc34b0de9ea66`；三seed通过、13,891拍；SOURCE清单 `2a94f2369b24e3b8b0f3181e0f65f49d19a4e47b73449ad1a6457909899c85c3` |
| 输入/预期包 | `build/int8_packets_20261112/result.json`，`1a3dd891f7b1e2b5345f505cc801b77e3947aff130680994c54189ab33d6a2ad`；本次独立逐项检查了 12 层 36 个包/预期文件哈希 |
| codec/adapter/transport | 各自冻结目录中的 `SOURCE_SHA256.json`；不重复把独立测试称为整机验收 |

当前 packet 保存的 contract hash 是生成时旧版，不包含后来加的 marker 清零事务；最终镜像字节未因此改变，但真实总线写次数 **增加 1**。本次所有 wire budget 均补入这一笔，未改旧产物。

这 12 个包均为各层 validation sample 9。该 sample 是生成静音；它是实际模型张量的精确数值/协议测试，但不能代表完整语音分布的压缩比。更广的 3,072 任务预算单独列出，不把重复 seed 算成额外独立模型样本。

## 数值、地址及容量约束

- 格式仍为冻结 `x8_w8_y8_h0`：signed8 X/W、signed16 bias、channel shift 0..47、ties-to-even 后 signed8 饱和。打包与 Rice 都无损，不重新训练参数。模型 bias16 必须是原整数 bias 的精确表示，不是另做裁剪。
- Winograd 配对项 `(x_even+w_odd)*(x_odd+w_even)` 两输入范围为 [-256,254]，需要 signed9；产品需要 signed18。32 项累加绝对上界不超过 2,097,152，signed23 足够。R/C 各为 32 个 signed8 产品之和，范围 [-520,192,524,288]，signed21 足够。减去 R/C 再加 signed16 bias，保守中间上界 3,178,496，signed24 安全；最终直接 dot+bias 的范围更小。不能把此证明套到旧 signed48 bias 任意全范围。
- 输入头 202 词：10 词格式/长度 + 128 bias + 64 shift。X 合法位数上界 `6336*8+ceil(6336/32)=50886`；每 W 组 `2048*8+64=16448`。decoder 同时验证长度、尾 padding 和规范 raw escape，不接受任意超长 unary。
- 输出每 tile 1,584 bytes，最坏 `1584*8+50=12722 bits`，398 词槽足够。16 槽 + 17 最终头词共 6,385 词/25,540 bytes 的地址保留量；不能把整个 allocation 当实际都写了。
- 最新 wire 操作有 **18 次头写**：开始清 marker 1、16 个实际 bit-length、最后成功 marker 1。最坏 payload 6,368 词，所以最坏 output 写操作为 6,386 次，比最终地址数多一次。
- source/output 对齐和 shared 范围用 35-bit 加法检查；所有 W 地址求和及 source/output 整区不重叠校验完成后才开始 payload。最多输入 `202+1591+8*514=5905` 词。未发现当前上界中的 32-bit wrap 漏检；后续扩大尺寸必须重做该证明。
- 无效 descriptor 不修改输出。复用旧输出地址时，成功的范围/格式检查后先实际写 0 并等 ACK，故开始执行后的部分失败不能留下旧成功 marker。调用者仍必须看本次 error/done，不能只读一个可能预存的 marker。

## 完整时窗与错误协议

建议同时保留三个可复核边界，而不是同名混用：

1. **preloaded 工程窗口**：本次 accepted START，显式共享 cache clear、core BEGIN 冷 epoch、header/metadata/X/W 真读取、全部计算与压缩、每个输出 payload/length 写，到最后 marker 的 originating ICB response ACK。共享 source 在 START 前预装的时间明确排除。
2. **engine completion 窗口**：同一起点到 engine `done`。按当前 NBA/FSM，最后 ACK 在 R，transport R+1 置 `wr_done_valid`，engine R+2 消费。因此预期比第 1 窗口多 2 拍；应由 TB 实测并断言，不能声称两窗口完全相同。
3. **strict loader/SoC 窗口**：若以实际外部加载起点计，从第一个真实输入写开始，包括 loader、E203 指令/MMIO 调度、所有等待，至真实最后结果写回 ACK。题面相关起点没有把具体 host/共享 loader 握手钉死，本地缺完整官方 loader，仍是 OPEN。不能直接删除历史 source→live copy 而把预装工作消失；新 engine 使用单份共享数据并真实读回，是新的明确工程模型。

CPU IRQ、MMIO WAIT 返回和 engine `done` 都可能晚于最后 ACK，需另标返程延迟。不能把 CPU、厂商 SRAM 或共享接口从全 SoC 能耗中删去。

错误时 `abort_now` 立即停止 transport 新 offer，已 offered/accepted 的外部命令保持身份并真实排空。内部 pipe reset 同时作用于 core/decoder/reorder/encoder，允许取消它们之间的私有流；外部 transport 不 reset，ABORT_DRAIN 消费已有读 FIFO 并等待总线归还。此处不是伪 ACK。

若 slave 永久不返包，`TIMEOUT_CYCLES` 可以使 error 状态有限时间变成失败，但 **done/busy 不能假装已经排空**。当前 ABORT_DRAIN 会继续 busy，下一 START 被拒绝。MMIO wrapper 应能报告错误及 busy/draining，并保持自己的控制访问有界；不能把该现象描述成 DMA 已恢复。TIMEOUT 参数需为正，永久 stall 与恢复后 restart 都应测试。

## 声明级资源清单：避免重复计数

下表为当前 RTL 的 retained 状态手工分类，不计 always 块内先赋后用的组合临时变量，不把 SRAM 行为模型 `rdata` 再当一份矩阵缓存。实际综合可能因固定 k/row 常量和未使用 telemetry 剪枝，故它既不是最优面积，也不是门级 FF 数承诺。

| 独立实例/状态 | 当前声明 bits | 组成及边界 |
|---|---:|---|
| 128 raw pair lanes | 5,760 | 每 lane product18 + accumulator23 + pipe/first/last3 + out_valid1=45；out_pair_sum 是 accumulator 的别名，不再加23 |
| core 其余 retained state | 2,805 | 加载 C/bias/shift 1,440；active C/bias/shift/R 888；R累加42；R待写值/tag/count65；两乘法 product/tag49；C完整位32；slot/epoch21；FSM/读tags65；group/完成flags11；六计数器192 |
| Rice encoder | 3,284 | history2048 + 两32B block512 + reservoir512 + output/control/counters212 |
| Rice decoder | 2,813 | history2048 + reservoir512 + output/control/counters253 |
| rowpair adapter | 2,133 | 64×32 data2048 + control/counters85；无另一个输出数据寄存器 |
| prefix transport，8/16/8配置 | 1,202 | 读FIFO512 + 写FIFO256 + read-last16 + owner标签16 + held command67 + pointers/计数/descriptor/状态335；不能漏 held payload，也不另加398词tile buffer |
| 当前 engine FSM/包地址/长度 | 769 | 含 W bit-length8×32、W base8×32、source/output/X bits、35位cursor、packed_index11、output_index9、状态与计数 |
| **engine层级 subtotal** | **18,766** | 不含以下 SRAM 宏、共享控制器、E203/fabric/MMIO/新仲裁；没有同时再加旧 opt33 FIO/accel |
| shared read-ahead 控制器 | 121 | 两tag/有效位、cache_data32、held response32和响应属性；look entry 借用当前宏Q，不凭空再加32-bit data RAM |
| 512KB物理 bank 选择寄存器 | 5 | `qingyu_banked_sram` 的32-bank read select；decoder/mux组合逻辑另计 |

泛化 codec history 各为256B。当前常量格式实际只需要 X 前一行64B和 Y前一行16B；未来专门参数化或可靠常量传播可能缩减，但本表没有预先把可能优化当已实现。类似 decoder/encoder/adapter 的部分32-bit telemetry 输出未参与 engine 控制，可能被剪掉；不要先减后又在综合结果里减一次。

| 私有宏用途 | 实例 | allocated bits |
|---|---|---:|
| X | 8 × 1024×16 | 131,072 |
| W，四个地址槽 | 16 × 128×16 | 32,768 |
| R99 | 2 × 128×16 | 4,096 |
| C/bias/shift | 3 × 128×16 | 6,144 |
| **私有合计** | **29 macros** | **174,080 = 21.25 KiB** |

这些是实际 RTL instance 尺寸和项目行为 SRAM 接口，仍需正式综合中绑定真实厂家宏。不能把行为 `mem` 展成 FF 后仍按宏面积报分，也不能把宏 Q 和行为 rdata 的同一功能再计为一整套外置 SRAM。

固定共享512KB对应64个4096×16宏：复用范围可按正式规则从新增面积扣除，但这些宏、CPU TCM、E203、原总线的能耗全部保留。新增 read-ahead、MMIO、merge、decoder、mux 和任何 FIFO 都不能归入旧平台扣除项。最终应从完整衍生 SoC 实例树分类，不能拿本表取代面积报告。

独立 snapshot 原型增加 raw sums `128×23=2944` 和对应 `R8×21=168`，即 **3,112 数据位**，加 group4/tile4/valid1 共 **3,121 位**；复用原store row/word控制。当前 active R 供当前 DOT，从独立 R SRAM读取；snapshotR供上一组输出，因此不是再悄加第三套 R。C/bias/shift 保持整 tile 到最后 snapshot 输出 ACK，不在128个PE内复制。该新增数未并入上表串行版本subtotal。

## 哪些工作可重叠，哪些目前仍串行

| 路径 | 当前真实关系 | 可审查的后续条件 |
|---|---|---|
| shared read → decoder → rowpair → private X/W | 已按 ready/valid 流水；首行/块填充和背压真实存在 | 不能把四者完整周期串行求和，也不能漏首填/末排空 |
| X/W私有写 → R/C两乘法 | 已同实际装载握手产生 factor，写队列/缓存提交仍计时 | factor不是软件预计算，不再另加一遍全部factor乘法周期 |
| core DOT → STORE | 当前串行，35拍DOT后32拍满组STORE（尾组12拍） | raw/R snapshot和独立output上下文才能重叠，3,112bits新增成本必须计入 |
| R SRAM读取 → DOT | 当前R_READ/R_WAIT串行 | R宏与X/W宏独立，当前组前8/3拍读R可与32拍DOT并行；需要独立响应tag和生命周期验证 |
| core STORE → encoder → compressed write | 已流式重叠；encoder接受最后原始词后仍有flush/真实ACK | 连续write背压可传回core；tile length与下一START不能凭encoder done跳过ACK |
| 下一tile内部计算 → 上一tile压缩flush | core可能已推进，允许下一tile合法held valid | engine必须拒绝超出396次当前tile的输入；已修复的pre-offer检查须持续背压验证 |
| 下一W组加载 → 当前DOT | 当前没有；engine等旧两tile payload/length完成后才decode下一W | 四个**地址槽**不产生端口。DOT每拍读全部16个W单口宏，新W词写其中2个宏会冲突；需真实idle-slot仲裁、stall或另加物理bank |
| transport read与write | transport支持并发 | 当前engine FSM读阶段与输出阶段串行，不能用transport能力宣称已重叠了整组W预取 |

当前串行周期分解为 `5888 + 259 + 2064 + 7280 + 6336 = 21827`。其中6,656个配对主步为 `16 tiles × 13 rowgroups × 32`；7280含每组3拍管线/完成开销。cache2064含16×17 metadata读和16×(99+13) R读/等待。

与架构代理协调的独立 overlap 分解：`5888 load + 259 commit + 272 metadata + 7280 DOT + 192 tail-store = 13891`。R读并入本组DOT；每tile前12组32词输出可被后续35拍计算覆盖，最后3行12词不能凭空省掉，所以尾store为16×12=192。四态首层及后续完整三seed结果均一致：1,584次R读在DOT内，208次snapshot，6,144输出词与下一DOT重叠；三seed还分别覆盖382/383/382次旧snapshot末ACK与新capture同拍替换，以及64拍双context满stall和reset。该private结果本身不含codec/reorder初填、实际总线miss、engine状态转移及CPU调度；后文另列随后获得的整机首层证据。

即使给满组每35拍中的3拍全部用于W预取，每pair共26组也只有约78个idle拍，而下一W组需要512个decoded word接受；四槽本身远不足以把全部下一组装载隐藏。若增加物理双buffer，需要明确额外宏数、写端口、C factor epoch和能耗，不能把地址双buffer误当带宽双buffer。

## 原总线的条件服务下界

令 I 为整个输入包实际词数，O 为 payload + **18次头写**。R1/W1意味着读命中/写提交可每拍服务；冷miss、CPU竞争、descriptor边界和返回延迟全部还未加入。R2/W1沿用原fabric接同步读/同边沿真实写ACK的已测能力边界。任何一项都不是完整任务实测。

| 窗口/条件 | 服务下界 | 当前12个静音包均值 | 完整3072任务均值 |
|---|---|---:|---:|
| preloaded，R1/W1 | I+O | 7,845.0000 | 8,907.3376 |
| preloaded，R2/W1 | 2I+O | 12,392.8333 | 13,706.3171 |
| strict loader也写一次，R1/W1 | 2I+O | 12,392.8333 | 13,706.3171 |
| strict loader写一次，R2/W1 | 3I+O | 16,940.6667 | 18,505.2965 |

当前12包 `I_mean=4547.8333`、`O_mean=3297.1667`。完整3072任务来自已冻结 tiled budget，`I_mean=4798.9794921875`、`O_mean=4108.358072916667`，只增加了marker invalidate这笔写，没有重新拟合或修改格式。全分布 strict R1/W1 理想余量仅 **647.75拍**，仍没有含任何不可重叠工作；不同样本有不同bit数，不能只用静音包的余量代表全集。

若 loader 必须先完整写完再允许START，其服务与engine流水不能重叠：

`C_strict_serial >= C_actual_loader + C_engine`，并且即使理想one-write/cycle也有 `C_actual_loader >= I`。

用13,891无背压core周期作为全分布条件值，12包下界18,438.8333，完整分布18,689.9795，均失败。若未来允许边加载边计算，必须有真实官方接口/数据就绪协议、同一总线竞争及最后loader ACK证据；不能靠预置内存、提前START读取未写字节、隐去CPU初始化指令来获得上述重叠。

## 下一步证据要求

先验证 snapshot/R并行的新完整核，再接同版engine复测；记录每个阶段真实ready/valid交叠、W宏仲裁、最后marker ACK以及task done差值。预注册正常/长背压/错误后restart/永久失联的边界测试。随后用非静音和完整验证分布测数据依赖压缩流量，最后才是同一综合网表、真实厂家宏与指定 SCC40NLL_RVT 库的150MHz时序和全SoC能耗。

本审查不建议更改官方fabric、不扩宽共享端口、不改变精度或任务分母。当前存在可实现的阶段重叠方向，但尚无同时满足三个验收指标的证据。

## 后续追加：MMIO 与真实 E203 证据

原 `int8soc` FIO 的 blocking WAIT 只等 `!engine_busy`，在永久不返回的DMA上会使CPU看不到已发生的timeout；STATUS又只在done时锁存error。本次独立审查已报告，root修成active error可读、WAIT可返回busy+error，后台仍真实排空。这里的有限返回没有伪造done或ready。

自有 `experiments/integration/int8soc/tb_int8stream_fio.sv` 和 `run_mmio_checks.py` 使用**真实 engine/core/codec**，外接仅用于MMIO隔离验证的有序RAM端点。最终 `build/int8stream_mmio/20261111T171826155350Z/result.json` SHA `c5960f73be88be9dc601c3d8226f81bbfae1b36f0c10905133942a9b4850323c` 通过：

- 三seed各8场景、80次MMIO，96拍独立deadline；覆盖全部非法partial mask、held response、busy配置拒绝、未accept命令永久阻塞、已accept响应永久不回，以及WAIT错误响应held期间DMA恢复、状态保持、排空后restart。
- 长deadline真实layer00连续两个完整任务及一次真实bus error后重载，共三个完整成功任务；每次4,522读、3,357写，全部6,385输出槽与source不变检查通过。该隔离RAM端点下计数22,326，**不能当官方fabric或CPU性能**。
- DUT FIO SHA `9a10d1474981537c8f288be12d47e90068acb7860244369698792d5fc83dd8ea`，engine为本表快照。编译/运行前后源码哈希相同。
- 旧 `171709884767Z` 失败已保留：Icarus对中文绝对路径plusarg产生不可打印字符，使`readmemh`失败。仅runner改为已验hash的ASCII相对文件名后重跑；没有放宽测试期望或修改DUT。

新增 FIO 自身声明142状态位。衍生top保留 `NP=2, OUTSTANDING=4, ONE_PER_PORT=01` 的CPU/DMA merger，声明85状态位，仍须计新增面积。拓扑已只读核对：唯一engine DMA → 新CPU/DMA merger → 原 `e203_subsys_mems` → 单sysmem shared入口；旧六主仲裁不在新top。MMIO走独立sysfio，WAIT不占用这个数据入口。

对 root 已PASS的真实 E203 结果做了独立read-only核验：

| 实际整机证据 | 首CPU source-pointer命令接受至末marker originating ACK | START至末ACK | engine done与末ACK差 |
|---|---:|---:|---:|
| 串行core，12层平均 `build/int8soc/20261111T171723244199Z/result.json` | 22,404.3333 | 22,392.3333 | 每层2拍 |
| overlap core，首层 `build/int8soc/20261111T171723243779Z/result.json` | 14,469 | 14,457 | 2拍 |

两份结果SHA分别为 `fc2552ff758c8b132730a7ce3a2ded3e7f87f14d3bb6108ccc2f1466a33265fb` 和 `d5dfa640f4a2ab39ecfb636f516396f3b6e9d5f1033dcb20af1562b29e2aedd9`。overlap首层在未签核150MHz换算 **10,366.9915 task/s**，仍小于10,450；差114.933拍完整工程窗口。72任务语料检查当时仍运行，未提前写通过或总体均值。

核验内容：152份实际compiled source及3份被include文件全部匹配记录；二进制和各层日志hash正确；`firmware64.hex`逐词还原的8192×64-bit little-endian内容与`firmware.bin`补齐64KiB逐byte相同，符合官方ITCM DW64/DP8192及0x80000000链接地址。没有把32-bit程序字误装成64-bit存储单元。每层 `engine_counter = START_to_ACK + 2`，首pointer至START差12拍。所有输入恰读一次、源响应逐值检查，实际输出写/ACK数、未使用输出槽、source不变和整个共享guard空间均检查；仅四个明确的post-task CPU diagnostics词排除guard比较。

`cpu_setup_to_ack` 的精确起点是第一个source-pointer MMIO实际接受边沿，不含之前ID读取、mcycle采样和形成参数的指令。另报`firmware_cycles`，并保持loader exclusion，不能把它称为官方完整初始加载窗口。

当前证据无新增阻断项。下一版runner硬化建议（不修改正在运行的源）：reuse应比较有序logical filelist/template hash而不只比较源hash字典；目前同一模板已实核一致，但未来只改编译顺序可能漏拒绝。明确prior passed或compile-only复用合同。TB可加fabric/shared的wmask逐笔相等及末ACK后至HOST禁止新DMA；当前静态RTL未见这些违规，不据此否定已验证的结果。
