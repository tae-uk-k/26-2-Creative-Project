"""Google Business Profile API 모드(09 9.1)와 영업시간 변환(to_gbp_hours·from_gbp_hours).

httpx.MockTransport로 응답을 흉내 낸다(실제 호출 없음). updateMask에는 승인한 칸 하나만 들어간다.
"""

import dataclasses
import json
from typing import Any

import httpx
import pytest

from seelo.domain.field_dictionary import same_value
from seelo.domain.hours import from_gbp_hours, to_gbp_hours
from seelo.integrations.browser import StoreRef
from seelo.integrations.browser.guards import (
    AttentionNeeded,
    AutomationBlocked,
    FieldWriteFailed,
    StoreNotVisible,
    TransientAutomationError,
)
from seelo.integrations.gbp_api import ACCOUNTS, INFO, VERIFY, GoogleAdminApi, api_client

REF = StoreRef(store_id=1, name="명동교자", address=None, google_place_id="PLACE1", kakao_place_id=None)


def _week(**days: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        d: [{"open": "11:00", "close": "21:00"}] for d in ("mon", "tue", "wed", "thu", "fri", "sat")
    }
    base["sun"] = []
    return {"days": base | days, "breaks": {}, "notes": None}


# --- 영업시간 변환 -----------------------------------------------------------------------------------


def test_to_gbp_hours_overnight_closed_and_breaks() -> None:
    w = _week(fri=[{"open": "18:00", "close": "02:00"}])
    w["breaks"] = {"mon": [{"start": "15:00", "end": "17:00"}]}
    periods = to_gbp_hours(w)["periods"]
    mon = [(p["openTime"], p["closeDay"], p["closeTime"]) for p in periods if p["openDay"] == "MONDAY"]
    assert mon == [
        ({"hours": 11, "minutes": 0}, "MONDAY", {"hours": 15, "minutes": 0}),
        ({"hours": 17, "minutes": 0}, "MONDAY", {"hours": 21, "minutes": 0}),
    ]  # 쉬는 시간은 구간을 나눠 보낸다
    (fri,) = [p for p in periods if p["openDay"] == "FRIDAY"]
    assert (fri["closeDay"], fri["closeTime"]) == ("SATURDAY", {"hours": 2, "minutes": 0})  # 자정 넘김
    assert not [p for p in periods if p["openDay"] == "SUNDAY"]  # 쉬는 날은 기간 없음


def test_to_gbp_hours_refuses_unknown_day() -> None:
    with pytest.raises(ValueError):
        to_gbp_hours(_week(wed=None))  # 보내면 그 요일이 쉬는 날로 바뀐다


def test_round_trip_is_same_value() -> None:
    w = _week(fri=[{"open": "18:00", "close": "02:00"}])
    w["breaks"] = {"mon": [{"start": "15:00", "end": "17:00"}]}
    back = from_gbp_hours(to_gbp_hours(w))
    assert back is not None and back["days"]["sun"] == [] and back["breaks"] == {}
    assert same_value("hours", back, w)  # 쉬는 시간을 구간 나눔으로 적어도 같은 영업시간
    assert not same_value("hours", back, _week())
    assert from_gbp_hours(None) is None
    assert from_gbp_hours(
        {"periods": [{"openDay": "MONDAY", "openTime": {}, "closeDay": "MONDAY", "closeTime": {"hours": 24}}]}
    )["days"]["mon"] == [  # type: ignore[index]
        {"open": "00:00", "close": "24:00"}
    ]


# --- API 모드 -----------------------------------------------------------------------------------


class Server:
    def __init__(self) -> None:
        self.location: dict[str, Any] = {
            "name": "locations/9",
            "title": "명동교자",
            "profile": {"description": "옛 소개"},
            "websiteUri": "https://old.example/",
            "phoneNumbers": {"primaryPhone": "02-111-2222"},
            "metadata": {"placeId": "PLACE1", "hasPendingEdits": False},
        }
        self.vom: dict[str, Any] = {"hasVoiceOfMerchant": True, "hasBusinessAuthority": True}
        self.invitations: list[dict[str, Any]] = []
        self.accepted: list[str] = []
        self.patches: list[tuple[dict[str, str], dict[str, Any]]] = []
        self.status: dict[str, int] = {}  # 경로 끝 → 상태 코드(오류 흉내)
        self.seen: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url).split("?")[0]
        self.seen.append(f"{req.method} {url}")
        assert req.headers["Authorization"] == "Bearer TOKEN"
        for suffix, st in self.status.items():
            if url.endswith(suffix) and (
                req.method == "PATCH" or suffix != "locations/9" or req.method == "GET"
            ):
                return httpx.Response(st, json={"error": {"code": st}})
        if url == f"{ACCOUNTS}/accounts":
            return httpx.Response(200, json={"accounts": [{"name": "accounts/1"}]})
        if url == f"{ACCOUNTS}/accounts/1/invitations":
            return httpx.Response(200, json={"invitations": self.invitations})
        if url.endswith(":accept"):
            self.accepted.append(url)
            return httpx.Response(200, json={})
        if url == f"{INFO}/accounts/1/locations":
            page = req.url.params.get("pageToken")
            if page is None:
                return httpx.Response(
                    200,
                    json={
                        "locations": [{"name": "locations/1", "metadata": {"placeId": "X"}}],
                        "nextPageToken": "p2",
                    },
                )
            return httpx.Response(
                200, json={"locations": [{"name": "locations/9", "metadata": {"placeId": "PLACE1"}}]}
            )
        if url == f"{VERIFY}/locations/9/VoiceOfMerchantState":
            return httpx.Response(200, json=self.vom)
        if url == f"{INFO}/locations/9":
            if req.method == "PATCH":
                self.patches.append((dict(req.url.params), json.loads(req.content)))
                return httpx.Response(200, json=self.location)
            return httpx.Response(200, json=self.location)
        return httpx.Response(404)


async def _api(server: Server) -> tuple[GoogleAdminApi, httpx.AsyncClient]:
    http = api_client(httpx.MockTransport(server))
    return GoogleAdminApi(http, token="TOKEN"), http


async def test_find_location_accept_invitation_and_read() -> None:
    srv = Server()
    srv.invitations = [
        {
            "name": "accounts/1/invitations/5",
            "targetLocation": {"locationName": "명동교자", "placeId": "PLACE1"},
        },
        {
            "name": "accounts/1/invitations/6",
            "targetLocation": {"locationName": "다른 가게", "placeId": "OTHER"},
        },
    ]
    api, http = await _api(srv)
    async with http:
        assert await api.open_store(REF, None) == "locations/9"  # 두 번째 쪽에서 placeId로 찾음
        srv.location["metadata"]["hasPendingEdits"] = True
        got = await api.read_fields(["description", "website", "phone", "regular_hours", "menu"])
    assert srv.accepted == [f"{ACCOUNTS}/accounts/1/invitations/5:accept"]  # 이 가게 초대만 수락
    assert {k: v.value for k, v in got.items()} == {
        "description": "옛 소개",
        "website": "https://old.example/",
        "phone": "02-111-2222",
        "regular_hours": None,
    }  # 메뉴는 API 미확인(D-14) → 빠짐
    assert all(v.pending_review for v in got.values())


async def test_write_sends_only_that_field() -> None:
    srv = Server()
    api, http = await _api(srv)
    async with http:
        await api.open_store(REF, "locations/9")
        await api.write_field("description", "새 소개")
        await api.write_field("regular_hours", _week())
        await api.write_field("phone", "02-776-0000")
        with pytest.raises(FieldWriteFailed) as e:
            await api.write_field("attributes", {"vegetarian": True})
        assert e.value.reason == "unsupported_field"
        with pytest.raises(FieldWriteFailed) as e:
            await api.write_field("regular_hours", _week(wed=None))
        assert e.value.reason == "hours_incomplete"
    masks = [(p["updateMask"], list(body)) for p, body in srv.patches]
    assert masks == [
        ("profile.description", ["profile"]),
        ("regularHours", ["regularHours"]),
        ("phoneNumbers.primaryPhone", ["phoneNumbers"]),
    ]
    assert srv.patches[0][1] == {"profile": {"description": "새 소개"}}
    assert all("validateOnly" not in p for p, _ in srv.patches)


async def test_validate_only_setting(settings_env: Any) -> None:
    settings_env(GBP_VALIDATE_ONLY="true")
    srv = Server()
    api, http = await _api(srv)
    async with http:
        await api.open_store(REF, "locations/9")
        await api.write_field("website", "https://new.example/")
    assert srv.patches[0][0] == {"updateMask": "websiteUri", "validateOnly": "true"}


@pytest.mark.parametrize(
    ("vom", "reason"),
    [
        ({"hasVoiceOfMerchant": False, "verify": {}}, "verification_required"),
        ({"hasVoiceOfMerchant": False, "waitForVoiceOfMerchant": {}}, "under_review"),
        ({"hasVoiceOfMerchant": False, "resolveOwnershipConflict": {}}, "duplicate_profile"),
        ({"hasVoiceOfMerchant": False, "complyWithGuidelines": {}}, "guideline_violation"),
        ({"hasVoiceOfMerchant": False}, "other"),
    ],
)
async def test_voice_of_merchant_reasons(vom: dict[str, Any], reason: str) -> None:
    srv = Server()
    srv.vom = vom
    api, http = await _api(srv)
    async with http:
        with pytest.raises(AttentionNeeded) as e:
            await api.open_store(REF, "locations/9")
    assert e.value.reason == reason


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (404, StoreNotVisible),
        (403, StoreNotVisible),
        (429, TransientAutomationError),
        (503, TransientAutomationError),
        (401, AutomationBlocked),
    ],
)
async def test_location_errors(status: int, error: type[Exception]) -> None:
    srv = Server()
    srv.status = {"locations/9": status}
    api, http = await _api(srv)
    async with http:
        with pytest.raises(error):
            await api.open_store(REF, "locations/9")


async def test_write_rejected_and_not_found() -> None:
    srv = Server()
    api, http = await _api(srv)
    async with http:
        await api.open_store(REF, "locations/9")
        srv.status = {"locations/9": 400}
        with pytest.raises(FieldWriteFailed) as e:
            await api.write_field("website", "https://new.example/")
        assert e.value.reason == "rejected"
    api, http = await _api(Server())
    async with http:
        with pytest.raises(StoreNotVisible):
            await api.open_store(dataclasses.replace(REF, google_place_id="NOPE"), None)  # 위치 목록에 없음
