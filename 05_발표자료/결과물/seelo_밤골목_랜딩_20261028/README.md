# seelo 밤 골목 랜딩 (HTML)

스크롤하면 1인칭으로 밤 골목을 걸어 들어가 불 켜진 가게 앞에 도착하는 랜딩 페이지. 파일 하나(`index.html`)로 동작한다.

## 열어 보기

`index.html`을 브라우저로 열면 된다. 글꼴(Noto Sans KR, Manrope)만 Google Fonts에서 불러오므로 인터넷이 필요하다.

## 수정 위치 (`index.html` 안에서 검색)

| 바꾸고 싶은 것 | 찾을 문자열 |
| --- | --- |
| 색상·글꼴 토큰 | `:root{` (맨 위 `--lamp`, `--night-*`, `--cream` 등) |
| 노란 버튼 색 | `.btn-lamp` |
| 입력칸 색 | `.finder{` (첫 화면 끝), `.reg{` (맨 아래) |
| 걷는 중 소개 박스 문구 | `id="info1"`, `id="info2"`, `id="info3"` |
| 소개 박스 색·크기 | `.info{` |
| 첫 화면 제목·버튼 | `<div class="intro"` |
| 골목 끝 문구 | `<div class="cta"` |
| 이용 방법 5단계 | `<section class="sec how"` |
| 리포트 예시 수치 | `<section class="sec report"` |
| FAQ | `<div class="faq"` |
| 걷는 길이 | `.hero{position:relative;height:340svh}` (숫자가 클수록 길어짐) |
| 박스가 뜨는 시점 | `const WIN=[[.17,.38],[.36,.57],[.55,.76]]` (0~1, 스크롤 진행률) |

## 메모

- 로그인·회원가입·무료 진단 버튼은 시안이라 실제 이동 대신 안내 메시지를 띄운다.
- 리포트 수치(40%→60% 등)는 Figma 프로토타입의 예시 값이다.
- 화면 크기별 확인: 1280×720, 1366×768, 1536×864, 모바일 390px.
