"""배포 뒤 읽기 전용 선행 확인(10 6장, W-11-2).

실제 정상 흐름·공급자 중단·연속 시연은 infra/OPERATIONS.md 절차로 별도 기록한다.
이 시험만으로 W-11-2를 완료로 판정하지 않는다.
"""

import os
from urllib.parse import urlsplit

import httpx
import pytest

pytestmark = pytest.mark.live


async def test_deploy_https_health_and_hidden_docs():
    base = os.environ.get("SEELO_DEPLOY_BASE_URL", "").rstrip("/")
    if not base:
        pytest.skip("배포 VM·도메인 결정 후 SEELO_DEPLOY_BASE_URL 필요")
    parsed = urlsplit(base)
    assert parsed.scheme == "https" and not parsed.username and not parsed.password and not parsed.query
    async with httpx.AsyncClient(base_url=base, timeout=10, follow_redirects=False) as client:
        response = await client.get("/api/health")
        assert response.status_code == 200 and response.json() == {"status": "ok", "db": "ok"}
        assert response.headers["strict-transport-security"].startswith("max-age=")
        assert response.headers["referrer-policy"] == "no-referrer"
        assert (await client.get("/api/openapi.json")).status_code == 404
        assert (await client.get("/api/docs")).status_code == 404
