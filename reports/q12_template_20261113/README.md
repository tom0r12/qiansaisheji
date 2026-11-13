# 轻语前馈线性加速器技术报告

[阅读 PDF](qingyu_technical_report.pdf)

2026 年全国大学生嵌入式芯片与系统设计竞赛芯片设计赛道技术报告。设计版本为 `8731bf4f553e80a1ac5e68fb924b0436ddbdb77f`，标签为 `q12-submission-20261113-r1`。本目录包含 PDF、LaTeX 源文件、图表素材、测试数据和编译脚本。

2026 年 11 月 13 日完成正文与排版定稿核对：22 页、14 幅图、10 个编号表格；冻结源码、证据文件与报告数据一致，全部页面已检查。封面两项必填信息见下方说明。

## 内容

- 两页快速预览：系统架构、设计要点、性能指标和验证结果。
- 中英文摘要、设计平台、完整任务流程、成对乘积推导、PE 阵列、私有 SRAM、定点格式、输出映射、总线与固件协议。
- 功能验证、12 个历史任务的完整周期、面积明细、时序边界、逐任务功耗/能耗、等价性及规则核对。
- 五页测试报告节选及 TikZ/PGFPlots 矢量架构图与曲线。截图采用结果区域，图像裁剪范围由 LaTeX 的 `trim` 参数控制。

## 封面信息

在 `cover_config.json` 中填写 `team_id`（队伍编号）和 `team_name`（参赛队名）。这两个字段目前为空。

已有 PDF 可直接阅读。修改封面时，在 Windows Python 环境安装 `reportlab` 后执行：

```powershell
python make_cover.py
```

脚本默认使用 Windows 的宋体与黑体，不打包或分发字体。其他系统可以通过 `--song-font`、`--hei-font` 指向有授权的中文 TrueType 字体。封面保留官方底稿的标题、字段和顺序，重新排齐字体、填写基线和间距；每次生成独立矢量封面，不叠加旧文字。编辑字段后再编译正文。目录使用 12 磅宋体、16 磅基线间距。

## 重新编译

推荐使用 TeX Live 2023 或更新版本，包含 XeLaTeX、ctex、Fandol、TeX Gyre Termes、TikZ/PGFPlots 和常用 LaTeX 扩展包。正文不依赖 Windows 字体，Fandol 字体直接按文件名加载。Ubuntu / WSL 的对应包为：

```bash
sudo apt-get install texlive-xetex texlive-lang-chinese texlive-latex-extra texlive-fonts-recommended fonts-texgyre
bash build.sh
```

`prepare_report.py` 使用 Python 标准库核对源码与网表标识、面积加和、吞吐及能量计算，并校验原始截图 SHA-256，随后生成数据表。`build.sh` 编译三遍以更新目录，检查越界、缺字及未定义引用。输出为 `qingyu_technical_report.pdf`。

排版更改后仍需渲染全部页面进行人工检查，例如：

```bash
mkdir -p rendered
pdftoppm -png -r 110 qingyu_technical_report.pdf rendered/page
pdftotext qingyu_technical_report.pdf build/report.txt
```

## 数据口径

历史 12 个完整任务窗口平均为 24687.33 周期，按 150 MHz 换算为 6075.99 tasks/s；增量综合面积为 0.388582 mm²，整机面积为 2.730734 mm²；整机功耗工程估计为 58.36 mW、能耗为 9.60 µJ/任务。正式 600 样本精度及 loader 接口验收尚未完成，未约束时序端点、功耗活动覆盖、模型警告和等价未匹配点仍待复核。

`earlycheck_observation.json` 保存早期测试快照，其中 Formality 状态为运行中；后续结果保存在 `final_report_data.json` 和 `power_observation.json`。各文件保留对应测试阶段的状态。

`report_provenance.json` 保存模板来源、源码、网表及截图的哈希；`submission_check.json` 保存本次与冻结交付包的核对记录；`quality_check.json` 保存 PDF 哈希、页数和排版检查结果。`assets/cover_blank.pdf` 为官方封面底稿，`assets/cover.pdf` 为按相同内容重新排版后的封面。
