from pathlib import Path
import html
import json
import shutil

ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT.parent / 'geo_mock_v2_20261106'
SOURCE = ROOT.parent / '지도UI_실제정비_2예시_20261106'
DATA = json.loads((PREVIOUS / 'cases.json').read_text(encoding='utf-8'))
ASSETS = ROOT / 'assets'
ASSETS.mkdir(exist_ok=True)
shutil.copy2(SOURCE / 'assets/1fdd370294d73409.svg', ASSETS / 'kakaomap.svg')

ICONS = {
    'search': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>',
    'pin': '<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
    'phone': '<path d="m7 3-3 2c-2 3 4 13 10 15 3 1 5-3 5-3l-4-3-2 2c-3-1-5-3-6-6l2-2Z"/>',
    'globe': '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
    'save': '<path d="M6 3h12v18l-6-4-6 4Z"/>',
    'share': '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m9 10 6-3M9 14l6 3"/>',
    'route': '<path d="m12 2 10 10-10 10L2 12Z"/><path d="M8 15v-5h8m-3-3 3 3-3 3"/>',
    'photo': '<rect x="3" y="5" width="18" height="15" rx="2"/><circle cx="8" cy="10" r="2"/><path d="m3 17 5-4 4 3 4-5 5 6"/>',
    'menu': '<path d="M5 3h14v18H5ZM8 7h8M8 11h8M8 15h5"/>',
    'arrow': '<path d="m9 5 7 7-7 7"/>',
    'back': '<path d="m14 5-7 7 7 7M7 12h14"/>',
    'close': '<path d="m6 6 12 12M18 6 6 18"/>',
    'layers': '<path d="m12 3 10 6-10 6L2 9Zm-10 11 10 6 10-6M2 19l10 6 10-6"/>',
}


def icon(name):
    return f'<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>'


def photo(platform, position, label, cls=''):
    return f'<button type="button" class="photo tile-{position} {cls}" data-photo="{position}" aria-label="{html.escape(label)} 크게 보기" style="--photo:url(assets/{platform}_photos.png)"><span class="photo-image"></span><span class="photo-caption">{html.escape(label)}</span></button>'


def menu_rows(platform):
    rows = []
    for idx, m in enumerate(DATA[platform]['menus']):
        desc = m['description']
        # Repeat neither the introduction nor ingredient lists: retain the unit and ordering conditions.
        if platform == 'kakao':
            desc = [
                '1인분 · 공깃밥 포함',
                '1인분 · 국내산 돼지고기 200g\n공깃밥·밑반찬 3종 포함 / 보통·덜 맵게 선택',
                '2인 세트 총액 · 수제비 1개 + 제육 400g + 공깃밥 2개\n평일 11:30~14:00 주문 가능',
            ][idx]
        if platform == 'google':
            desc = [
                '1인분 · 메밀면 180g\n무즙·대파·와사비, 육수 별도 제공',
                '1인분 · 가다랑어포·다시마 육수, 유부 2장\n면 곱빼기 +1,500원',
                '1인 세트 총액 · 냉메밀소바 + 미니돈가스\n평일 11:30~14:00 / 유부우동 변경 +500원',
            ][idx]
        m['showcase_description'] = desc
        rows.append(f'''<article class="menu-row">{photo(platform, idx+1, m['after'], 'menu-photo')}<div class="menu-copy"><h3>{html.escape(m['after'])}</h3><p class="price">{m['price']}</p><p class="menu-desc">{html.escape(desc).replace(chr(10), '<br>')}</p></div></article>''')
    return ''.join(rows)


def base_rows(platform):
    address = '서울 성동구 성수이로18길 12, 1층' if platform == 'kakao' else '서울 마포구 망원로12길 8, 1층'
    phone = '02-000-0000'
    return f'''<div class="info-row">{icon('pin')}<div>{address}<span class="subtle">{'성수역 3번 출구에서 320m' if platform == 'kakao' else '망원역에서 도보 약 7분'}</span></div></div><div class="info-row">{icon('clock')}<div><span class="open">영업 중</span> <span class="muted">· 21:00에 영업 종료</span><span class="subtle">매일 11:00~21:00 · 마지막 주문 20:30</span></div></div><div class="info-row">{icon('phone')}<div>{phone}</div></div>'''


def tabs(platform):
    labels = [('top', '홈'), ('menu', '메뉴'), ('photos', '사진'), ('info', '매장정보')] if platform == 'kakao' else [('top', '개요'), ('menu', '메뉴'), ('photos', '사진'), ('info', '정보')]
    return '<nav class="tabs" aria-label="가게 정보">' + ''.join(f'<a href="#{target}" class="{"active" if i==0 else ""}">{label}</a>' for i, (target, label) in enumerate(labels)) + '</nav>'


def action_row(platform):
    items = [('route', '길찾기'), ('save', '저장'), ('share', '공유')] if platform == 'kakao' else [('route', '경로'), ('save', '저장'), ('share', '공유')]
    return '<div class="actions">' + ''.join(f'<div class="action {"primary" if i==0 else ""}"><span>{icon(key)}</span>{label}</div>' for i, (key, label) in enumerate(items)) + '</div>'


def restaurant(platform):
    c = DATA[platform]
    c['showcase_intro'] = '직접 반죽한 들깨수제비와 국내산 돼지고기 제육정식' if platform == 'kakao' else '가다랑어포와 다시마로 우린 유부우동, 냉메밀소바와 주문 후 튀기는 돈가스를 준비하는 일식당입니다.'
    name = html.escape(c['name'])
    stars = '<span class="stars" aria-label="별점">★★★★★</span>'
    rating = f'<div class="rating">{stars}<strong>{"4.6" if platform=="kakao" else "4.7"}</strong><span>{"후기 82" if platform=="kakao" else "(128)"}</span><span class="dot">·</span><span>{c["category"]}</span></div>'
    main_photo = photo(platform, 1, '들깨수제비' if platform == 'kakao' else '냉메밀소바', 'hero-main')
    side_photo = photo(platform, 0, '매장 내부', 'hero-interior') + photo(platform, 3, '대표 세트', 'hero-set')
    hero = f'<div class="hero">{main_photo}<div class="hero-side">{side_photo}</div><a href="#photos" class="photo-count">{icon("photo")} 사진 4</a></div>'
    title = f'<div class="place-title"><h1>{name}</h1>{rating}{"<p class=category>한식</p>" if platform=="kakao" else ""}</div>'
    header = title + action_row(platform) + hero if platform == 'kakao' else hero + title + action_row(platform)
    intro = f'<section class="intro-section"><h2>{"한 줄 소개" if platform=="kakao" else "비즈니스 소유자가 제공한 설명"}</h2><p>{c["showcase_intro"]}</p></section>'
    menu = f'<section id="menu" class="menu-section"><div class="section-heading"><h2>메뉴 <span>3</span></h2><span class="owner-note">업체 제공</span></div>{menu_rows(platform)}</section>'
    photos = f'<section id="photos" class="album-section"><div class="section-heading"><h2>사진 <span>4</span></h2></div><div class="album">' + ''.join(photo(platform, i, t) for i, t in enumerate(['매장 내부', '대표 메뉴', '식사 메뉴', '세트 구성'])) + '</div></section>'
    info = f'<section id="info" class="info-section"><div class="section-heading"><h2>매장정보</h2></div>{base_rows(platform)}</section>'
    return f'<div class="restaurant" id="top">{header}{tabs(platform)}{intro}<section id="info" class="quick-info">{base_rows(platform)}</section>{menu}{photos}<footer class="listing-footer">{"kakaomap" if platform=="kakao" else "Google"} · 가게 정보</footer></div>'


def map_svg(platform):
    # Local fictional map, for page context only. No live tiles or real-store markers.
    labels = [('성수역', 440, 390), ('성수이로', 700, 260), ('연무장길', 305, 570), ('성수동', 770, 700)] if platform == 'kakao' else [('망원역', 420, 380), ('망원로', 660, 270), ('월드컵로', 240, 600), ('망원동', 800, 680)]
    blocks = ''.join(f'<rect x="{x}" y="{y}" width="{100 + (x+y)%60}" height="{60+(x+y)%80}" rx="7" fill="{["#eae7e0", "#ede9e3", "#e7e5df"][(x+y)%3]}"/>' for x in range(30, 1200, 180) for y in range(30, 1000, 150))
    streets = ''.join(f'<path d="M0 {y} 1200 {y-80}"/>' for y in [130,310,540,760,960]) + ''.join(f'<path d="M{x} 0 {x+80} 1000"/>' for x in [130,400,680,950])
    words = ''.join(f'<text x="{x}" y="{y}" font-size="19" fill="#7c817b">{t}</text>' for t, x, y in labels)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1000" viewBox="0 0 1200 1000"><rect width="1200" height="1000" fill="#f3f1ed"/>{blocks}<path d="M1040 0h160v390l-70-45-90-170Z" fill="#d7e7c9"/><g fill="none" stroke="#ddd7ca" stroke-width="29">{streets}</g><g fill="none" stroke="#fff" stroke-width="23">{streets}</g><path d="M0 825 1200 700" stroke="#f9f4d4" stroke-width="48"/>{words}<g transform="translate(640 470)"><path d="M0-34c-20 0-32 14-32 31 0 24 32 54 32 54S32 21 32-3C32-20 20-34 0-34Z" fill="{"#2b7de9" if platform=="kakao" else "#ea4335"}"/><circle cy="-3" r="11" fill="white"/></g></svg>'
    (ASSETS / f'{platform}_map.svg').write_text(svg, encoding='utf-8')


def page(platform):
    c = DATA[platform]
    topbar = '<header class="kakao-header"><img src="assets/kakaomap.svg" alt="카카오맵"><div class="header-search">온담식탁 성수점'+icon('search')+'</div><span>로그인</span></header>' if platform == 'kakao' else '<header class="google-search">'+icon('back')+'<span>소담면가 망원점</span>'+icon('search')+icon('close')+'</header>'
    notice = '<div class="example-notice"><a href="index.html">← 두 지도 비교</a><span>가상 식당 · 정보·사진·평점은 설명용 설정</span></div>'
    return f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{c["name"]} | {platform} 지도 정비 예시</title><link rel="stylesheet" href="showcase.css"></head><body class="platform-{platform}">{notice}{topbar}<div class="map-context" aria-hidden="true"></div><main class="page-content">{restaurant(platform)}</main><dialog id="photo-dialog"><button class="close-dialog" aria-label="사진 닫기">{icon("close")}</button><div class="dialog-photo"></div><p></p></dialog><script src="showcase.js"></script></body></html>'


for platform in ('google', 'kakao'):
    map_svg(platform)
    (ROOT / f'{platform}.html').write_text(page(platform), encoding='utf-8')

index = '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GEO 지도 페이지 정비 예시</title><link rel="stylesheet" href="showcase.css"></head><body class="showcase-index"><header class="showcase-heading"><div><span class="eyebrow">SEELO · MAP INFORMATION</span><h1>사진은 풍성하게, 정보는 명확하게.</h1><p>가상 식당으로 구성한 구글·카카오 지도 페이지 정비 예시</p></div><span class="example-badge">FICTIONAL EXAMPLE</span></header><main class="comparison"><section class="platform-example"><div class="example-title"><div><span class="platform-mark g-mark">G</span><h2>Google 지도</h2></div><a href="google.html">페이지 크게 보기 ↗</a></div><iframe src="google.html?embed=1" title="Google 지도 소담면가 가상 예시"></iframe></section><section class="platform-example"><div class="example-title"><div><img src="assets/kakaomap.svg" alt="카카오맵"><h2 class="sr-only">카카오맵</h2></div><a href="kakao.html">페이지 크게 보기 ↗</a></div><iframe src="kakao.html?embed=1" title="카카오맵 온담식탁 가상 예시"></iframe></section></main><footer class="showcase-footer">가게·주소·연락처·평점·운영 조건은 가상 설정이며, 사진은 예시용 생성 이미지입니다.</footer></body></html>'''
(ROOT / 'index.html').write_text(index, encoding='utf-8')
(ROOT / 'fictional_facts.json').write_text(json.dumps(DATA, ensure_ascii=False, indent=2), encoding='utf-8')
assert len(DATA['kakao']['showcase_intro']) <= 40
assert all(m['price'] in (ROOT / f'{p}.html').read_text(encoding='utf-8') for p in ('google', 'kakao') for m in DATA[p]['menus'])
print(json.dumps({'pages': ['index.html', 'google.html', 'kakao.html'], 'kakao_intro_chars': len(DATA['kakao']['showcase_intro']), 'fictional': True}, ensure_ascii=False))
