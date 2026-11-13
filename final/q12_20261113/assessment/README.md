# Q12 冻结候选：整机综合、STA 诊断、Formality 与同窗功耗

这是 `20261112T161939623706Z/result.json` 唯一候选的服务器工程评估包。固定结果 SHA256 为 `07bc11f0d6301a7570979e70aca022f54845c8bab6468eae58f10ba94aa3a80e`。保留 bounded encoder、decoder2、rowpair、core data reset、blocking WAIT、真实 E203 与独立 NP3 loader；不修改 RTL，不运行新的设计优化。

包内无 PDK、数据集、EDA 工具。物理库从服务器既有官方 SCC40NLL RVT TT 1.10 V 25 ℃ 和对应 SRAM DB 加载。源文件按 `prepare_hardware.py` 的既有契约准备，仅把行为存储替换为已经审阅的厂家宏封装；完整映射包含 30×RAMSP128X16、6×RAMSP1024X16、80×RAMSP4096X16，后者包含固定共享 SRAM 与 E203 TCM。所有库、源码、网表、SVF 与活动文件均保留哈希。

## 运行

将 zip 上传并解压至桌面后，先进入解压出的 `q12_final_assessment`。登录 shell 若为 tcsh，使用下面的 `sh -c` 形式。

```sh
python3 run_assessment.py --verify-only
sh -c 'nohup python3 run_assessment.py --phase synth > launch_synth.log 2>&1 < /dev/null &'
```

日志首行给出 `Q12_FINAL_ASSESSMENT_DIRECTORY=...`。`STATUS.txt` 和 `result.json` 持续记录阶段；`synth/dc.log` 有 `Q12_COMPILE_BEGIN/END` 标记。综合默认允许 10800 秒，不使用旧包的 600 秒筛选期限。相同候选有排他文件锁，不会同时重复综合；已有完成阶段校验输出哈希后跳过。中断或失败目录完整保留，脚本不会悄悄覆盖或自动重新跑。

综合完成、厂家宏 12 层活动包成功后，将实际目录传入；以下使用环境变量表达路径，须设为上一步日志给出的完整路径。

```sh
python3 run_assessment.py --phase post --run-dir "$ASSESSMENT_RUN" --vendor-run "$VENDOR_RUN" --layers 12
```

`post` 先做 Formality，再用同一整机网表逐层做 PrimeTime PX。也可 `--phase formal` 或 `--phase power` 单独运行；`--layers 1` 仅验证第 0 层功耗。12 层逐一保存原始报告，单位/覆盖审计失败单独记为未合格，不能把原始数字当作合格功耗。

若桌面文件系统空间不足，可增加 `--work-root /实际可写目录`，所有新结果和 EDA 临时文件写到该目录；源码包与既有官方库仍只读。脚本不会删除旧证据或活动文件。排他锁位于系统临时目录。报告格式适配后，可对**完全相同**的映射输入使用 `--allow-tooling-update --recheck-reports` 重新审查已保存报告，只有硬件文件、map.tcl、audit.tcl 和库哈希全部不变才允许复用，避免重复综合。

## 数字的范围

- **新增面积**：实际 leaf cell 面积求和。包含 `u_fio` 全部计算/编解码/私有宏/邮箱、完整 NP3 `u_mem_merge`、`u_shared` 内全部非宏自定义控制/缓存/接口逻辑。共享的 64 个 RAMSP4096X16 宏、CPU/TCM/固定平台分别列出。避免层级重复计数。面积先保存库原生单位；换算 mm² 还需确认库物理面积单位。
- **STA**：TT、150 MHz 名义周期、1 ns I/O 延迟、0.1 ns setup uncertainty/0.02 ns hold uncertainty。三个时钟根及导出的核心/总线时钟显式采用 pre-CTS 理想网络，避免把时钟高扇出当普通数据路径修复。生成时钟、check_timing、clock attributes、最大/最小路径均输出。负 slack、未约束端点、时钟覆盖问题按失败/待审报告，不做 ECO。不代表五角/布局布线后时序通过。
- **功耗/能耗**：完整 SoC 网表，`tb_q12soc/dut`，严格使用 earliest command offer 至最终完成标志 ACK 的 SAIF 窗口。必须来自同一冻结候选、厂家宏仿真逐输出检查通过、精确 ps 时间戳。116 个宏实例与输入活动来源逐项审查，单位未知、覆盖格式未知或默认活动不能混为合格功耗。能耗只用合格的实际窗口功耗乘对应时长；不从第 0 层外推 12 层。估算不包含真实 CTS 网络和布线寄生，不是芯片实测。
- **Formality**：冻结 RTL 与本次生成网表的映射等价检查；两侧 SRAM 使用相同官方库边界。SRAM 内部功能由厂家宏仿真承担。失败/未证明不会触发设计修改。

## 大致耗时

综合通常按 30–120 分钟预留，硬上限 3 小时；Formality 约 10–60 分钟，硬上限 2 小时；PX 每层约 1–5 分钟，12 层约 15–60 分钟。工具许可、服务器负载与具体面积会影响时间。综合与独立的厂家宏仿真可并行，整体先按 2–4 小时安排；若超时、库/时钟/覆盖审计失败，保留已经得到的性能与失败事实，不承诺签核成功。

本地仅执行包完整性、语法与解析器对抗测试。实际 EDA 结果必须来自服务器新目录。所有脚本为受限兼容 Python 3.6+ 的标准库程序。
