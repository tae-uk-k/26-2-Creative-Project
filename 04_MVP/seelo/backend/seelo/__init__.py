"""seelo 베타 백엔드."""

import asyncio
import sys

# psycopg 비동기는 Windows 기본 이벤트 루프(Proactor)를 쓰지 못한다(17 5장).
# Playwright는 반대로 Proactor가 필요하므로 fix 워커는 Windows에서 띄우지 않는다.
if sys.platform == "win32":  # pragma: no cover - Windows 개발 환경 전용
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
