# opt33 继承文字的适用范围更正

`opt33_readcache/verification_contract.json` 保留了 opt31 的一句旧约束：“Backpressure must prevent both acceptance and mutation.” 这句话描述 opt31 的写响应实现，不适用于 opt33。为保留已经哈希冻结的原始候选和结果，本说明单列更正，不改写历史清单。

opt33 的实际协议为：没有旧响应待返回且没有 cache_clear 时，可接受写命令，即使响应接收方暂时不 ready。写入在**实际命令接受边沿**提交一次；若同拍响应未被接收，控制器保存响应并保持到其被接受，期间不接受下一命令。它不会在命令未被接受时写存储，也不会把尚未写入的数据提前确认。

独立控制器十种随机种子、行为/物理 wrapper 各三种种子均覆盖响应背压下的真实提交及稳定响应。汇总路径为 `20261112_readcache_validation.json`；原测试日志与源码哈希不变。此更正涉及协议文档，不增加任何时序、面积或功耗结论。
