"""담당자 브라우저 세션(몰별 전용 프로필)의 상태 확인·이전·삭제.

서버의 worker-fix 컨테이너에는 화면이 없어 직접 로그인할 수 없다. 담당자는 PC에서
`commerce_browser_login.py`로 로그인한 뒤 이 도구로 세션 쿠키를 옮긴다.

- status: 세션 파일 유무·쿠키 수·도메인·만료 시각만 보여 준다. 쿠키 값은 출력하지 않는다.
- export: PC 프로필의 세션을 평문 JSON 파일(권한 600)로 내보낸다. 화면에는 값을 쓰지 않는다.
- import: 내보낸 파일을 현재 서버 키로 다시 암호화해 넣고 평문 파일을 지운다.
- forget: 몰 프로필을 지운다.

플랫폼 도메인(cafe24.com·naver.com) 쿠키만 다룬다. 일반 Chrome 프로필·비밀번호는 읽지 않는다.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seelo.config import get_settings  # noqa: E402
from seelo.integrations.browser.commerce import BrowserProduct  # noqa: E402
from seelo.security.crypto import decrypt_json, encrypt_json  # noqa: E402

DOMAINS = {"cafe24": ("cafe24.com",), "smartstore": ("naver.com",)}
STATE = ".seelo-session.enc"


def allowed(platform: str, cookie: dict) -> bool:
    domain = str(cookie.get("domain", "")).lstrip(".").lower()
    return any(domain == base or domain.endswith("." + base) for base in DOMAINS[platform])


def clean(platform: str, cookies: object) -> list[dict]:
    if not isinstance(cookies, list):
        raise SystemExit("cookies 목록이 아닙니다.")
    result = []
    for cookie in cookies:
        if not isinstance(cookie, dict) or not cookie.get("name") or "value" not in cookie:
            raise SystemExit("쿠키 형식이 올바르지 않습니다.")
        if allowed(platform, cookie):
            result.append(cookie)
    return result


def summary(platform: str, cookies: list[dict]) -> dict:
    expiries = [
        c["expires"] for c in cookies if isinstance(c.get("expires"), int | float) and c["expires"] > 0
    ]

    def stamp(value: float | None) -> str | None:
        return datetime.fromtimestamp(value, UTC).isoformat() if value else None

    return {
        "platform": platform,
        "cookies": len(cookies),
        "domains": sorted({str(c.get("domain", "")).lstrip(".") for c in cookies}),
        "earliestExpiry": stamp(min(expiries) if expiries else None),
        "latestExpiry": stamp(max(expiries) if expiries else None),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=["status", "export", "import", "forget"])
    parser.add_argument("--platform", choices=sorted(DOMAINS), required=True)
    parser.add_argument("--external-id", required=True)
    parser.add_argument("--shop-no", type=int, default=1)
    parser.add_argument("--file", type=Path, help="export 대상 또는 import 원본 파일")
    args = parser.parse_args(argv)
    # BrowserProduct가 몰 ID 형식을 검사하고 몰별 프로필 경로를 정한다.
    profile = Path(BrowserProduct(args.platform, args.external_id, args.shop_no).profile)
    state = profile / STATE
    if args.command == "status":
        cookies = decrypt_json(state.read_bytes()).get("cookies", []) if state.exists() else []
        print(
            json.dumps(
                {"profile": str(profile), "session": state.exists(), **summary(args.platform, cookies)}
            )
        )
        return
    if args.command == "forget":
        root = Path(get_settings().commerce_browser_profile_root).resolve()
        if profile.exists() and profile.resolve().is_relative_to(root):
            shutil.rmtree(profile)
        print(json.dumps({"profile": str(profile), "removed": not profile.exists()}))
        return
    if args.file is None:
        raise SystemExit("--file이 필요합니다.")
    if args.command == "export":
        if not state.exists():
            raise SystemExit("내보낼 세션이 없습니다. 먼저 commerce_browser_login.py로 로그인해 주세요.")
        cookies = clean(args.platform, decrypt_json(state.read_bytes()).get("cookies", []))
        # 이미 있는 파일을 덮어쓰지 않는다. 권한 600으로 만들고 값은 화면에 쓰지 않는다.
        fd = os.open(args.file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"platform": args.platform, "externalId": args.external_id, "cookies": cookies}, stream)
        print(json.dumps({"exported": str(args.file), **summary(args.platform, cookies)}))
        return
    data = json.loads(args.file.read_text(encoding="utf-8"))
    if data.get("platform") != args.platform or data.get("externalId") != args.external_id:
        raise SystemExit("다른 몰의 세션 파일입니다.")
    cookies = clean(args.platform, data.get("cookies"))
    if not cookies:
        raise SystemExit("이 플랫폼 도메인의 쿠키가 없습니다.")
    profile.mkdir(parents=True, exist_ok=True)
    pending = state.with_suffix(".tmp")
    pending.write_bytes(encrypt_json({"cookies": cookies}))
    pending.replace(state)
    args.file.unlink()
    print(
        json.dumps(
            {"imported": True, "plaintextRemoved": not args.file.exists(), **summary(args.platform, cookies)}
        )
    )


if __name__ == "__main__":
    main()
