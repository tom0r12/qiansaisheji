"""Fill the supplied official cover without changing its printed layout."""
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
parser.add_argument('--title-font', type=Path, default=Path('C:/Windows/Fonts/STZHONGS.TTF'))
parser.add_argument('--field-font', type=Path, default=Path('C:/Windows/Fonts/simfang.ttf'))
args = parser.parse_args()
for font in (args.title_font, args.field_font):
    if not font.is_file():
        parser.error(f'Font not found: {font}. Supply a licensed Chinese TrueType font path.')
config = json.loads((ROOT / 'cover_config.json').read_text(encoding='utf-8'))
assert config['year'] == 2026
pdfmetrics.registerFont(TTFont('CoverTitle', str(args.title_font)))
pdfmetrics.registerFont(TTFont('CoverField', str(args.field_font)))
page = PdfReader(ROOT / 'assets/cover_blank.pdf').pages[0]
buf = io.BytesIO()
cv = canvas.Canvas(buf, pagesize=(float(page.mediabox.width), float(page.mediabox.height)))
cv.setFont('CoverTitle', 27.95)
cv.drawCentredString((177.95 + 360.70) / 2, 433, config['report_type'])
cv.setFont('CoverField', 14.05)
for field, line_y in [('project_name', 287), ('team_id', 255.8), ('team_name', 224.6)]:
    assert pdfmetrics.stringWidth(config[field], 'CoverField', 14.05) <= 302, f'{field} is too long for the cover line.'
    cv.drawString(233, line_y + 4, config[field])
cv.drawCentredString((320.05 + 340.92) / 2, 133, str(config['month']))
cv.drawCentredString((354.97 + 375.959) / 2, 133, str(config['day']))
cv.save()
buf.seek(0)
page.merge_page(PdfReader(buf).pages[0])
writer = PdfWriter()
writer.add_page(page)
writer.add_metadata({'/Title': '轻语前馈线性加速器技术报告封面', '/Author': '', '/Creator': ''})
with (ROOT / 'assets/cover.pdf').open('wb') as handle:
    writer.write(handle)
missing = [key for key in ('team_id', 'team_name') if not config[key]]
provenance_path = ROOT / 'report_provenance.json'
provenance = json.loads(provenance_path.read_text(encoding='utf-8'))
provenance['missing_cover_fields'] = missing
provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Cover generated. Empty mandatory fields:', ', '.join(missing) or 'none')
