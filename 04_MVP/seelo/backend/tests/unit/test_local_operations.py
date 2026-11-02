"""실제 송신 없이 외부 감시·백업 경계와 CLI 인증 비교값을 검증한다."""

import hashlib
import json
import subprocess
from types import SimpleNamespace

import httpx
import pytest

from seelo.local_ai import operations
from seelo.services.kakao_unlink import authorized


@pytest.mark.parametrize(
    "status,body,ok",
    [
        (200, {"status": "ok", "db": "ok"}, True),
        (302, {"status": "ok", "db": "ok"}, False),
        (200, {"status": "ok", "db": "failed"}, False),
        (500, {"status": "ok", "db": "ok"}, False),
    ],
)
def test_health_requires_exact_https_result(monkeypatch, status, body, ok):
    def get(url, **kwargs):
        assert url == "https://seelo.site/api/health"
        assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
        return httpx.Response(status, json=body)

    monkeypatch.setattr(httpx, "get", get)
    assert operations.check_health()["ok"] is ok


def test_connection_error_is_safe(monkeypatch):
    def broken(*args, **kwargs):
        raise httpx.ConnectError("secret transport detail")

    monkeypatch.setattr(httpx, "get", broken)
    assert operations.check_health() == {"ok": False, "reason": "external_connection_failed"}


@pytest.mark.parametrize(
    "manifest",
    [
        [],
        {"backups": None},
        {"backups": [None]},
        {"backups": [{"name": "../outside.dump", "sha256": "a" * 64}]},
        {"backups": [{"name": "seelo_20261031T000000Z.dump", "sha256": "bad"}]},
    ],
)
def test_bad_manifest_never_downloads(tmp_path, monkeypatch, manifest):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps(manifest))

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ValueError, match="invalid_backup_manifest"):
        operations.sync_backups(tmp_path)
    assert len(calls) == 1  # 원격 목록 조회만, scp 실행 없음


def test_existing_backup_is_verified_without_overwrite(tmp_path, monkeypatch):
    folder = tmp_path / "backups"
    folder.mkdir()
    target = folder / "seelo_20261031T000000Z.dump"
    target.write_bytes(b"preserved backup")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = {"backups": [{"name": target.name, "sha256": digest}]}
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps(manifest))

    monkeypatch.setattr(subprocess, "run", run)
    assert operations.sync_backups(tmp_path) == manifest["backups"]
    assert len(calls) == 1 and target.read_bytes() == b"preserved backup"
    manifest["backups"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="existing_backup_hash_mismatch"):
        operations.sync_backups(tmp_path)
    assert target.read_bytes() == b"preserved backup"


def test_health_events_only_on_change_and_backup_error_recorded(tmp_path, monkeypatch):
    env = tmp_path / "bridge.env"
    env.write_text('LOCAL_AI_DATA_DIR="' + tmp_path.as_posix() + '"\n', encoding="utf-8")
    monkeypatch.setattr(operations, "check_health", lambda: {"ok": True, "reason": "ok"})
    monkeypatch.setattr(operations, "sync_backups", lambda _: [])
    operations.run_once(env)
    operations.run_once(env)
    assert len((tmp_path / "health-events.jsonl").read_text().splitlines()) == 1

    def broken(_):
        raise RuntimeError("credential detail")

    monkeypatch.setattr(operations, "sync_backups", broken)
    result = operations.run_once(env, force_backup=True)
    assert result["backup_error"] == "RuntimeError" and not result["notifications_enabled"]
    assert "credential detail" not in (tmp_path / "operations-status.json").read_text()


def test_admin_auth_requires_scheme_and_digest():
    digest = hashlib.sha256(b"correct-key").hexdigest()
    assert authorized("KakaoAK correct-key", digest)
    for header in ("Bearer correct-key", "KakaoAK wrong", "KakaoAK correct-key ", "KakaoAK", ""):
        assert not authorized(header, digest)
    assert not authorized("KakaoAK correct-key", "")
