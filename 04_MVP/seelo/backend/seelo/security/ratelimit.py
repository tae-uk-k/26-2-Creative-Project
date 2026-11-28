"""요청 제한(05 10장): rate_limits 테이블에 분 단위로 센다(Redis 없음)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from seelo.errors import AppError
from seelo.timeutil import now_utc

# 키 이름과 분당 한도(05 10장)
LIMITS = {"signup": 5, "pwreset": 5, "resend": 5, "identify": 10}

_HIT_SQL = text(
    """
    INSERT INTO rate_limits (key, window_start, count)
    VALUES (:k, :w, 1)
    ON CONFLICT (key, window_start) DO UPDATE SET count = rate_limits.count + 1
    RETURNING count
    """
)


async def hit(db: AsyncSession, kind: str, subject: str | int) -> None:
    """kind:subject 키의 이번 분 횟수를 1 올린다. 한도를 넘으면 센 값을 커밋하고 429를 던진다.

    한도 안이면 커밋하지 않는다(부르는 쪽 트랜잭션과 함께 커밋된다).
    """
    limit = LIMITS[kind]
    # 창은 앱 시계로 정한다(DB now()와 같은 분 단위). 테스트가 시간을 멈춰 경계를 피할 수 있다
    now = now_utc()
    window = now.replace(second=0, microsecond=0)
    count = await db.scalar(_HIT_SQL, {"k": f"{kind}:{subject}", "w": window})
    if count is not None and count > limit:
        await db.commit()
        raise AppError("RATE_LIMITED", {"retryAfterSeconds": max(1, 60 - now.second)})
