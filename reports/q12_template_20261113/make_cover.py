"""Generate the report cover from cover_config.json."""
from pathlib import Path
import argparse
import io
import json
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--kai-font', type=Path, default=Path('C:/Windows/Fonts/simkai.ttf'))
parser.add_argument('--hei-font', type=Path, default=Path('C:/Windows/Fonts/simhei.ttf'))
args = parser.parse_args()
for font in (args.kai_font, args.hei_font):
    if not font.is_file():
        parser.error(f'Font not found: {font}. Supply a licensed Chinese TrueType font path.')
config = json.loads((ROOT / 'cover_config.json').read_text(encoding='utf-8'))
assert config['year'] == 2026, 'The original cover has a printed 2026 year.'
pdfmetrics.registerFont(TTFont('CoverKai', str(args.kai_font)))
pdfmetrics.registerFont(TTFont('CoverHei', str(args.hei_font)))
buf = io.BytesIO()
cv = canvas.Canvas(buf, pagesize=(595, 842))
cv.setFont('CoverHei', 28)
cv.drawCentredString(270, 433, config['report_type'])
cv.setFont('CoverKai', 12)
for field, y in [('project_name', 287), ('team_id', 255.8), ('team_name', 224.6)]:
    assert pdfmetrics.stringWidth(config[field], 'CoverKai', 12) < 306, f'{field} is too long for the cover line.'
    cv.drawString(235, y, config[field])
cv.setFont('CoverKai', 14)
cv.drawString(323, 133, str(config['month']))
cv.drawString(358, 133, str(config['day']))
cv.save()
buf.seek(0)
page = PdfReader(ROOT / 'assets/cover_blank.pdf').pages[0]
page.merge_page(PdfReader(buf).pages[0])
writer = PdfWriter()
writer.add_page(page)
writer.add_metadata({'/Title': '轻语前馈线性加速器技术报告封面', '/Author': ''})
with (ROOT / 'assets/cover.pdf').open('wb') as f:
    writer.write(f)
missing = [key for key in ('team_id', 'team_name') if not config[key]]
provenance_path = ROOT / 'report_provenance.json'
provenance = json.loads(provenance_path.read_text(encoding='utf-8'))
provenance['missing_cover_fields'] = missing
provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Cover generated. Empty mandatory fields:', ', '.join(missing) or 'none')
