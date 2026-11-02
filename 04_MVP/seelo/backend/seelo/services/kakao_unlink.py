"""카카오 연결 해제: 로그인 연결·세션·가입 대기만 폐기하고 가게/진단은 보존한다.

인증은 대표 어드민 키 원문 대신 SHA-256 비교값으로 한다. 이 값으로는 카카오 관리 API를
호출할 수 없다. 공개 등록 전 계정 복구·데이터 보존 정책을 운영자가 확인해야 한다.
"""

import hashlib
import hmac
import re

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.models.user import AuthIdentity, AuthToken, PendingSignup, Session
from seelo.timeutil import now_utc


def authorized(header: str, expected_digest: str) -> bool:
    if not re.fullmatch(r"[a-f0-9]{64}", expected_digest) or len(header) > 512:
        return False
    scheme, separator, key = header.partition(" ")
    if scheme != "KakaoAK" or not separator or not key or key.strip() != key:
        return False
    supplied = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return hmac.compare_digest(supplied, expected_digest)


async def disconnect(db: AsyncSession, provider_user_id: str) -> None:
    # 동일 웹훅을 다시 받아도 다른 사용자나 서비스 데이터에는 영향을 주지 않는다.
    identity = await db.scalar(
        select(AuthIdentity)
        .where(AuthIdentity.provider == "kakao", AuthIdentity.provider_user_id == provider_user_id)
        .with_for_update()
    )
    if identity is not None:
        await db.execute(delete(Session).where(Session.user_id == identity.user_id))
        await db.execute(
            update(AuthToken)
            .where(AuthToken.user_id == identity.user_id, AuthToken.used_at.is_(None))
            .values(used_at=now_utc())
        )
        await db.delete(identity)
    await db.execute(
        delete(PendingSignup).where(
            PendingSignup.provider == "kakao", PendingSignup.provider_user_id == provider_user_id
        )
    )
    await db.commit()
