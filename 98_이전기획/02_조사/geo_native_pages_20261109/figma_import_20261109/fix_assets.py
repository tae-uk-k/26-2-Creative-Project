"""Recover discrete photo fills and editable outlines from the existing source."""
from pathlib import Path
import hashlib
import json
import re
import sys

from lxml import html
from PIL import Image

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent
sys.path.insert(0, str(SOURCE.parents[1] / '.test-tmp/figma-brotli'))
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

targets = {
    'kakao': [('1134:120',272,204),('1134:129',132,98),('1134:136',132,98),('1134:144',132,98),('1134:151',132,98),('1134:287',112,112),('1134:305',112,112),('1134:322',112,112)],
    'google': [('1135:43',408,272),('1135:266',195,195),('1135:272',195,195),('1135:299',149,149),('1135:331',149,149),('1135:339',149,149)]
}
photos = []
for name, nodes in targets.items():
    source = Image.open(SOURCE / 'assets' / (name + '_photos.png'))
    elements = html.parse(str(SOURCE / (name + '.html'))).xpath('//img[contains(@style,"background-image")]')
    assert len(elements) == len(nodes), (name, len(elements), len(nodes))
    for element, (node, width, height) in zip(elements, nodes):
        style = element.get('style')
        pos = re.search(r'background-position:([^;]+)', style)[1].split()
        px, py = [float(x.rstrip('%')) / 100 for x in pos]
        sy = 2 * height / source.height
        sx = 2 * width / source.width if 'background-size:200% 200%' in style else sy
        left = -(width - source.width * sx) * px / sx
        top = -(height - source.height * sy) * py / sy
        crop = source.crop((left, top, left + width / sx, top + height / sy)).convert('RGB')
        path = OUT / (node.replace(':', '-') + '.jpg')
        crop.save(path, quality=97)
        photos.append({'nodeId': node, 'path': str(path), 'width': width, 'height': height})

css = (SOURCE / 'assets/google-inline.css').read_text(encoding='utf-8')
block = next(b for b in re.findall(r'@font-face\s*\{[^}]*\}', css) if 'Google Symbols' in b)
url = re.search(r'url\("([^"]+)"', block)[1]
font = TTFont(OUT / 'resources' / hashlib.sha256(url.encode()).hexdigest())
glyphs = font.getGlyphSet()
em, ascent = font['head'].unitsPerEm, font['hhea'].ascent
icons = json.loads((OUT / 'google-icons.json').read_text(encoding='utf-8'))
for icon in icons:
    glyph = font.getBestCmap()[ord(icon['text'])]
    pen = SVGPathPen(glyphs)
    glyphs[glyph].draw(pen)
    color = icon['fills'][0]['color']
    fill = '#' + ''.join(f'{round(color[k]*255):02x}' for k in ['r','g','b'])
    size = icon['fontSize']
    icon['svg'] = f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {em} {em}"><path transform="translate(0,{ascent}) scale(1,-1)" fill="{fill}" d="{pen.getCommands()}"/></svg>'

(OUT / 'photo-assets.json').write_text(json.dumps(photos, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'vector-icons.json').write_text(json.dumps(icons, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'photos': len(photos), 'icons': len(icons), 'font_units': em, 'font_ascent': ascent}))
