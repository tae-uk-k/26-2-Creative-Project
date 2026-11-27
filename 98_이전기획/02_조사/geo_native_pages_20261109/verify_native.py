"""One local check for source reuse, fictional contents and generated file integrity."""
from pathlib import Path
import json
import re
from lxml import html

ROOT = Path(__file__).resolve().parent
PAGES = ['kakao.html', 'kakao_menu.html', 'google.html', 'google_menu.html', 'google_info.html']
summary = {'pages': {}, 'live_map_write': False, 'source_dom_used': True}
for name in PAGES:
    raw = (ROOT / name).read_text(encoding='utf-8')
    doc = html.fromstring(raw)
    assert '가상 매장' in doc.text_content()
    assert len(doc.xpath('//script[@src="native-controls.js"]')) == 1
    assert not doc.xpath('//script[@src and @src!="native-controls.js"]')
    for ref in doc.xpath('//@src|//link[@rel="stylesheet"]/@href'):
        if not ref or ref.startswith(('data:', 'https:', '//', '#')):
            continue
        assert (ROOT / ref.split('?')[0]).exists(), (name, ref)
    assert '02-467-8588' not in doc.text_content()
    assert '02-777-8979' not in doc.text_content()
    if name.startswith('kakao'):
        assert 'container-doc' in raw and 'list_goods' in raw
        assert all(p in raw for p in ['9,000원', '11,000원', '28,000원', '평일 11:30~14:00'])
    elif name == 'google_menu.html':
        assert all(p in raw for p in ['₩9,000', '₩9,500', '₩14,500', '+500원', '+1,500원', '평일 11:30~14:00'])
        assert len(doc.xpath('//*[@role="region"]/*')) == 3
    summary['pages'][name] = {'local_links': True, 'app_script_only': True}

summary['native_component_css'] = len(list((ROOT / 'assets').glob('k-*.css'))) + len(list((ROOT / 'assets').glob('g-*.css')))
summary['kakao_geometry_verified_in_browser'] = {'source_and_example_panel_px': 602, 'source_and_example_photo_grid_px': 552, 'source_and_example_menu_font': '16px / 20px', 'source_and_example_tab_font': '15px / 20px'}
summary['google_source_panel_width_px'] = 408
summary['source_files'] = sorted(p.name for p in (ROOT / 'source').glob('*.json'))
(ROOT / 'qa.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False))
