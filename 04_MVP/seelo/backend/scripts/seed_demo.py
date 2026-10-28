"""시드 계정 만들기(17 2장) — 2단계 뼈대: 계정만. 가게·측정·정비 상태는 해당 단계에서 더한다.

실행: python scripts/seed_demo.py --reset
- APP_ENV=prod면 거부한다.
- 모든 계정은 이메일 인증·약관 동의 완료 상태다.
- 비밀번호는 아래 DEMO_PASSWORD 하나다(문서·채팅에 적지 않는다).
- 이메일 도메인 .test는 실제로 메일이 가지 않는 예약 도메인이다.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text  # noqa: E402

from seelo.config import get_settings  # noqa: E402
from seelo.db import dispose_engine, session_scope  # noqa: E402
from seelo.models.user import AuthIdentity, User  # noqa: E402
from seelo.security.passwords import hash_password  # noqa: E402
from seelo.timeutil import now_utc  # noqa: E402

DEMO_PASSWORD = "SeeloDemo2026"

# (이메일, 역할, 목표 S07 카드). 카드 상태는 해당 단계에서 채운다(17 2장 표).
ACCOUNTS: list[tuple[str, str, str]] = [
    ("admin@seelo.test", "admin", "-"),
    ("nostore@seelo.test", "owner", "no_store"),
    ("measuring@seelo.test", "owner", "measuring"),
    ("failed@seelo.test", "owner", "measure_failed"),
    ("diagnosed@seelo.test", "owner", "diagnosed"),
    ("changed@seelo.test", "owner", "free_used_store_changed"),
    ("requested@seelo.test", "owner", "fix_requested"),
    ("rejected@seelo.test", "owner", "fix_rejected"),
    ("connect@seelo.test", "owner", "connect_needed"),
    ("preparing@seelo.test", "owner", "plan_preparing"),
    ("approve@seelo.test", "owner", "plan_needs_approval"),
    ("fixing@seelo.test", "owner", "fixing"),
    ("waiting@seelo.test", "owner", "remeasure_waiting"),
    ("remeasuring@seelo.test", "owner", "remeasuring"),
    ("refailed@seelo.test", "owner", "remeasure_failed"),
    ("report@seelo.test", "owner", "report_ready"),
    ("revoked@seelo.test", "owner", "fixing+revoked"),
]


async def reset_service_tables() -> None:
    async with session_scope() as s:
        rows = await s.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename <> 'alembic_version' AND tablename NOT LIKE 'procrastinate%'"
            )
        )
        tables = [r[0] for r in rows]
        if tables:
            await s.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
        await s.commit()


async def seed_accounts() -> int:
    pw_hash = hash_password(DEMO_PASSWORD)
    now = now_utc()
    created = 0
    async with session_scope() as s:
        for email, role, _card in ACCOUNTS:
            if await s.scalar(select(User.id).where(User.email == email)):
                continue
            user = User(
                email=email,
                email_verified_at=now,
                password_hash=pw_hash,
                role=role,
                terms_agreed_at=now,
            )
            s.add(user)
            await s.flush()
            s.add(AuthIdentity(user_id=user.id, provider="email", provider_user_id=None))
            created += 1
        await s.commit()
    return created


async def main(reset: bool) -> int:
    if get_settings().app_env == "prod":
        print("APP_ENV=prod에서는 시드를 만들지 않는다")
        return 1
    try:
        if reset:
            await reset_service_tables()
        n = await seed_accounts()
        print(f"seed: 계정 {n}개 만듦(전체 {len(ACCOUNTS)}개)")
    finally:
        await dispose_engine()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="서비스 테이블을 비우고 다시 만든다")
    raise SystemExit(asyncio.run(main(parser.parse_args().reset)))
