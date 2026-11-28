"""외부 감시용 일회성 건강 확인(10 6장). 5분 주기는 외부 모니터가 담당한다."""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(url: str, *, timeout: float = 10) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("UPTIME_URL must be an HTTPS health endpoint")
    if parsed.path != "/api/health" or parsed.query or parsed.fragment:
        raise ValueError("UPTIME_URL must end with /api/health without secrets")
    try:
        request = Request(url, headers={"User-Agent": "seelo-health/1.0"})
        with build_opener(NoRedirect).open(request, timeout=timeout) as response:
            if response.status != 200:
                return False
            body = json.loads(response.read(4096))
        return body == {"status": "ok", "db": "ok"}
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="외부에서 seelo 건강 상태를 확인한다")
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    try:
        healthy = check(args.url)
    except ValueError:
        print("health=invalid_config", file=sys.stderr)
        return 2
    print("health=ok" if healthy else "health=failed")
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
