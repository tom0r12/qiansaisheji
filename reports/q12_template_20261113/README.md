# 轻语技术报告：模板排版版

[阅读 PDF](qingyu_technical_report.pdf)

本报告使用提供的中文 LaTeX 技术报告模板，采用指定的 2026 年芯片设计赛道封面。正文对应冻结提交 `8731bf4f553e80a1ac5e68fb924b0436ddbdb77f`（标签 `q12-submission-20261113-r1`）。报告在后续工作分支单独维护，没有修改冻结 RTL、原始证据或已冻结交付清单。

## 内容

- 封面后两页快速预览：系统接入、主要设计点、测量结果和待验收项。
- 中英文摘要、设计平台、完整任务流程、成对乘积推导、PE 阵列、私有 SRAM、定点格式、输出映射、总线与固件协议。
- 功能验证、12 个历史任务的完整周期、面积明细、时序边界、逐任务功耗/能耗、等价性及规则核对。
- 五张真实服务器证据截图，采用横向 A4 保留完整边界；架构图与曲线由 TikZ/PGFPlots 生成矢量内容。
- 删除不适用的实物对比、PCB、上板照片等栏目。没有使用参考报告中的成果数值或实物图片。

## 必须补齐的封面字段

`cover_config.json` 中 `team_id`（队伍编号）和 `team_name`（参赛队名）目前为空。未从参考报告借用其他队伍身份；提交前填写真实信息，正文及队名不得包含规则禁止出现的学校信息。

已有 PDF 可直接阅读。修改封面时，在 Windows Python 环境安装 `pypdf`、`reportlab` 后执行：

```powershell
python make_cover.py
```

脚本默认使用 Windows 的楷体与黑体，不打包或分发字体。其他系统可以通过 `--kai-font`、`--hei-font` 指向有授权的中文 TrueType 字体。脚本从 `assets/cover_blank.pdf` 重新生成封面，不会叠加旧文字。编辑字段后再编译正文。

## 重新编译

推荐使用 TeX Live 2023 或更新版本，包含 XeLaTeX、ctex、Fandol、TeX Gyre Termes、TikZ/PGFPlots 和常用 LaTeX 扩展包。正文不依赖 Windows 字体，Fandol 字体直接按文件名加载。Ubuntu / WSL 的对应包为：

```bash
sudo apt-get install texlive-xetex texlive-lang-chinese texlive-latex-extra texlive-fonts-recommended fonts-texgyre
bash build.sh
```

`prepare_report.py` 仅使用 Python 标准库，核对已保存的源/网表身份、面积加和、吞吐和能量算术，以及五张原始图的 SHA-256，再生成数据表；不会连接服务器或运行 EDA。`build.sh` 连续编译三遍以更新目录，并拒绝已检测到的越界、缺字和未定义引用。输出为 `qingyu_technical_report.pdf`。

排版更改后仍需渲染全部页面进行人工检查，例如：

```bash
mkdir -p rendered
pdftoppm -png -r 110 qingyu_technical_report.pdf rendered/page
pdftotext qingyu_technical_report.pdf build/report.txt
```

## 数据口径

报告数值为：历史 12 个完整窗口平均 24687.33 周期，按 150 MHz 换算 6075.99 tasks/s；增量综合面积 0.388582 mm²，整机面积 2.730734 mm²；整机功耗工程估计 58.36 mW、能耗 9.60 µJ/任务。不能将历史整数功能验证代替正式 600 样本精度，或把已报告路径非负当成全约束时序通过。功耗覆盖及模型警告、严格等价审计和 loader 接口验收仍有未闭合项。

`earlycheck_observation.json` 是较早时间点的原始观察，其中 Formality 仍显示运行中。`final_report_data.json` 和 `power_observation.json` 保存后续归纳与功耗结果；报告保留各时间点差别，不覆盖原始记录。工具截图中的历史失败不代表后续功耗流程未完成，也不能据此忽略仍存在的审计问题。

`report_provenance.json` 记录模板来源哈希、冻结源码和网表身份以及原始截图哈希；`quality_check.json` 记录最终 PDF 的文件身份、页数和排版检查结果。参考 PDF 的内容仅用于了解模板和组织方式，不随源包重复分发。源包包含指定封面的空白第一页以支持重新填写。
