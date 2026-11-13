"""Generate the report cover from cover_config.json."""
from pathlib import Path
import argparse
import json
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--hei-font', type=Path, default=Path('C:/Windows/Fonts/simhei.ttf'))
parser.add_argument('--song-font', type=Path, default=Path('C:/Windows/Fonts/simsun.ttc'))
args = parser.parse_args()
for font in (args.hei_font, args.song_font):
    if not font.is_file():
        parser.error(f'Font not found: {font}. Supply a licensed Chinese TrueType font path.')
config = json.loads((ROOT / 'cover_config.json').read_text(encoding='utf-8'))
assert config['year'] == 2026
pdfmetrics.registerFont(TTFont('CoverHei', str(args.hei_font)))
pdfmetrics.registerFont(TTFont('CoverSong', str(args.song_font), subfontIndex=0))
width, height = A4
cv = canvas.Canvas(str(ROOT / 'assets/cover.pdf'), pagesize=A4)
cv.setTitle('轻语前馈线性加速器技术报告封面')
cv.setAuthor('')
cv.setCreator('')
cv.setFont('CoverHei', 19)
cv.drawCentredString(width / 2, 748, '2026 年全国大学生嵌入式芯片与系统设计竞赛')
cv.setFont('CoverHei', 22)
cv.drawCentredString(width / 2, 703, '芯片设计赛道')
cv.setFont('CoverHei', 30)
cv.drawCentredString(width / 2, 548, config['report_type'] + '报告')

label_x, value_x, line_end = 62, 220, width - 58
cv.setLineWidth(0.6)
for field, label, y in [
    ('project_name', '作品名称（必填）：', 348),
    ('team_id', '队伍编号（必填）：', 300),
    ('team_name', '参赛队名（必填）：', 252),
]:
    cv.setFont('CoverSong', 14)
    cv.drawString(label_x, y, label)
    assert pdfmetrics.stringWidth(config[field], 'CoverSong', 14) <= line_end - value_x - 7, f'{field} is too long for the cover line.'
    cv.drawString(value_x + 4, y, config[field])
    cv.line(value_x, y - 8, line_end, y - 8)
cv.setFont('CoverSong', 14)
cv.drawCentredString(width / 2, 122, f"日期：{config['year']} 年 {config['month']} 月 {config['day']} 日")
cv.save()
missing = [key for key in ('team_id', 'team_name') if not config[key]]
provenance_path = ROOT / 'report_provenance.json'
provenance = json.loads(provenance_path.read_text(encoding='utf-8'))
provenance['missing_cover_fields'] = missing
provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Cover generated. Empty mandatory fields:', ', '.join(missing) or 'none')
