# 실제 지도 HTML 기반 GEO 정비 예시

2026-11-09. 이전 시안을 보존하고 별도 폴더에서 다시 만들었다.

## 열기

- `index.html`: 카카오·Google·원본 대조 화면 전환.
- `kakao.html`, `kakao_menu.html`: 온담식탁 성수점 가상 예시의 홈·메뉴.
- `google.html`, `google_menu.html`, `google_info.html`: 소담면가 망원점 가상 예시의 개요·메뉴·정보.
- `kakao_reference.html`, `google_reference.html`: 읽은 실제 DOM을 변경하지 않은 대조용 화면. 스크립트·추적 기능·외부 동작은 제거했다.
- `추가입력항목_조사.md`: 실제 가게에서 확인한 추가 정보와 공식 입력 지원 범위, 업주 입력과 플랫폼 생성 정보 구분.
- `preview.html`: 최종 브라우저 캡처를 담은 단일 HTML 미리보기.

## 제작 근거

브라우저에서 실제 카카오 파르코·명동피자, Google 힛사츠와자·파르코·명동피자·명동교자 페이지를 열었다. 페이지의 실제 HTML, CSS 자산, 메뉴·정보 탭을 읽었다. `source/`에 읽은 DOM과 출처를, `assets/`에 원본 CSS·SVG 및 사진을 저장했다.

카카오 공개 UI의 `board_photo`, `wrap_actionbtn`, `tab_primary`, `list_goods`와 Google의 상세 패널·검색창·탭·메뉴·속성 DOM을 재사용했다. CSS 파일의 이미지 경로는 로컬 파일에 맞게 변경했다. Google의 일부 글꼴 URL은 인터넷이 필요하다.

카카오 본문 너비는 실제 페이지와 재현본이 모두 602px(600px 내부 + 테두리), 사진 격자는 552px였다. 탭과 메뉴의 글꼴·줄 높이도 브라우저에서 비교했다. Google 상세 패널은 실제로 관찰한 408px, 검색창은 376px를 사용했다.

매장·사진·수치·운영 조건은 가상 예시다. Google 지도 배경은 참고 화면 이미지에 계정 가림과 가상 라벨을 적용했다. 지도 이동·저장·리뷰 등록 등 서비스 전체의 기능을 구현하지 않았다. 서로 다른 화면 상태에서 값의 길이·항목 수가 달라지므로 화면 전체가 픽셀 단위로 동일하다고 주장하지 않는다.

실제 DOM을 확인하지 못한 소개 카드 배치는 화면에 추가하지 않았다. 소개 초안은 이전 `geo_clean_showcase_20261109/fictional_facts.json`에 보존돼 있다. 메뉴 설명과 조건은 기존 가상 사실만 사용했다. 구글 정보 탭의 화장실·결제수단은 해당 가상 매장에서 제공한다고 설정한 추가 예시이며 실제 가게 검증 결과가 아니다.

## 재생성·검사

```powershell
python 02_조사/geo_native_pages_20261109/build_native.py
python 02_조사/geo_native_pages_20261109/verify_native.py
node --check 02_조사/geo_native_pages_20261109/native-controls.js
```

`build_native.py`의 원본 자산은 `assets/`에 보존돼 있다. 개발 중 생성한 임시 bundle 경로가 없어진 경우에는 해당 디렉터리를 다시 내려받지 않고 보존된 파일을 사용한다. 새 원본을 받는 절차와 완성 HTML을 보는 절차는 별개다.
