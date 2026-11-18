11+12 号最终冻结服务器验证包（q12clean6）对应候选 A（v9a，W12，默认主推）与候选 B（v9b，W10，高吞吐备选）。
原始 q12clean6.zip 为 5502057 字节，SHA-256 为 475ea5b1f6f52174cf6fee541bfe7003b3b80362e110df3fb2f5be1b96c495e4；
12 号整机 FF125 保持修复与 TT SDF 门级仿真收尾脚本 q12_12_final_close.py 为 28201 字节，SHA-256 为 3479f59e81801529ac83059faacdbbbc874800f50ac9c746eb4ff1f57684cacf。
公开仓库按统一规范省略私有任务向量目录 A/vendor/tasks 与 B/vendor/tasks；复现时需在授权环境补齐 vendor/tasks、厂家 SRAM 模型（SRAM_Lib_2025）与官方 SCC40NLL RVT 工艺库。
