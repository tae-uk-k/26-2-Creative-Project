"""시험 메일 한 통 등록(W-10-1 수신 확인용). 워커(email 큐)가 실제로 보낸다.

실행: python scripts/send_test_mail.py --to someone@example.com
- 관리자용 템플릿(fix_requested)에 "시험 발송" 값을 넣어 보낸다. 사장님 데이터는 쓰지 않는다.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seelo.db import dispose_engine, session_scope  # noqa: E402
from seelo.services import email_service  # noqa: E402
from seelo.worker.app import app  # noqa: E402


async def main(to: str) -> int:
    try:
        async with app.open_async():
            async with session_scope() as s:
                log_id = await email_service.queue(
                    s,
                    "fix_requested",
                    to=to,
                    params={"request_id": 0, "store_name": "시험 발송"},
                )
                await s.commit()
        print(f"queued email_log_id={log_id}")
    finally:
        await dispose_engine()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--to", required=True)
    raise SystemExit(asyncio.run(main(p.parse_args().to)))
