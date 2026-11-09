# 시안 D 새 표지

- 작업일: 2026-11-09
- 새 표지: https://www.figma.com/design/M5WCPZN32W6PEeIaEvcRkC/?node-id=1118-19
- 위치: 시안 D 바로 위. 기존 1페이지 `1114:4573`은 보존.
- 참고: 첨부된 두 표지의 큰 왼쪽 제목·오른쪽 입체 그래픽 구성. 시안 B의 강조 문구 위치와 D 6페이지의 파랑·초록 색상.
- 새 표지의 글자·화살표·배경·이미지는 모두 슬라이드 바로 아래 개별 요소. 내부 프레임·그룹·오토레이아웃 추가 없음.
- 시안 D 2~9페이지: B에서 색으로 강조한 제목·수치·핵심 항목 중 문구가 일치하는 36개 텍스트에 파랑·초록 적용. 문구·배치 유지.
- 1페이지 최신 수정: 두 번째 참고 이미지처럼 어두운 초록 배경 `#083D33` → `#14634D`, 흰색 제목과 밝은 파랑·초록 강조. 문구·배치·기존 표지 유지.
- 5페이지 최신 수정: 부분 네온 8개 전부 제거. 남은 네온 0개 확인.
- 3페이지: 현재 초록 유리 가게 이미지가 이미 반영된 상태를 확인해 보존.

## 결과 파일

- `D_cover_v1.png`: 새 표지 확인 이미지.
- `D_cover_dark_v2.png`: 현재 어두운 초록 표지.
- `D_page5_no_neon_v2.png`: 현재 네온을 모두 제거한 5페이지.
- `assets/D_cover_glass_store_v1.png`: 표지 입체 그래픽 원본, 투명 PNG.
- `D_page5_soft_neon_v1.png`: 흐린 네온 적용 확인 이미지.
- `assets/store_green_glass_v7.png`: 앞선 3페이지용으로 생성한 초록 유리 가게 원본.

## 어두운 초록 9장 비교본

- Figma: https://www.figma.com/design/M5WCPZN32W6PEeIaEvcRkC/?node-id=1126-11
- 섹션: `seelo · D · 어두운 초록 버전 · 9장`.
- 원본 오른쪽 400px 간격에 복제. 기존 문구·배치·이미지·상자 형태 유지.
- 1페이지는 사용자가 수정한 현재 D 표지 내용을 복제. 2~9페이지 배경은 같은 어두운 초록 그라데이션 적용.
- 본문 카드는 원본의 밝은 색과 진한 글자 유지. 상자 밖 제목·본문·관계선은 밝은 파랑·초록·흰색으로 대비 조정.
- 원본 변경 없음, 네온 0개, 내부 프레임 0개, 오토레이아웃 0개 확인.
- `D_dark_all_v3.png`: 9장 전체 미리보기.
- `D_dark_page3_v3.png`, `D_dark_page4_v3.png`, `D_dark_page6_v3.png`: 주요 페이지 확인 이미지.

## 이미지 생성

- 실행: 내장 image_gen, 투명 배경 true.
- 참고 이미지 1: 파란 유리 플랫폼 R&D 표지.
- 참고 이미지 2: 녹색 ESG 표지.
- 참고 이미지 3: 앞서 생성한 초록 글라스 가게.
- 최종 생성 프롬프트:

Use case: stylized-concept. Asset: transparent-background 3D hero illustration, to be placed on the RIGHT half of a white Korean startup project cover slide. Reference image 1: use its clean isometric layered clear glass platform, blue technology objects, luminous edges, visual depth and generous whitespace. Reference image 2: use its harmonious emerald green volume, polished soft 3D materials, floating data panel and dynamic curved movement; DO NOT copy its dark background or globe. Supporting image 3: preserve the familiar small bakery/shop shape, rounded glass surface finish and emerald storefront from this project. Create ONE coherent isometric composition about helping local businesses appear in AI recommendations: a beautiful small frosted white translucent GLASS SHOP with green tinted pitched roof and green/clear striped awning, clear display window and door, standing on a low layered rounded square clear glass platform. Around the shop float ONE blue translucent MAP PIN at the upper left/back, ONE small green CHAT BUBBLE at upper right/back, and ONE small clear glass ANALYTICS PANEL at lower right showing three simple blue/green bars and a rising line. These objects are supporting small satellites; the SHOP is the central dominant object. Add one subtle sweeping blue-to-green translucent arc behind the shop connecting the pin and chat bubble, without arrowheads. No large globe. Materials are smooth frosted milky glass and transparent softly beveled resin, bright white rim highlights, soft ambient refraction, restrained blue and saturated fresh emerald accents, no metal, no faceted jewel crystal. Elevated three-quarter view, broad shopfront facing viewer and slightly LEFT toward the text area of the slide; right side wall visible. Balanced tall-square composition, all elements fully visible with transparent margins. Clean professional presentation artwork, simple readable geometry, pale clear base, soft studio lighting, subtle soft grounding shadow. Genuine transparent background, not a white square and not a black backdrop. NO text, NO numbers, NO letters, NO logo, NO watermarks, NO people, NO chef, NO Memoji, NO real brand logos. Blank shop sign.
