"""배포된 화면·API 프록시·쿠키를 외부에서 확인한다. 운영 CI와 로컬 Docker 검증에 같은 검사를 쓴다.

예: python3 check-web.py --host https://seelo.site --commit <sha> --secure-cookie
    python check-web.py --host http://127.0.0.1:18080
"""

import argparse
import json
import re
import urllib.error
import urllib.request


def fetch(host: str, path: str) -> tuple[int, str, dict[str, list[str]]]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(host + path, timeout=15) as response:
            headers: dict[str, list[str]] = {}
            for key, value in response.headers.items():
                headers.setdefault(key.lower(), []).append(value)
            return response.status, response.read().decode("utf-8", "replace"), headers
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace"), {}


def check(host: str, commit: str | None, secure_cookie: bool) -> list[str]:
    host = host.rstrip("/")
    done = []
    status, index, headers = fetch(host, "/")
    assert status == 200 and '<div id="root"></div>' in index, "frontend_index_missing"
    assert "no-cache" in " ".join(headers.get("cache-control", [])), "index_cache_policy"
    done.append("첫 화면 index.html·캐시 정책")
    deep_paths = (
        "/stores",
        "/stores/1/products?page=2",
        "/stores/1/products/2?plan=3",
        "/operator",
        "/login?returnTo=%2Fstores",
    )
    for path in deep_paths:
        status, body, _ = fetch(host, path)
        # 직접 접근·새로고침도 같은 React 진입 파일을 받아야 한다.
        assert status == 200 and body == index, f"spa_fallback_failed:{path}"
    done.append("직접 경로 접근·새로고침")
    script = re.search(r'src="(/assets/[^"]+\.js)"', index)
    assert script, "asset_reference_missing"
    status, _, asset = fetch(host, script.group(1))
    assert status == 200 and "javascript" in " ".join(asset.get("content-type", [])), "asset_type"
    assert "max-age=31536000" in " ".join(asset.get("cache-control", [])), "asset_cache_policy"
    status, body, _ = fetch(host, "/assets/missing-file.js")
    assert status == 404 and '<div id="root">' not in body, "missing_asset_must_not_fallback"
    done.append("해시 정적 파일·없는 파일 404")
    status, body, _ = fetch(host, "/api/health")
    assert status == 200 and json.loads(body) == {"status": "ok", "db": "ok"}, "api_proxy_health"
    status, body, _ = fetch(host, "/api/auth/me")
    assert status == 401 and json.loads(body)["error"]["code"] == "AUTH_REQUIRED", "api_proxy_json_error"
    done.append("API 프록시·JSON 오류")
    status, _, headers = fetch(host, "/api/auth/csrf")
    cookies = [c for c in headers.get("set-cookie", []) if c.startswith("seelo_csrf=")]
    assert status == 204 and cookies, "csrf_cookie_missing"
    attrs = cookies[0].lower()
    assert "samesite=lax" in attrs and "path=/" in attrs and "httponly" not in attrs, "csrf_cookie_policy"
    assert ("secure" in attrs) == secure_cookie, "csrf_cookie_secure_flag"
    done.append("CSRF 쿠키 SameSite·Path·Secure")
    if commit:
        status, body, _ = fetch(host, "/deployment.json")
        assert status == 200 and json.loads(body)["commit"] == commit, "deployment_commit"
        done.append("배포 커밋")
    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--commit")
    parser.add_argument("--secure-cookie", action="store_true")
    args = parser.parse_args()
    for item in check(args.host, args.commit, args.secure_cookie):
        print("확인:", item)


if __name__ == "__main__":
    main()
