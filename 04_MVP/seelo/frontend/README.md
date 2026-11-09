# seelo frontend

React 화면은 아직 범위가 아니다(백엔드 구현계획 00 5장). API 계약은 `01_기획/개발/백엔드_구현계획/04_API.md`,
타입은 `backend/scripts/export_openapi.py`로 만든 `openapi.json`을 쓴다(17 4장).

계약을 갱신·검사하려면 `backend`에서 실행한다.

```bash
uv run python scripts/export_openapi.py
uv run python scripts/export_openapi.py --check
```

설정 파일·실행 중인 서버·실제 키는 필요 없다. API 변경 뒤 계약을 다시 생성한다.
가짜 개발 환경의 카드별 시연 데이터는 `python scripts/seed_demo.py --scenarios`로 추가한다.
기존 가게와 무료 사용 이력은 보존하므로 이미 사용한 시연 계정의 카드는 새 DB와 다를 수 있다(17 2장).
