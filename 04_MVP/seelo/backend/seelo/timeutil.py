"""시간 도우미(13 4장). DB는 UTC, '하루'는 한국 시간 기준."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_utc() -> datetime:
    return datetime.now(UTC)


def kst_day_range(at: datetime | None = None) -> tuple[datetime, datetime]:
    """at이 속한 한국 날짜의 [00:00, 다음날 00:00)을 UTC로."""
    at = at or now_utc()
    d = at.astimezone(KST).date()
    start = datetime(d.year, d.month, d.day, tzinfo=KST)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def kst_date(at: datetime) -> date:
    return at.astimezone(KST).date()
