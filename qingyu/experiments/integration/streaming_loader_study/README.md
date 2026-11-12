# 完整装载窗口与流式生产者研究

结论：在原 32 位 fabric 和单共享 SRAM 入口不变的条件下，**安全重叠装载与计算在协议上可行**。优先实施独立条件模型：首 202 个源词成功写 ACK 后 START，后续每个读 descriptor 只有覆盖的全部源词已成功写 ACK，才交给现有 transport。输入数据仍真正写入共享，再通过原总线读出；水位只提供有效性，不传送数据。这是待实测的最小改动，不是已经可用的官方 loader。

当前官方 loader 的具体端口、并发能力和速率在已检查的本地资产中未找到。预装后 START 的整机结果不能替代它。本研究不改任何冻结 RTL、官方源/参数、数值配置或已有结果，也不启动远程作业。研究采用 `chip-design-architecture` 的需求/假设/下界分离方法；不借估算给出面积或能耗结论。

## 一手证据与当前边界

原件是工作区提供的竞赛说明 PDF，不属于本 Git 仓库，因此不会随代码分发。`evidence.json` 记录原件 SHA-256、页码和本地摘取文件哈希，用于核对研究依据；派生的逐页文本和图像只保留在本机。本文只概述与计时窗口和平台接口有关的要求。

- 物理第 3 页/页脚 2 的图把 SRAM 放在 System Bus 的从设备侧，图本身没有给出参数 loader 的具体协议和速率。
- 物理第 4 页/页脚 3 明确采用组委会平台总线/外设、共享 512 KiB、统一 150 MHz；“组委会提供参数加载仿真环境，通过平台已有访问接口向共享 SRAM 写入参数和输入数据”。它没有写明完整参数包必须写完才能 START，也没有提供并发端口许可细节。
- 物理第 12 页/页脚 11 明确从输入和参数开始装载到结果全部写回计时，任务开始前清空数据和参数缓存，参数装载、总线等待及 E203 调度全部计入。吞吐是完成任务数除以总时间，每次精度须单独过 3%。一次性文件格式转换不计入，不意味着可以把硬件因子计算或运行时搬运移到窗口外。
- 本地 pinned E203 清单 `reports/e203-source-manifest.json` 是 137 项公开 RTL/LICENSE 的校验记录，不是官方加载环境交付记录。`e203_subsys_mems.v:33` 是 CPU memory master 入口，`:46` 是 sysmem slave 出口，`:72` 的 DM 也是被该 fabric 访问的从接口。`sirv_debug_module.v:70` 的 `i_icb_*` 是输入命令，`:434` 的 “agent” 注释不能证明存在一个可持续一词/拍向共享写入的独立 loader master。
- 当前 `experiments/integration/int8soc/tb_int8soc.sv:44` 读 fixture 文件，`:47–48` 在复位前直接给 shared 行为数组赋值。`soc_main.c:17–21` 只写指针、START、阻塞 WAIT，不执行参数初始加载。实际整机 CPU 首配置→最后 ACK 的周期有效，但明确排除了这次预装。

“未找到”只限定本地已查 PDF、公开 vendor snapshot 和项目 TB/驱动；不能推断组委会没有该环境，或从示意图推导某个未见端口已可使用。

## 已知测量与可证明下界

`analyze.py` 从冻结 tiled Rice 的全部 3072 个验证任务重新逐项计算，无新拟合、阈值选择或格式改变。保留全部层/样本数据于 `budget.json`，可以用 `python experiments/integration/streaming_loader_study/analyze.py` 复算。该命令仅重生成本研究目录内的证据。

令 I 为输入完整包词数，O 为最终输出唯一词数。现 engine 另写一次 magic=0 作冷启动失效标记，所以实际输出写次数为 O+1。初始源写、源读和输出写全走一条原总线时：

```
C_service >= 2I + O + 1                 (每类命令理想一拍)
C_service >= 3I + O + 1                 (读仍为两拍，写一拍)
C_strict_serial = C_loader + C_preloaded_engine + 未计入的真实调度
C_strict_stream >= max(总线/宏服务下界、真实计算/codec依赖下界、真实loader供给下界)
```

最后一个式子只是必要条件，不能把 max 当成可实现周期；因果依赖、启动、仲裁、读未命中和尾排空还可能增加。原 read-ahead 用同一物理端口，宏访问次数和有效总线命令次数也须分别核对，不能把预读称作免费读口。

| 项目 | 最小 | 平均 | P95 | 最大 |
| --- | ---: | ---: | ---: | ---: |
| I | 4471 | 4798.9795 | 4932 | 5170 |
| 实际输出写 O+1 | 3280 | 4108.3581 | 4520 | 5461 |
| 理想严格服务 2I+O+1 | 12231 | 13706.3171 | 14369 | 15787 |
| 读两拍严格服务 3I+O+1 | 16702 | 18505.2965 | 19299 | 20950 |

150 MHz / 10450 = 14354.067 拍；超过目标需平均周期严格小于它。R1/W1 均值只剩 **647.750 拍** 给所有无法重叠的工作。即使其它开销为零，平均每次输入读的服务成本也只能小于约 **1.135 拍**。3072 个任务中 165 个的理想服务下界已超过目标，原始逃逸格式的合法最大服务量是 18196 拍。这不等于吞吐按 12 个抽样平均必败，也不支持对未知抽样保证达标。

真实 task9 首层 `build/int8soc/20261111T175515904061Z/result.json`：I=4522，输出写3357，CPU窗口9616，core9573=load2264+factor141+cache272+compute6320+store576，宏读4547。该样本是生成静音。给它加理想串行初始加载4522拍得到14138拍，只是条件算式；不能推广到其它声音或叫已测严格成绩。全部72任务的新 E203结果由 root 单独维护，不在本研究中替换或重复启动。

## 三条明确路线

| 路线 | 改动/证据要求 | 能解决什么 | 主要代价或限制 |
| --- | --- | --- | --- |
| A：完整真实装载，再 START | 独立模型用原总线实际写 I 词，等全部源 ACK 后 START；冻结 engine不变 | 给串行窗口建立可比较的基准，消除数组预装假设 | 必须支付真实 Cloader+Cengine，不能用服务 max 掩盖串行依赖 |
| B：整 descriptor 提交水位，推荐首做 | 新 engine 只加提交尾地址/loader错误输入和 descriptor valid/ready 门控 | 在加载 W 后半段时运行已准备 X/前组 W；不占坑、不改 transport/核 | 每段需完整落地后才能读；真实 loader/CPU并发仍待平台证明 |
| C：逐词提交水位 | 在新 transport 的 `read_eligible` 中加单词可用判定，并维持原 held payload/credit/公平性 | X/W段内部也可边写边读，减少整段等待 | 更多协议变化；读紧贴生产端时预读可能读到未来 poison，再被写失效，R1会退化；更高验证代价 |

不推荐在 shared slave 看到未装载读后才拉低 ready/扣住 response。这笔读已经进入原 OUTS=1 splitter 时，随后生产者写可能永远到不了 shared：消费者等写，写等消费者释放，就是总线死锁。门控必须发生在 master offer 之前。也不推荐一个固定延迟后盲 START；任意 producer 背压可击穿时间假设。

## 推荐 B 的准确接口与生产者契约

机器可读细节见 `contract.json`。拟加两根同钟输入：`loader_committed_end[31:0]` 是已成功 ACK 的连续源前缀的字节排他尾地址，`loader_fault` 是该生产 epoch 的 sticky error。它们只有有效性和错误元数据，不能向私有核传送源数据。真实平台若异钟，须另作原子 CDC；不能把多位总线直接跨钟。

1. 冷 task 先清私有数据/参数/因子 epoch；共享源区不能在 t0 前隐藏预填。本地条件模型可把整个 shared 初值设 poison，这不是加载数据。
2. 生产者严格递增、对齐、全 mask、每词一次，先202词固定前缀，再 X 和8个 W group；不存在 source→live 重复副本。序列是现有一次性冻结格式，因子和计算仍在实际硬件内完成。
3. 命令 offer 被背压时保持 valid 和 payload；accept 不代表上游成功完成。只有匹配的成功 **producer originating response handshake** 才推进 committed_end；错误不能越过失败词。多在途时必须有响应身份/FIFO，不能用命令计数代替提交水位。
4. 第202词成功 ACK 后才可 START。首202词含所有 bias/shift，以后跨地址读取 metadata 无须另设洞位图。更早从10词 header START在理论上也能安全，但必须同样 gate全部元数据，额外收益最多192个已计入装载周期，首版不增加此复杂度。
5. 用35位算 descriptor_end=base+count×4。只有 base≥source_base 且 end≤loader_committed_end，才把读 valid交给 transport；返回FSM的 ready也必须与available相与。不能只 gate valid却让FSM提前离开REQ。写方向不受水位门控。
6. descriptor一经接受，其全部词已经提交，现有 transport可正常持有/排空。之后loader失败走现有abort路径，不撤任何已offered/accepted bus命令。禁止在旧epoch排空前清水位或重设指针。
7. 最终成功仍由所有输入读响应、16个payload/length ACK及最终magic写的真实originating ACK确认。错误必须抑制成功marker，并保持双方已offered/accepted请求直到排空；单有core.done不足以宣布任务结束。

单调前缀使状态保持较小：尾地址/计数、epoch/error、比较器和producer响应身份是必要成本；首版不需要整包数据FIFO或每字bitmap。若实际loader允许乱序、部分mask或反复写，则这个小合同不再适用，必须加入byte有效性/洞跟踪或由实际驱动发布已提交段。不能把此限制悄当官方输入能力。

当前 firmware START后立即做阻塞WAIT。如果同一E203还承担剩余源store，WAIT会挡住生产者，无法靠硬件watermark自行解除。该情形的driver必须先推进/完成生产再WAIT；独立loader可并行，但独立入口目前未证实。CPU从哪里取得数据、相关输入事务/指令时间也必须计入，不能在ITCM/寄存器里藏完整任务参数然后从后半程开表。

## 独立条件实验的分工与矩阵

root负责新gated engine，portable负责新TB/runner；本代理仅定义合同，不重复实现大工程。旧 bare `int8stream_dual/tb_int8stream_engine.sv:44` 直接 engine→memfab，并没有实际闲置CPU端。新TB须显式实例化生产整合的原 `qingyu_icb_merge`，让loader模型占port0，engine占port1，再进入完全原样的memfab和shared。没有第三master，没有shared旁路，source文件数组仅驱动loader总线数据。

必须先测当前生产参数 `NP=2, OUTSTANDING=4, ONE_PER_PORT=2'b01`。它把CPU侧限制为一笔在途；模型即使持续offer，也未必一词/拍accept。另一个 `ONE_PER_PORT=2'b00` 仅在独立报告中表示有排队能力的平台loader条件，不能称当前CPU行为，不能改vendor参数或并入正式候选冒充已确认许可。两种都给producer自己有限信用，响应顺序逐笔检查。

初测至少用sample0/9/202的层0，稳定后十二层，prefetch8/task9都作A/B。每种核对串行(A)和descriptor流水(B)，同包、同源、同总线/credit和随机种子。主计时从首源写 **offer** 到最终engine magic ACK，并额外报告首accept和首ACK起点，避免初始背压被吞掉。同时报START窗口、producer完成时间及精确原始tick；真正官方窗口待实际loader确认，不能用最短的一列代替。

主检查须逐笔关联 producer/engine→merge→official fabric→shared→originating response。完整正常任务的架构事务总数是 `I + I + O + 1`。所有输出/源读对不可变参考、source不可变、unused输出槽与整个shared guard、所有mask/错误、冷cache、多个连续epoch、producer未来数据与read-ahead失效均检查。特别延迟第201/202词及各流末词的ACK，确保不早读、不中途占住fabric；加载错误和输出held并发时须排空且禁止成功marker。

## 计算/控制的后续价值与风险

不再盲扩大阵列。task9精确99行并将配对PE从128增至144，在私核9355对9931省576，但真实首层只省470，其差额已落在factor/metadata等待。root的新72任务观察只平均省约191拍，说明系统依赖比空载计算峰值更重要。新loader对照应保留8行，不能预设9行更优于面积目标。

- **先消除loader串行等待。** 它有数千真实初装词可重叠，但同一总线上的 I 次写不会消失；必须检查可用读和写交织是否保持read-ahead命中。消费者若紧追逐词生产，预读到尚未写词后再被生产者写失效，会增加miss。B的完整段门控天然给顺序读留下领先量。
- **metadata预取/上下文值得小范围后续验证。** 现每tile16次M读+同步收尾，共272拍，且32条metadata写后才整体slot有效。已有active C/bias/shift是16×(21+16+8)=720bits；加第二上下文可在前tile DOT时预取，但不能把这些寄存器或读口当免费。严格最高只能先按≤272拍可隐藏量列上界，不能把factor141和cache272直接相加承诺收益。
- **不加数据影子的偶tile直接metadata路径可另立候选。** 加载已有C32/bias32/shift32，偶tile开始时可考虑将其中16项复制到active16并只将奇tile16项写Mcache，减少一半M读/写。必须新增显式epoch/消费握手，证明下一组loader没有提前覆盖来源、旧snapshot已最终ACK，才能免重复保存。仅看当前周期相邻关系不足以证明安全；首版loader实验不混入它。
- **不要删掉DOT间隙当纯收益。** W是16个单口宏，64次256bit burst/每双tile都靠非DOT读边沿实写。task9的每快组35拍与输出36词已经近输出极限，部分间隙正用于W预载。减少间隙可能把等待转到下一组而非缩短任务。
- **控制小泡收益有限。** 当前engine约30拍启动/收尾及每段descriptor、header、length、magic真实ACK不能统统删掉；CPU实际调度/错误检查也不能移出计时。先按profile识别未被供给/输出隐藏的边沿，再建有界候选。

这些是结构建议，不是已实现或已测收益。全部源/参数保持冻结；150MHz、面积0.5mm²、全SoC能耗6.3µJ仍需同候选、同窗口、同网表证据。
