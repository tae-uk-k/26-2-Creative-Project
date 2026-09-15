# 발표 대본 텔레프롬프터 (Presentation Avatar Assignment)

발표 대본을 입력하거나 PDF로 업로드하면 문장 단위로 자동 분리되어 저장되고,
화면에는 한 번에 한 문장만 나타났다가 사라지는 방식으로 표시됩니다. 수동으로
이전/다음 버튼을 눌러 넘기거나, 자동재생을 켜서 지정한 간격(초)마다 자동으로
다음 문장으로 넘어가게 할 수 있습니다.

## 구조

- **`app.py`** — Python(Flask) 서버. 페이지 렌더링과 대본 저장/조회 API를 담당합니다.
  - `GET /` — `index.html` 페이지를 반환
  - `GET /api/script` — 저장된 대본(JSON) 조회
  - `POST /api/script` — 입력한 텍스트를 문장 단위로 분리해 JSON에 저장
  - `POST /api/script/upload` — PDF 업로드 시 텍스트를 추출해 문장 단위로 분리, JSON에 저장
- **`templates/index.html`** — 화면 전체를 구성하는 단일 페이지. 대본 입력창, PDF 업로드, 한 줄씩 나타났다 사라지는 표시 영역(이전/다음, 자동재생, 줄 간격 조절)으로 구성됩니다.
- **`static/script.js`**, **`static/style.css`** — 프론트엔드 동작과 스타일
- **`data/scripts.json`** — 분리된 대본 문장들이 저장되는 데이터 파일. 페이지 로드 시 이 파일을 불러와 화면에 표시합니다.

## 실행 방법

```bash
pip install -r requirements.txt
python app.py
```

실행 후 `http://127.0.0.1:5000` 접속.
