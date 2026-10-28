"""Google Business Profile API(09 9.1, GOOGLE_FIX_MODE=api). MapAdmin과 같은 인터페이스.

- 토큰: GBP_OAUTH_* 갱신 토큰으로 google-auth Credentials를 갱신한다(동기 호출이라 to_thread).
  만료 5분 전이면 다시 갱신한다.
- 칸 → Location 필드: description → profile.description, regular_hours → regularHours,
  website → websiteUri, phone → phoneNumbers.primaryPhone.
  편의 정보·메뉴는 [확인 필요, D-14] → FieldWriteFailed.
- 위치 단위 호출의 403·404 → StoreNotVisible(권한 회수, E18). 429·5xx·연결 오류 → TransientAutomationError.
  쓰기의 400(값을 받지 않음) → FieldWriteFailed("rejected"). 401·그 밖 → AutomationBlocked("api_error").
- 쓰기는 updateMask에 그 칸 하나만 넣는다(승인한 칸만 바뀜).
  GBP_VALIDATE_ONLY면 validateOnly=true(바꾸지 않고 검증만).
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog

from seelo.config import get_settings
from seelo.domain.hours import from_gbp_hours, to_gbp_hours
from seelo.domain.normalize import same_name
from seelo.integrations.browser import ReadValue, StoreRef
from seelo.integrations.browser.guards import (
    AttentionNeeded,
    AutomationBlocked,
    FieldWriteFailed,
    StoreNotVisible,
    TransientAutomationError,
)
from seelo.integrations.http import make_client

log = structlog.get_logger()

SCOPE = "https://www.googleapis.com/auth/business.manage"
TOKEN_URI = "https://oauth2.googleapis.com/token"
ACCOUNTS = "https://mybusinessaccountmanagement.googleapis.com/v1"
INFO = "https://mybusinessbusinessinformation.googleapis.com/v1"
VERIFY = "https://mybusinessverifications.googleapis.com/v1"
TIMEOUT_S = 20.0
TOKEN_MARGIN = timedelta(minutes=5)
READ_MASK = "name,title,phoneNumbers,websiteUri,regularHours,profile,metadata"
FIELD_MASK = {
    "description": "profile.description",
    "regular_hours": "regularHours",
    "website": "websiteUri",
    "phone": "phoneNumbers.primaryPhone",
}
VOM_REASON = {  # VoiceOfMerchantState 조치 → attention_reason(09 5장)
    "verify": "verification_required",
    "waitForVoiceOfMerchant": "under_review",
    "resolveOwnershipConflict": "duplicate_profile",
    "complyWithGuidelines": "guideline_violation",
}


def _fresh(creds: Any) -> bool:
    """만료 5분 전까지만 그대로 쓴다(google-auth의 expiry는 시간대 없는 UTC)."""
    if creds is None or not creds.token or creds.expiry is None:
        return False
    return bool(creds.expiry - datetime.now(UTC).replace(tzinfo=None) > TOKEN_MARGIN)


def _body(field: str, value: Any) -> dict[str, Any]:
    if field == "description":
        return {"profile": {"description": value}}
    if field == "regular_hours":
        try:
            return {"regularHours": to_gbp_hours(value)}
        except (ValueError, KeyError, TypeError) as e:
            raise FieldWriteFailed("hours_incomplete") from e
    if field == "website":
        return {"websiteUri": value}
    return {"phoneNumbers": {"primaryPhone": value}}


def _value(loc: dict[str, Any], field: str) -> Any:
    if field == "description":
        return (loc.get("profile") or {}).get("description")
    if field == "regular_hours":
        return from_gbp_hours(loc.get("regularHours"))
    if field == "website":
        return loc.get("websiteUri")
    return (loc.get("phoneNumbers") or {}).get("primaryPhone")


class GoogleAdminApi:
    def __init__(self, http: httpx.AsyncClient, *, token: Any = None) -> None:
        """token: 테스트용 고정 토큰(문자열). 없으면 GBP_OAUTH_* 로 갱신한다."""
        self._http = http
        self._fixed_token: str | None = token
        self._creds: Any = None
        self._location: str | None = None

    async def _token(self) -> str:
        if self._fixed_token:
            return self._fixed_token
        if _fresh(self._creds):
            return str(self._creds.token)
        import google.auth.transport.requests
        from google.oauth2.credentials import Credentials

        s = get_settings()
        if not (s.gbp_oauth_client_id and s.gbp_oauth_refresh_token.get_secret_value()):
            raise AutomationBlocked("api_not_configured")
        creds = Credentials(
            None,
            refresh_token=s.gbp_oauth_refresh_token.get_secret_value(),
            client_id=s.gbp_oauth_client_id,
            client_secret=s.gbp_oauth_client_secret.get_secret_value(),
            token_uri=TOKEN_URI,
            scopes=[SCOPE],
        )
        try:
            await asyncio.to_thread(creds.refresh, google.auth.transport.requests.Request())
        except Exception as e:  # 갱신 토큰이 막힘·네트워크: 관리자가 확인해야 함
            log.error("gbp_token_refresh_failed", error=type(e).__name__)
            raise AutomationBlocked("api_auth") from e
        self._creds = creds
        return str(creds.token)

    async def _call(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        location: bool = False,
        write: bool = False,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {await self._token()}"}
        try:
            r = await self._http.request(method, url, params=params, json=json, headers=headers)
        except httpx.HTTPError as e:
            raise TransientAutomationError(type(e).__name__) from e
        st = r.status_code
        if st < 300:
            return r.json() if r.content else {}
        log.info("gbp_api_error", method=method, status=st, location=location)
        if location and st in (403, 404):
            raise StoreNotVisible()
        if st == 429 or st >= 500:
            raise TransientAutomationError(f"http_{st}")
        if write and st == 400:
            raise FieldWriteFailed("rejected")
        raise AutomationBlocked("api_auth" if st == 401 else "api_error")

    async def _pages(self, url: str, key: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            q = dict(params or {}) | ({"pageToken": token} if token else {})
            data = await self._call("GET", url, params=q)
            out += data.get(key) or []
            token = data.get("nextPageToken")
            if not token:
                return out

    async def _find_location(self, store: StoreRef) -> str | None:
        """계정마다 이 가게 초대를 수락하고(9.1), 위치 목록에서 metadata.placeId로 찾는다."""
        threshold = get_settings().name_similarity_threshold
        for acc in await self._pages(f"{ACCOUNTS}/accounts", "accounts"):
            for inv in await self._pages(f"{ACCOUNTS}/{acc['name']}/invitations", "invitations"):
                tl = inv.get("targetLocation") or {}
                pid = tl.get("placeId")
                if (pid and pid == store.google_place_id) or (
                    not pid and same_name(tl.get("locationName") or "", store.name, threshold)
                ):
                    await self._call("POST", f"{ACCOUNTS}/{inv['name']}:accept", json={})
                    log.info("gbp_invitation_accepted", store_id=store.store_id)
            locations = await self._pages(
                f"{INFO}/{acc['name']}/locations",
                "locations",
                {"readMask": "name,title,metadata", "pageSize": "100"},
            )
            for loc in locations:
                place_id = (loc.get("metadata") or {}).get("placeId")
                if store.google_place_id and place_id == store.google_place_id:
                    return str(loc["name"])
        return None

    # --- MapAdmin ---
    async def open_store(self, store: StoreRef, external_ref: str | None) -> str:
        name = external_ref or await self._find_location(store)
        if not name:
            raise StoreNotVisible()
        await self._call("GET", f"{INFO}/{name}", params={"readMask": "name,metadata"}, location=True)
        vom = await self._call("GET", f"{VERIFY}/{name}/VoiceOfMerchantState", location=True)
        if not vom.get("hasVoiceOfMerchant"):
            raise AttentionNeeded(next((r for k, r in VOM_REASON.items() if k in vom), "other"))
        self._location = name
        return name

    async def read_fields(self, fields: list[str]) -> dict[str, ReadValue]:
        if self._location is None:
            raise RuntimeError("open_store first")
        loc = await self._call(
            "GET", f"{INFO}/{self._location}", params={"readMask": READ_MASK}, location=True
        )
        pending = bool((loc.get("metadata") or {}).get("hasPendingEdits"))
        return {f: ReadValue(_value(loc, f), pending) for f in fields if f in FIELD_MASK}

    async def write_field(self, field_: str, value: object) -> None:
        if self._location is None:
            raise RuntimeError("open_store first")
        if field_ not in FIELD_MASK:
            raise FieldWriteFailed("unsupported_field")
        params = {"updateMask": FIELD_MASK[field_]}
        if get_settings().gbp_validate_only:
            params["validateOnly"] = "true"
        await self._call(
            "PATCH",
            f"{INFO}/{self._location}",
            params=params,
            json=_body(field_, value),
            location=True,
            write=True,
        )


def api_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return make_client(TIMEOUT_S, transport=transport)
