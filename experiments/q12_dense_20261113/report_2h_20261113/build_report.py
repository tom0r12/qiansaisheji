"""Build the bounded engineering report from explicitly attributed observations."""
from pathlib import Path
import argparse,hashlib,json
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4,landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph,Table,TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
ap=argparse.ArgumentParser();ap.add_argument('--font',default='C:/Windows/Fonts/simhei.ttf');a=ap.parse_args()
pdfmetrics.registerFont(TTFont('ReportCN',a.font))
obs=json.loads((BASE/'earlycheck_observation.json').read_text(encoding='utf-8'))
extra=BASE/'final_report_data.json';d=json.loads(extra.read_text(encoding='utf-8'))if extra.exists()else{}
out=ROOT/'output/pdf/q12_150mhz_2h_report_20261113.pdf';out.parent.mkdir(parents=True,exist_ok=True)
W,H=landscape(A4);c=canvas.Canvas(str(out),pagesize=(W,H))
c.setTitle('Q12 150 MHz 两小时优化与验证报告');c.setAuthor('Qingyu Project')
ink=colors.HexColor('#102a43');muted=colors.HexColor('#526575');blue=colors.HexColor('#136b99');amber=colors.HexColor('#9b5500')
style=ParagraphStyle('body',fontName='ReportCN',fontSize=11,leading=17,textColor=ink,wordWrap='CJK')
small=ParagraphStyle('small',parent=style,fontSize=9,leading=13)
page=0
def glyphs(text):
 return str(text).replace('²','^2').replace('µ','u').replace('ᵢ','_i')
def start(title,sub):
 global page
 page+=1;c.setFillColor(colors.HexColor('#f7f9fc'));c.rect(0,0,W,H,fill=1,stroke=0)
 c.setFillColor(blue);c.rect(32,H-48,5,22,fill=1,stroke=0)
 c.setFillColor(ink);c.setFont('ReportCN',21);c.drawString(48,H-43,title)
 c.setFillColor(muted);c.setFont('ReportCN',9);c.drawString(48,H-64,sub)
def para(text,x,y,width,st=style):
 p=Paragraph(glyphs(text),st);w,h=p.wrap(width,H);p.drawOn(c,x,y-h);return y-h-10
def table(rows,x,y,widths):
 wrapped=[[Paragraph(escape(glyphs(v)),small)for v in row]for row in rows]
 t=Table(wrapped,colWidths=widths,hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dceaf3')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#edf3f8')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('LINEBELOW',(0,0),(-1,0),.6,blue)]))
 w,h=t.wrap(W,H);t.drawOn(c,x,y-h);return y-h-16
def finish():
 c.setStrokeColor(colors.HexColor('#c8d6e0'));c.line(32,37,W-32,37)
 c.setFont('ReportCN',8);c.setFillColor(muted);c.drawString(32,22,'Q12 | 2026-11-13 | TT 1.10 V / 25 C | 布局前工程结果，非硅后测量')
 c.drawRightString(W-32,22,str(page));c.showPage()
area=obs['incremental_area_um2']/1e6;baseline=.448646862835
start('Q12：完整输出与 150 MHz 验证','限时窗口：2026-11-13 15:27:58 - 17:27:58（UTC+8） | '+d.get('cutoff','进行中快照'))
y=para(d.get('headline','新版综合已完成；完整时序审查、等价性与能耗覆盖仍在核查。'),40,H-91,W-80)
rows=[['指标','当前测量','证据与边界'],['吞吐',f"{obs['throughput_at_150mhz']:.2f} tasks/s",'历史冻结 12 任务，厂家 SRAM 模型；并非官方随机 600 样本验收'],['增量面积',f'{area:.6f} mm²',f'比已核对基线 {baseline:.6f} mm² 低 {(1-area/baseline)*100:.2f}%'],['DC setup / hold','0.00000000 / +0.00070456 ns',d.get('timing_scope','完整时序与未约束端点仍在复核')],['整机功耗 / 每任务能耗',d.get('power_text','测试中'),d.get('power_scope','必须通过 12 个完整任务窗口和活动覆盖核查')],['等价性 / 正式精度',d.get('formal_text','Formality 运行中；正式 600 样本未完成'),'精度、接口验收和证明缺项均不得以旧版本结果替代']]
y=table(rows,40,y,[132,225,W-437])
para('当前候选：native12_earlycheck。所有面积、时序与功耗引用同一冻结网表；此前的 0.399 mm² 中间版有真实 hold 违例，未晋升。',40,y,W-80)
finish()
start('与历史版本的数值对比','不同版本的测量口径未完全统一；除核实基线外，不作为正式排名或等条件收益证明')
y=table([['版本','吞吐 tasks/s','增量面积 mm^2','能耗 uJ/任务'],['当前冻结候选','6075.99','0.388582','9.60（工程估计）'],['用户上一版约数','6000','0.48','未提供同口径值'],['已核对综合基线','6022.40（历史记录）','0.448647','未提供同口径值'],['早期用户记录','4700','0.38','7（口径未核实）'],['群内比较目标','10450','0.5','6.3（口径未核实）']],40,H-91,[220,150,155,W-605])
y=para('相对 6000 tasks/s、0.48 mm^2：吞吐 +1.27%，面积 -19.05%。相对已核实面积基线 0.448647 mm^2：面积 -13.39%。当前功耗约 58.36 mW，包含整机，不是仅加速器功耗。',40,y,W-80)
y=para('9.60 uJ 比旧记录 7 uJ 高约 37.19%，比群内 6.3 uJ 高约 52.43%；旧值缺少同网表、同窗口、同活动覆盖与工艺条件，不能据此判断真实能效退化幅度。当前吞吐尚未达到群内 10450 tasks/s 目标。',40,y,W-80)
para('本版由用户指定为时间受限时的提交基线，并不因此改变验收状态。冻结标签保存源码与报告；后续修复在独立分支进行，不能静默替换本版测量值。',40,y,W-80)
finish()
start('改动与规则核对','规则依据：赛题问题答复（4 页）及赛题指南；不把工程自检等同于正式验收')
rows=[['项目','实现及核验','状态'],['完整矩阵输出','25344 个 signed12 数值，固定下标、固定宽度；16 tile，每 tile 594 个 32 位字。无 Rice、差分、变长或零值省略。','已改；逐值与物理 SRAM 读回通过'],['共享 SRAM / System Bus','保留原 32 位 System Bus 和单一共享 SRAM 入口；无直连额外读写口；完成点为最后写响应 ACK。','总线路由与事务守恒已核查'],['量化与输出精度','X12/W10/Y12；权重及偏置固定最近偶数舍入除以 4，移位减 1；无重训或按测试样本拟合。','原精度分数不能沿用；600 样本待验'],['错误处理时序','输出身份检查不再依赖 ready，断开 ready→abort→ready 组合反馈；合法任务周期不变。','12 正常任务 + 2 错误注入通过'],['面积与总线边界','面积计入加速器、接口和新增逻辑；整机功耗包含 E203、互连和全部 SRAM。','新增 loader_* 接口仍有正式验收项']]
y=table(rows,40,H-91,[140,440,W-660])
para('量化后固定 12 位存储是本设计的原生数值格式，不是对结果另做压缩。但其精度必须重新验证，不能仅凭输出格式合规就宣称完整比赛合规。',40,y,W-80)
finish()
start('时序条件与修复依据','6.666666667 ns 周期 | setup 不确定度 0.1 ns | hold 不确定度 0.02 ns | 数据 I/O 延迟不放宽')
y=para('原版 SRAM 数据路径有 -0.14896035 ns 的真实 hold 违例。新候选在正常逻辑映射后执行 hold-only 修复；没有把加速器、SRAM 或总线数据路径设为 false path。最终最差 hold 为 +0.00070456 ns，余量仅约 0.70 ps。',40,H-91,W-80)
y=para('仅对四个原有 PWM 异步同步器的第 0 级 D 引脚设置入口例外；后续同步级继续计时。loader_clk 为直接导出的时钟，改为 1:1 generated clock，删除其误加的数据输出延迟。功能 debug strap 为 111，与任务仿真一致。',40,y,W-80)
y=table([['检查','结果 / 说明'],['DC 路径报告','setup 0.00000000 ns；hold +0.00070456 ns'],['完整 check_timing / STA',d.get('timing_review','核查中')],['等价性',d.get('formal_detail','同版 RTL → mapped.v / mapped.svf 的 Formality 证明运行中')],['限制','官方 TT、理想时钟、布局前工程条件；不代表布线后、多工艺角或硅片签核。']],40,y,[180,W-260])
para('任何未约束的功能端点、未解释的时钟或未完成的证明都会保留为未闭合项；不能只凭最差路径非负就声称所有约束通过。',40,y,W-80)
finish()
start('面积与功耗测量方法','来源为服务器 DC / PrimeTime 原始报告；本页数值由屏幕证据转录，源报告留存在服务器')
y=table([['面积项目','µm²','mm²'],['加速器及私有存储',obs['fio_area_um2'],f"{obs['fio_area_um2']/1e6:.9f}"],['NP3 仲裁',obs['np3_area_um2'],f"{obs['np3_area_um2']/1e6:.9f}"],['共享路径新增非宏逻辑',obs['shared_nonmacro_area_um2'],f"{obs['shared_nonmacro_area_um2']/1e6:.9f}"],['增量合计',obs['incremental_area_um2'],f'{area:.9f}'],['整机总面积（不作为增量分数）',obs['full_soc_area_um2'],f"{obs['full_soc_area_um2']/1e6:.9f}"]],40,H-91,[340,185,W-605])
y=para('吞吐 = 150000000 ÷ 平均任务周期。12 个窗口的平均周期为 24687.3333，最慢 24802 周期；测量覆盖实际装载、计算、等待和最终写回响应。',40,y,W-80)
y=para('能耗 = Σ(Pᵢ × Δtᵢ) / 12。PrimeTime 对同一网表分别读取每个任务的原始 cell-aware SAIF；116 个 SRAM 实例逐一对应，保留单位、活动覆盖、输入引脚来源与 check_power 报告。',40,y,W-80)
para(d.get('power_detail','功耗复测正在运行。任何默认活动、未解释的覆盖缺口或单位歧义都会使能耗保持“未验收”，不把缺失 SRAM 活动记为零。'),40,y,W-80)
finish()
start('可复现身份与交付边界','提交分支 q12-submission-20261113 | 标签 q12-submission-20261113-r1 | 原历史目录保留')
y=para('服务器目录：'+escape(obs['run']),40,H-91,W-80)
y=para('RTL engine SHA-256：<br/>'+obs['engine_sha256']+'<br/>网表 SHA-256：<br/>'+obs['netlist_sha256'],40,y,W-80)
y=para('逐任务周期：'+', '.join(map(str,obs['task_cycles'])),40,y,W-80)
y=para('本地复测：run_local.py 的 --early-output-check 生成同一候选；check_output_fault.py 覆盖 ready=1 与 ready=0 的错误排空。server/run_earlycheck_full.py 运行厂家仿真、整机综合和 Formality；server/run_power_recovery.py 处理 PT 2022 的兼容性并保留原始报告。',40,y,W-80)
y=para('仍需闭合：'+escape(d.get('open_items','正式随机 600 样本精度；新增 loader_* 平台接口认可；完整时序审查与等价性；功耗活动来源。')),40,y,W-80)
para('证据原则：旧版、失败版、进行中结果分别标记；不混用不同网表的面积与功耗。报告截图来自实际 VNC 桌面，不重新绘制工具结果；完整原图与转录 JSON 保存在 report_2h_20261113。',40,y,W-80)
finish()
for item in d.get('figures',[{'file':'21_earlycheck_final_status.png','title':'服务器综合与吞吐结果','caption':'实际 VNC 原始截图；功耗恢复器首轮保护性退出亦保留，不能将其视为成功。'}]):
 p=BASE/'images'/item['file'];assert p.exists(),p
 start('证据图：'+item['title'],item['file'])
 im=ImageReader(str(p));iw,ih=im.getSize();scale=min((W-64)/iw,(H-175)/ih)
 c.drawImage(im,(W-iw*scale)/2,90,width=iw*scale,height=ih*scale)
 para(escape(item['caption']),40,78,W-80,small);finish()
c.save();print(out)
(BASE/'report_manifest.json').write_text(json.dumps({'pdf':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'pages':page,'observation':str(BASE/'earlycheck_observation.json')},indent=2)+'\n',encoding='utf-8')
