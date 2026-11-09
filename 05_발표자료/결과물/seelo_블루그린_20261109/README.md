# seelo 선명한 파랑·초록 발표 시안

- 작업일: 2026-11-09
- Figma: https://www.figma.com/design/ddjbzEoo5hZmnAXsRdUqpc/?node-id=1-187
- 현재 적용본: 선명한 포인트 + 3D 미모지 v3
- 후속 작업: 원본의 옅은 회색 그라데이션 상자 복원, 부분 네온을 아래·오른쪽으로 변경. 원래 프로젝트 파일의 시안 D 새 표지와 글자 강조는 `D_표지_작업기록.md` 참고.

## 현재 디자인

- 전체 9장은 흰색 바탕과 중립색 테두리를 사용. 포인트는 파랑 `#007AFF`, 진한 파랑 `#0067E8`, 초록 `#00CF7D`.
- 글자 박스는 흰색·밝은 중립색과 진한 글자로 통일. 포인트는 박스 바깥 선·설명 도형·흐름 화살표에 적용.
- 5페이지는 상자 모서리 일부에만 파랑·초록 네온 선과 바깥으로 번지는 빛을 추가. 상자 뒤의 개별 벡터 8개로 편집 가능하며 글자·상자 배치 유지.
- 4페이지 사용 흐름은 오른쪽 여백 100px을 두고 세로 배치. 기존 단계·문구를 유지하고 화살표는 아래 방향으로 변경. 내부 프레임·오토레이아웃 추가 없음.
- 2·4·5페이지의 대비를 복구하고 8페이지의 진한 글자 박스도 제거. 진한 글자 박스 배경 0개 확인.
- 3페이지는 첨부 참고 이미지처럼 왼쪽 사장님, 가운데 곡선 화살표, 오른쪽 플랫폼 로고 구성.
- 현재 정비 가능: Google 지도·카카오맵 로고를 각각 212×212로 강조.
- 확장 후보: 네이버 지도·Bing·Tripadvisor·Instagram 로고를 각각 80×80으로 한 줄에 배치.
- 사장님은 첨부 참고 이미지와 같은 단순한 3D 미모지 콧수염 요리사로 교체.
- 슬라이드 틀 9개만 유지. 내부 프레임·그룹·오토레이아웃은 0개. 이미지·글자·도형을 슬라이드 바로 아래에 직접 배치.
- 카드·내비게이션 배경은 일반 사각형. 7페이지 화면 예시는 개별 이미지 3개.

## 확인

- 슬라이드 크기 1920×1080 유지.
- 기존 글꼴 IBM Plex Sans KR·Pacifico·Plus Jakarta Sans 유지.
- 캐릭터·현재 로고 2개·확장 로고 4개 업로드 및 배치 확인.
- `page3_memoji_v3.png`와 `all_slides_vivid_v2.png` 시각 검수.

## 파일

- `assets/owner_chef_memoji_v3.png`: 현재 사용하는 3D 미모지 요리사.
- `assets/google_maps.jpg`, `kakao_map.jpg`, `naver_map.jpg`, `bing.jpg`, `tripadvisor.jpg`, `instagram.jpg`: 해당 개발사가 Apple App Store에 게시한 앱 로고.
- `assets/sources.json`: 게시자·메타데이터 URL·다운로드 URL.
- `page3_memoji_v3.png`: 현재 3페이지 결과.
- `page2_readability_v4.png`, `page4_readability_v4.png`, `page5_readability_v4.png`: 가독성과 바깥 포인트를 수정한 현재 결과.
- `page5_neon_v5.png`: 5페이지 모서리 부분 네온 적용 결과.
- `page4_vertical_v6.png`: 4페이지 사용 흐름 세로 배치 결과.
- `all_slides_vivid_v2.png`: 미모지 교체 전 전체 색감 확인용 결과.
- 나머지 PNG는 앞선 작업의 중간 결과로 보존.

## 현재 캐릭터 생성

- 실행 방식: 기본 내장 image_gen 도구.
- 투명 배경: true.
- 생성 프롬프트:

Use the attached image as the DEFINITIVE STYLE REFERENCE. Match its Apple Memoji / Animoji sticker aesthetic: an unmistakably stylized, simplified 3D emoji avatar with a large rounded head, smooth matte peach skin, simple softly sculpted cheeks and nose, large clean almond-shaped dark eyes, solid sculpted eyebrows and hair shapes, and soft even ambient lighting. Transform the subject into a friendly MIDDLE-AGED KOREAN MALE RESTAURANT OWNER AND CHEF, around 50 years old, neat thick dark moustache, no beard, short dark sculpted hair with a little grey at the temples, warm approachable smile. White chef toque and white chef jacket, vivid blue neckerchief. Head and shoulders / upper chest bust, front-facing, centered. Keep the proportions, simple facial feature construction and soft emoji rendering very close to the reference, not the woman's identity or clothing. IMPORTANT: not a real human, no photorealistic skin, no pores, no individual hair strands, no realistic facial rendering, no 2D illustration, no vector drawing, no black contour outlines, no cel shading, no anime, no comic style. One single actual 3D Memoji-style avatar, minimal detail like the reference sticker. Genuine transparent background, no scenery, no badge, no shadow on ground, no text or watermark. Entire chef hat and shoulders visible with transparent margins. Do not include a hand or props.
