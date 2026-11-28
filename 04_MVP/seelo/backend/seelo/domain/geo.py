"""거리·좌표(07 3.3·4.3, 14 2.3). IO 없음."""

import math

EARTH_RADIUS_M = 6_371_008.8  # 평균 지구 반지름(IUGG)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def parse_naver_coord(v: str | int | float) -> float:
    """네이버 mapx·mapy. 정수이고 절댓값이 1000보다 크면 1e7로 나눈다(예: 1269858123 → 126.9858123)."""
    s = str(v).strip()
    if s.lstrip("-").isdigit() and abs(int(s)) > 1000:
        return int(s) / 1e7
    return float(s)
