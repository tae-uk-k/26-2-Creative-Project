"""같은 가게 판정·후보 정리(07 3.2~3.4, 14 2.3). IO 없음."""

import hashlib

from seelo.domain.geo import haversine_m
from seelo.domain.normalize import name_similarity, normalize_address, normalize_name
from seelo.integrations import Place

MAX_CANDIDATES = 5


def distance_m(a: Place | tuple[float, float], b: Place) -> float | None:
    lat, lng = (a.lat, a.lng) if isinstance(a, Place) else a
    if lat is None or lng is None or b.lat is None or b.lng is None:
        return None
    return haversine_m(lat, lng, b.lat, b.lng)


def best_similarity(place: Place, names: list[str]) -> int:
    return max((name_similarity(place.name, n) for n in names if n), default=0)


def pick_same_place(
    ref: Place, results: list[Place], *, names: list[str], threshold: int, max_distance_m: float = 100.0
) -> Place | None:
    """기준에서 max_distance_m 안이고 이름이 같은 결과 하나. 여러 개면 유사도 높은 것, 같으면 가까운 것."""
    scored: list[tuple[int, float, Place]] = []
    for p in results:
        d = distance_m(ref, p)
        if d is None or d > max_distance_m:
            continue
        sim = best_similarity(p, names)
        if sim >= threshold:
            scored.append((sim, d, p))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][2]


def evidence_matches(
    name: str | None, address: str | None, *, names: list[str], our_address: str | None, threshold: int
) -> bool:
    """AI 웹 검색 사이트 거르기(07 6.4): 이름이 같거나 정규화 주소가 같으면 남긴다. 둘 다 없으면 버린다."""
    if name and any(name_similarity(name, n) >= threshold for n in names if n):
        return True
    ours, theirs = normalize_address(our_address), normalize_address(address)
    return ours is not None and ours == theirs


def same_name_results(results: list[Place], names: list[str], threshold: int) -> list[Place]:
    """이름이 같은 결과(유사도 높은 순, 최대 5개)."""
    scored = [(best_similarity(p, names), i, p) for i, p in enumerate(results)]
    hits = [x for x in scored if x[0] >= threshold]
    hits.sort(key=lambda x: (-x[0], x[1]))
    return [p for _, _, p in hits[:MAX_CANDIDATES]]


def within(results: list[Place], center: tuple[float, float], max_m: float) -> list[Place]:
    out = []
    for p in results:
        d = distance_m(center, p)
        if d is not None and d <= max_m:
            out.append(p)
    return out


def naver_fingerprint(p: Place) -> str:
    """네이버는 장소 번호를 주지 않으므로 이름+도로명 주소로 후보를 다시 찾는다(07 3.4)."""
    road = p.raw.get("roadAddress") or p.address or ""
    return hashlib.sha256(f"{normalize_name(p.name)}|{road}".encode()).hexdigest()
