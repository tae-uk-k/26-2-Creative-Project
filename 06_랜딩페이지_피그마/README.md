# seelo 랜딩페이지 (피그마 → HTML/CSS)

피그마 파일의 `Home / 메인 - 1 전체 (수정안)` 화면을 정적 HTML/CSS로 옮긴 것입니다.
빌드 도구 없이 `index.html`을 브라우저로 열면 바로 보입니다.

- `index.html` — 마크업 (히어로 · 이용 방법 · 사장님이 하지 않아도 되는 일 · 진단 리포트 · 무료 안내 · FAQ · 마무리 · 푸터)
- `style.css` — 색(lilac/violet), 글자(Noto Sans KR, Pacifico), 유리 카드·오목 효과 스타일. 1100px, 720px 이하 반응형 포함
- `script.js` — 배경 안개 위치 생성, FAQ 한 번에 하나만 열기

## 알아둘 점
- 지도 배경과 아이콘은 피그마 벡터를 내려받지 못해 CSS/SVG로 다시 그렸습니다. 피그마 원본과 모양이 조금 다를 수 있습니다.
- FAQ는 첫 번째 질문만 답변이 있습니다. 나머지 5개 질문은 피그마 시안에 답변 문구가 없어 비워 두었습니다 (`index.html`의 TODO 주석 참고).
- 기존 Flask 앱(`app.py`, `templates/`, `static/`)은 건드리지 않았습니다.
