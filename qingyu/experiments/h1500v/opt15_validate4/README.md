# opt15_validate4 参数验证扫描优化

本候选从 `opt14_ybank2` 派生。全部 RTL、头文件和应用固件保持字节一致，仅修改 `rtl/qingyu_accel.c` 中 `validate_job()` 的参数扫描部分。没有缓存验证结果、模型参数或计算答案；每个任务仍完整检查所有 256 列的 shift 和 bias。

## 行为与预期收益

shift 地址四字节对齐时，一次读取四个字节，用以下无符号表达式检查任一字节是否大于 47：

```c
((packed + UINT32_C(0x50505050)) | packed) & UINT32_C(0x80808080)
```

所有字节在 0..47 时，加 0x50 后既不进位到下一字节，也不设置最高位。48..127 在相加后设置最高位；128..255 在原值中已设置最高位，因此全部非法值都被检出。读取使用 GCC/Clang `may_alias` 类型，不依赖违反严格别名规则的类型转换。未对齐 shift 缓冲继续原逐字节路径。

空指针、维度、对齐、地址溢出、输出重叠检查均保持原顺序，先于数据扫描执行。组内的 shift/bias 检查顺序可能不同，但两者均返回 `QINGYU_ERR_FORMAT`，不会改变返回错误码。所有 bias 的有符号 48 位范围检查仍然执行。

对齐路径的 shift 读取由 256 次降为 64 次，减少 192 次共享内存读取。实际任务耗时须由包含验证扫描的 E203 端到端窗口测量；不能直接把读取次数比例当作吞吐提升。

## 已执行验证

独立 host C 测试同时链接未经修改的 opt14 驱动和本候选，并对照独立预期错误码。两轮各 283446 项检查均通过：

- GCC `-O3 -funroll-loops -fstrict-aliasing -Wall -Wextra -Werror`。
- 同样配置再启用 AddressSanitizer 和 UndefinedBehaviorSanitizer。

覆盖全部 256 种 shift 字节值、全部 256 列和四种地址对齐；每列的有符号 48 位 bias 边界；10000 组混合数据；全部结构错误码优先于非法参数内容；紧邻不可访问 guard page 的缓冲边界。验证函数未发生 MMIO 调用。

证据：

- `build/validate4_checks/20261111T120848789122Z/result.json`
- `build/validate4_checks/20261111T120858928186Z/result.json`

在装有 GCC 的 Linux/WSL 中，从 `qingyu` 执行：

```text
python3 scripts/run_validate4_checks.py
python3 scripts/run_validate4_checks.py --sanitize
```

完整 SoC 对照应使用 `scripts/run_candidate_soc.py --candidate opt15_validate4`，与 opt14 使用相同输入、工具、时钟假设和完整计时窗口。该候选不代表官方精度、综合时序、面积或功耗验收完成。
