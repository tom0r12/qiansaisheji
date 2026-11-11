# 优化 A：输出预读 FIFO 加深（outfifo）

基线：`experiments/h1500v/wbank2/rtl`（12 层平均 **94,085.67** 拍，1,594.29 层·s⁻¹）。
本实验：`experiments/h1500v/outfifo/rtl`，**只改 `qingyu_accel.sv` 的预读 FIFO（2 → 8 字）**；
`qingyu_fio.sv`、`qingyu_accel.c`、`soc_perf_main.c` 与 wbank2 逐字节相同（sha256 见
`build/outfifo/build_manifest.json`），`experiments/h1500v/rtl/` 与 wbank2 原文件未动。

## 结果（12 层，Verilator 全 SoC + 官方 304,128 输出逐位比对）

| 项 | wbank2 | outfifo（8 字） | 变化 |
|---|---:|---:|---:|
| 平均周期/层 | 94,085.67 | **94,085.67** | **0** |
| 吞吐（150 MHz 假设） | 1,594.29 层/s | **1,594.29 层/s** | 0 |
| 12 层输出 | 304,128 | **304,128 全部逐位一致** | — |
| 逐层周期 | 94,115 / 94,083×11 | 94,115 / 94,083×11 | 0 |
| 写回 `block_pop` 字数 | 25,344 | 25,344 | — |
| 写回占用拍数 | 25,773 | **25,773**（1.017 拍/字） | 0 |

证据：`build/outfifo/result.json`、`build/outfifo/layerNN/sim.log`
（含 `PASS real E203 … 25344 outputs`、`QINGYU_WEIGHT_TRANSFER commands=16 reads=8192 writes=8192`）。

结论：**FIFO 加深对周期数没有任何影响**——写回通路在改动前就已经是 1.017 拍/字，
不存在 FIFO 饥饿。下面是实测证据与真正的瓶颈分解。

## 设计（唯一改动：预读 FIFO 2 → 8 字）

`qingyu_accel.sv` 差异（≤12 行）：

```diff
- reg stream_slot, fetch_pending, fifo_head, fifo_tail, stream_response;
- reg [1:0] fifo_count;  reg [31:0] fifo [0:1];
+ localparam FIFO_AW = 3;  localparam FIFO_DEPTH = 1 << FIFO_AW;
+ reg [FIFO_AW-1:0] fifo_head, fifo_tail;  reg [FIFO_AW:0] fifo_count;
+ reg [31:0] fifo [0:FIFO_DEPTH-1];
+ wire [FIFO_AW:0] fifo_used = fifo_count + {{FIFO_AW{1'b0}},fetch_pending};
+ wire [FIFO_AW-1:0] fifo_head_next = fifo_head + 1'b1, fifo_tail_next = fifo_tail + 1'b1;
- (fifo_count+{1'b0,fetch_pending} < 2 || consume_stream)
+ (fifo_used < FIFO_DEPTH || consume_stream)
- assign block_next_valid = fifo_count==2 || (fifo_count==1 && fetch_pending);
- assign block_next_data = fifo_count==2 ? fifo[!fifo_head] : {y_rdata[...]};
+ assign block_next_valid = (fifo_count>1) || (fifo_count==1 && fetch_pending);
+ assign block_next_data = (fifo_count>1) ? fifo[fifo_head_next] : {y_rdata[...]};
- fifo_tail<=!fifo_tail;   fifo_head<=!fifo_head;
+ fifo_tail<=fifo_tail_next; fifo_head<=fifo_head_next;
```

- `block_data` / `block_next_data` / `block_next_valid` / `block_pop` 的对外语义完全不变，
  因此 **FIO 一行都没改**（`output_write_next` 的“当前字 + 下一字”双拍语义保持原样）。
- 写入条件用 `fifo_used = count + pending < DEPTH`，保证在飞的那个字也有位置，不会覆盖队头；
  深度可在 `FIFO_AW` 一处改成 4（16 字）。
- `bus_state!=B_OUT_REQ` 约束保留（与 MMIO 输出回读不抢 Y 口）。
- 实测 FIFO 占用：输出回灌的 25,773 拍里有 24,720 拍（95.9%）占用在 5~8 字之间，
  每批起点 `wr_cmd=208`（每批恰好 1 拍）、`first_word_wait=0`、`pop_no_valid=0`，即深度 8 已饱和。

## 为什么“2.21 拍/字 / 56,081 拍”不是输出通路的数字

`56,081` 是 FIO **块引擎总占用**（本实验实测 `copy_cycles=56,097`），它由三部分组成：

| 块拷贝类别 | 字数 | 拍数 | 拍/字 |
|---|---:|---:|---:|
| 层装载 staging（`load_words`，55 次块拷贝） | 11,680 | 24,148 | 2.07 |
| 输入拷贝（`0x90`，X 进加速器） | 3,168 | 6,354 | 2.01 |
| **输出写回（`0x3c/0x40`，208 批）** | **25,344** | **25,773** | **1.017** |

staging 与输入拷贝都是 2 拍/字，原因是单口共享 SRAM 的“读 1 笔 + 写 1 笔”和 16-bit 输入口
（每个 32-bit 字要写 2 个 16-bit 元素），与读预取 FIFO 无关。
输出写回 25,773 拍 / 25,344 字 = **1.017 拍/字**，理论上限 1.000，只剩 429 拍（0.46%）余量。

## 真正的瓶颈（layer01 = 94,083 拍，全部实测）

| 段 | 拍数 | 占比 | 性质 |
|---|---:|---:|---|
| 层装载 staging（55 次块拷贝 / 11,680 字） | 24,148 | 25.7% | 单口 SRAM 拷贝，2.07 拍/字，**测试台数据装载** |
| `qingyu_run` 前导（`validate_job` 256 列检查等） | ≈4,446 | 4.7% | 纯 CPU |
| 输入拷贝（3,168 字 × 2 拍） | 6,354 | 6.8% | 16-bit X 口 |
| 首个 tile 编程（权重预取 531 + 32 次 meta 620 + START） | ≈1,168 | 1.2% | CPU MMIO |
| **加速器计算（16 tile）** | **43,885** | **46.6%** | 含 `producer_stall` 1,980 |
| tile 间加速器空转（15 × 922） | 13,816 | 14.7% | CPU 写 32 个 meta（每个 ≈19.4 拍） |
| 收尾 | ≈168 | 0.2% | |

两条旁证：

- 固件自计时：`driver_task_cycles = 65,554`（`qingyu_run` 内部），即“驱动任务”本身已 < 70,000；
  TB 口径的 94,083 额外含 28.5k 拍的装载/前导（staging 24,148 + validate_job 4,446）。
- 32 次 meta MMIO 每 tile 620 拍 → 16 tile = 9,920 拍；其中每次 MMIO 往返 ≈19.4 拍是
  E203 非缓存设备访问的固定开销，与 FIFO 深度无关。

## 建议（按收益排序，均不在本次“只改 accel”范围内）

1. **staging 24,148 拍**（25.7%）：把层数据装载移出测量窗口，或用双端口/宽口 SRAM、DMA。
   这是当前单一最大可省项。
2. **meta MMIO 9,920 拍**（10.5%）：合并 32 个字（如 128-bit meta 写口 / 块写命令）。
3. **tile 间空转 13,816 拍**（14.7%）：与 2 同源（meta 写）+ 每次 MMIO 往返 ≈19 拍。
4. **`validate_job` 4,446 拍**（4.7%）：驱动里对 256 列的 bias/shift 逐列检查，纯软件，
   可改为查表/位图或只在 debug 版本做；属驱动改动，收益 4.7%。
5. **`producer_stall` 1,980 拍**（2.1%）：FIO 在 `wl_busy` 时阻塞了 batch 释放写
   （`!wl_busy || icb_cmd_read`），可放宽为允许该释放写；属 FIO 改动，收益 2%。
6. 输出写回只剩 429 拍余量，**继续加深 FIFO 无收益**。

## 复现

```powershell
python experiments/h1500v/outfifo/measure_outfifo.py --layers all
```

`tb_outfifo.sv` 在官方性能 TB 上加了 FIO 块引擎占用、FIFO 占用直方图、加速器忙/闲时间线
（`QINGYU_COPY` / `QINGYU_OUT` / `QINGYU_TL` / `QINGYU_CMD` 四种打印），只做观测，不影响行为。
