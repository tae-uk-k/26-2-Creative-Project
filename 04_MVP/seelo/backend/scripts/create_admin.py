"""인증을 마친 계정을 관리자로 바꾼다(01 2장). 관리자 계정은 이 스크립트로만 만든다.

실행: python scripts/create_admin.py --email someone@example.com [--revoke]
- 가입·이메일 인증을 먼저 마친 계정만 바꾼다. 비밀번호는 다루지 않는다.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from seelo.db import dispose_engine, session_scope  # noqa: E402
from seelo.models.user import User  # noqa: E402
from seelo.security.tokens import normalize_email  # noqa: E402


async def set_role(email: str, role: str) -> str:
    async with session_scope() as s:
        user = await s.scalar(select(User).where(User.email == normalize_email(email)).with_for_update())
        if user is None:
            return "계정이 없다. 먼저 가입하라"
        if user.email_verified_at is None:
            return "이메일 인증을 마치지 않은 계정이다"
        if user.role == role:
            return f"이미 역할이 {role}(user_id={user.id})"
        user.role = role
        await s.commit()
        return f"역할 → {role}(user_id={user.id})"


async def main(email: str, revoke: bool) -> int:
    try:
        print(await set_role(email, "owner" if revoke else "admin"))
    finally:
        await dispose_engine()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--revoke", action="store_true", help="관리자 권한을 거두고 owner로 되돌린다")
    args = p.parse_args()
    raise SystemExit(asyncio.run(main(args.email, args.revoke)))
