"""업타임 확인의 HTTPS·리디렉션·실패 판정(10 6장)."""

from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from scripts import check_uptime


class Response(BytesIO):
    status = 200


@pytest.mark.parametrize(
    "body,expected",
    [
        (b'{"status":"ok","db":"ok"}', True),
        (b'{"status":"ok","db":"failed"}', False),
        (b"<html>login</html>", False),
    ],
)
def test_health_payload(body, expected, monkeypatch):
    class Opener:
        def open(self, req, timeout):
            assert req.full_url == "https://localhost/api/health" and timeout == 10
            return Response(body)

    monkeypatch.setattr(check_uptime, "build_opener", lambda handler: Opener())
    assert check_uptime.check("https://localhost/api/health") is expected


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/api/health",
        "https://a:b@localhost/api/health",
        "https://localhost/api/health?token=x",
        "https://localhost/login",
    ],
)
def test_invalid_config(url):
    with pytest.raises(ValueError):
        check_uptime.check(url)


@pytest.mark.parametrize(
    "error", [URLError("offline"), HTTPError("https://localhost", 302, "redirect", {}, None)]
)
def test_external_failure(error, monkeypatch):
    class Opener:
        def open(self, req, timeout):
            raise error

    monkeypatch.setattr(check_uptime, "build_opener", lambda handler: Opener())
    assert check_uptime.check("https://localhost/api/health") is False


def test_no_redirect_handler():
    assert (
        check_uptime.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other") is None
    )
