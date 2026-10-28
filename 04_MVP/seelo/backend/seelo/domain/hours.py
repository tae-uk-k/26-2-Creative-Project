"""영업시간 형식(08 0.2, 14 2.4). IO 없음.

WeeklyHours = {"days": {요일: None | [] | [{"open","close"}]},
               "breaks": {요일: [{"start","end"}]}, "notes": str|None}
- None = 정보 없음, [] = 쉬는 날. close가 open보다 이르면 다음 날 새벽까지.
"""

import re
from typing import Any

from seelo.schemas.llm import WeeklyHoursOut

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_KO = {"mon": "월", "tue": "화", "wed": "수", "thu": "목", "fri": "금", "sat": "토", "sun": "일"}
_GOOGLE_DAY = {0: "sun", 1: "mon", 2: "tue", 3: "wed", 4: "thu", 5: "fri", 6: "sat"}
_HHMM = re.compile(r"^\d{1,2}:\d{2}$")

WeeklyHours = dict[str, Any]


def empty_hours() -> WeeklyHours:
    return {"days": dict.fromkeys(DAYS), "breaks": {}, "notes": None}


def _hhmm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def from_google_periods(periods: list[dict[str, Any]] | None) -> WeeklyHours:
    """Google regularOpeningHours.periods → WeeklyHours. 나오지 않은 요일은 None(정보 없음)."""
    w = empty_hours()
    for p in periods or []:
        o = p.get("open") or {}
        day = _GOOGLE_DAY.get(o.get("day"))
        if day is None:
            continue
        c = p.get("close")
        if c is None:  # 24시간 영업
            interval = {"open": "00:00", "close": "24:00"}
        else:
            interval = {
                "open": _hhmm(o.get("hour", 0), o.get("minute", 0)),
                "close": _hhmm(c.get("hour", 0), c.get("minute", 0)),
            }
        w["days"][day] = (w["days"][day] or []) + [interval]
    for day in DAYS:
        if w["days"][day]:
            w["days"][day].sort(key=lambda i: i["open"])
    return w


def to_weekly_hours(out: WeeklyHoursOut | None) -> WeeklyHours | None:
    """LLM 출력 → WeeklyHours.

    넣지 않은 요일은 None, closed면 [], 시각 형식이 틀리면 그 요일 None(추측 금지).
    """
    if out is None:
        return None
    w = empty_hours()
    w["notes"] = out.notes
    for d in out.days:
        if d.closed:
            w["days"][d.day] = []
            continue
        times = [(i.open, i.close) for i in d.intervals] + [(b.open, b.close) for b in d.breaks]
        if not all(_HHMM.match(a) and _HHMM.match(b) for a, b in times):
            w["days"][d.day] = None
            continue
        w["days"][d.day] = sorted(
            ({"open": i.open, "close": i.close} for i in d.intervals), key=lambda x: x["open"]
        )
        if d.breaks:
            w["breaks"][d.day] = [{"start": b.open, "end": b.close} for b in d.breaks]
    return w


def _minutes(v: str) -> int:
    h, m = v.split(":")
    return int(h) * 60 + int(m)


def hours_diff(a: WeeklyHours, b: WeeklyHours) -> list[str]:
    """두 쪽 모두 정보가 있는 요일만 비교해 다른 요일 목록."""
    out = []
    for day in DAYS:
        x, y = a["days"].get(day), b["days"].get(day)
        if x is None or y is None:
            continue
        nx = sorted((_minutes(i["open"]), _minutes(i["close"])) for i in x)
        ny = sorted((_minutes(i["open"]), _minutes(i["close"])) for i in y)
        if nx != ny:
            out.append(day)
    return out


def format_hours_ko(w: WeeklyHours) -> str:
    """예: 월 11:00~21:00 / 화 휴무. 정보 없는 요일은 뺀다."""
    parts = []
    for day in DAYS:
        v = w["days"].get(day)
        if v is None:
            continue
        text = "휴무" if v == [] else ", ".join(f"{i['open']}~{i['close']}" for i in v)
        parts.append(f"{DAY_KO[day]} {text}")
    return " / ".join(parts)


# --- Google Business Profile regularHours(09 9.1) ------------------------------------------------

_GBP_DAY = {
    "mon": "MONDAY",
    "tue": "TUESDAY",
    "wed": "WEDNESDAY",
    "thu": "THURSDAY",
    "fri": "FRIDAY",
    "sat": "SATURDAY",
    "sun": "SUNDAY",
}
_GBP_DAY_KEY = {v: k for k, v in _GBP_DAY.items()}


def open_minutes(w: WeeklyHours, day: str) -> list[tuple[int, int]] | None:
    """그 요일에 실제로 여는 구간(분, 쉬는 시간을 뺌). 다음 날 새벽까지면 close에 24시간을 더한다.

    None = 정보 없음, [] = 쉬는 날. 같은 영업시간을 다른 모양(쉬는 시간 vs 구간 나눔)으로 적어도 같게 나온다.
    """
    v = (w.get("days") or {}).get(day)
    if v is None:
        return None
    spans: list[tuple[int, int]] = []
    for i in v:
        a, b = _minutes(i["open"]), _minutes(i["close"])
        spans.append((a, b + 1440 if b <= a else b))
    for br in (w.get("breaks") or {}).get(day) or []:
        bs, be = _minutes(br["start"]), _minutes(br["end"])
        cut: list[tuple[int, int]] = []
        for a, b in spans:
            if be <= a or bs >= b:
                cut.append((a, b))
                continue
            if a < bs:
                cut.append((a, bs))
            if be < b:
                cut.append((be, b))
        spans = cut
    return sorted(spans)


def _time(m: int) -> dict[str, int]:
    return {"hours": m // 60, "minutes": m % 60}


def to_gbp_hours(w: WeeklyHours) -> dict[str, Any]:
    """WeeklyHours → Location.regularHours. 쉬는 날은 기간 없음.

    정보 없는 요일이 있으면 ValueError(보내면 그 요일이 쉬는 날로 바뀌므로).
    """
    periods = []
    for i, day in enumerate(DAYS):
        spans = open_minutes(w, day)
        if spans is None:
            raise ValueError(f"no hours for {day}")
        for a, b in spans:
            close_day = DAYS[(i + 1) % 7] if b > 1440 else day
            periods.append(
                {
                    "openDay": _GBP_DAY[day],
                    "openTime": _time(a),
                    "closeDay": _GBP_DAY[close_day],
                    "closeTime": _time(b - 1440 if b > 1440 else b),
                }
            )
    return {"periods": periods}


def from_gbp_hours(d: dict[str, Any] | None) -> WeeklyHours | None:
    """Location.regularHours → WeeklyHours. regularHours가 없으면 None, 기간이 없는 요일은 쉬는 날."""
    if not d:
        return None
    w = empty_hours()
    w["days"] = {day: [] for day in DAYS}
    for p in d.get("periods") or []:
        day = _GBP_DAY_KEY.get(p.get("openDay", ""))
        if day is None:
            continue
        o, c = p.get("openTime") or {}, p.get("closeTime") or {}
        w["days"][day].append(
            {
                "open": _hhmm(o.get("hours", 0), o.get("minutes", 0)),
                "close": _hhmm(c.get("hours", 0), c.get("minutes", 0)),
            }
        )
    for day in DAYS:
        w["days"][day].sort(key=lambda i: i["open"])
    return w
