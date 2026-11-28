# seelo 발표자료 · Apple / Toss 비교 시안

같은 1~3장 내용을 두 가지 시각 체계로 제작했다. 기존 백지 PPT와 앞서 만든 시안은 수정하지 않았다.

## Figma

- 페이지: `12:2` 발표자료 모음
- [Apple 3장](https://www.figma.com/design/M5WCPZN32W6PEeIaEvcRkC?node-id=562-54)
- [Toss 3장](https://www.figma.com/design/M5WCPZN32W6PEeIaEvcRkC?node-id=562-189)
- 각 장은 1920 × 1080. 위쪽 Apple, 아래쪽 Toss. 공통 컴포넌트는 두 구역 아래에 분리했다.

| 내용 | Apple | Toss |
| --- | --- | --- |
| 서비스 소개 | 562:60 | 562:195 |
| 문제 정의 | 562:83 | 562:218 |
| UX 인사이트 · 가치제안 | 562:140 | 562:271 |

## 적용 방식

- Apple: 설치한 `apple-liquid-glass`의 차가운 회색 바탕, 흰 단일 패널, 얇은 구분선, 큰 타이포, 한 가지 파란 강조색을 발표용으로 적용했다.
- Toss: `use-design-md`로 토스 디자인 문서를 전부 확인하고, `toss-design-system` 및 공식 TDS Colors 문서의 blue500·grey 팔레트, 평면 표면, 정보 묶음, 라운드 체계를 적용했다.
- 발표용 크기와 다단 구성은 이번 작업에서 정한 값이며 Apple/Toss의 공식 발표자료 템플릿이라는 뜻은 아니다.
- Figma 라이브러리 검색 후 macOS 26 기본 색상과 텍스트 스타일을 가져오려 했지만 라이브러리 가져오기 권한이 없어 설치한 스킬의 토큰을 로컬 변수·텍스트 스타일로 구성했다. 공식 라이브러리 인스턴스와 연결된 산출물은 아니다.
- Pretendard는 현재 Figma 가용 목록에 없고, SF Pro는 목록에 보이지만 실제 렌더러에서 missing font로 확인됐다. 두 버전의 한글과 숫자는 Noto Sans KR, 기존 seelo 워드마크는 Pacifico를 사용했다. 새로운 폰트를 임의 배포하지 않았다.
- 글라스모피즘은 사용하지 않았다.

## 내용과 검수

- 1장: 승인된 기존 표지 `545:6`의 소개·설명·3단계 문구. 이미지 없음.
- 2장: 원본 `468:21`의 문제 정의 3개, 53%, 집단 비교와 출처를 반영했다.
- 3장: 원본 `468:81`의 UX 인사이트와 가치제안 문장을 반영했다. 표지의 진단 → 정보 정비 → 전후 비교를 도식으로 연결했다.
- 버전당 원본 텍스트 노드 25개를 사용했다. 반복 배치를 포함한 56개 대응 항목을 실제 원본과 공백·줄바꿈을 제외하고 대조해 불일치 0개를 확인했다.
- 원본의 ___%는 그대로 유지했다. 미기입 수치를 추측하거나 수치가 있는 것처럼 막대 높이를 만들지 않았다.
- 기존 최상위 프레임의 이름·위치·크기와 대조 원본 문장 변경 0개. 백지 원본은 루트 포함 269개 노드다.
- 최소 글자 크기 28px. 최종 6장 모두 텍스트 간 겹침 0, 텍스트의 자동 레이아웃 부모 이탈 0, 누락 글꼴 0, 비정상 텍스트 높이 0.
- 6장 모두 텍스트·벡터·도형·프레임·컴포넌트 인스턴스로 편집할 수 있다. 전체 UI를 이미지로 붙여 넣은 레이어는 없다.
- 실제 Figma 렌더링 스크린샷으로 검수했다. 첫 렌더에서 발견한 1px 텍스트 높이는 resize 이후 HEIGHT를 적용하도록 고쳤고, 숫자 누락은 가용 서체로 교체해 해결했다.

## 파일

- `apple-final.png`: 최종 Apple 3장 미리보기
- `toss-final-refined.png`: 최종 Toss 3장 미리보기
- `생성결과.json`: 최초 생성한 노드 ID, 원본 텍스트 대응
- `검수결과.json`: 텍스트 재배치 및 내용 대조 결과
- `build-figma.js`: 생성 스크립트. 최종 텍스트 높이·서체 처리 반영

## 참고

- Apple 스킬: https://github.com/naplesblue/apple-design-skill
- 토스 적용 문서: https://www.getdesign.kr/services/toss/llms.txt
- 토스 공식 색상: https://tossmini-docs.toss.im/tds-mobile/foundation/colors/
- 토스 스킬: https://github.com/pinion05/toss-design-system-skill
