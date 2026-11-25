"""담당자 세션 이전 도구. 쿠키 값을 출력하지 않고 플랫폼 도메인만 옮기는지 확인한다."""

import importlib.util
import json
from pathlib import Path

import pytest

from seelo.config import get_settings
from seelo.security.crypto import decrypt_json, encrypt_json

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "commerce_browser_session.py"


def tool():
    spec = importlib.util.spec_from_file_location("commerce_browser_session", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_import_moves_only_platform_cookies_without_printing_values(tmp_path, monkeypatch, capsys):
    session = tool()
    pc, server = tmp_path / "pc", tmp_path / "server"
    monkeypatch.setattr(get_settings(), "commerce_browser_profile_root", str(pc))
    profile = pc / "cafe24" / "demo01" / "1"
    profile.mkdir(parents=True)
    cookies = [
        {"name": "ECSESSID", "value": "secret-cafe24", "domain": ".demo01.cafe24.com", "expires": 2000000000},
        {"name": "other", "value": "secret-other", "domain": ".example.com", "expires": -1},
    ]
    (profile / ".seelo-session.enc").write_bytes(encrypt_json({"cookies": cookies}))
    exported = tmp_path / "transfer.json"
    session.main(["export", "--platform", "cafe24", "--external-id", "demo01", "--file", str(exported)])
    output = capsys.readouterr().out
    assert "secret-" not in output and json.loads(output)["cookies"] == 1
    assert [c["name"] for c in json.loads(exported.read_text(encoding="utf-8"))["cookies"]] == ["ECSESSID"]
    with pytest.raises(FileExistsError):
        session.main(["export", "--platform", "cafe24", "--external-id", "demo01", "--file", str(exported)])
    monkeypatch.setattr(get_settings(), "commerce_browser_profile_root", str(server))
    with pytest.raises(SystemExit):
        session.main(["import", "--platform", "cafe24", "--external-id", "demo02", "--file", str(exported)])
    session.main(["import", "--platform", "cafe24", "--external-id", "demo01", "--file", str(exported)])
    output = capsys.readouterr().out
    assert "secret-" not in output and not exported.exists()
    stored = decrypt_json((server / "cafe24" / "demo01" / "1" / ".seelo-session.enc").read_bytes())
    assert [c["value"] for c in stored["cookies"]] == ["secret-cafe24"]
    session.main(["status", "--platform", "cafe24", "--external-id", "demo01"])
    status = json.loads(capsys.readouterr().out)
    assert status["session"] is True and status["domains"] == ["demo01.cafe24.com"]
    session.main(["forget", "--platform", "cafe24", "--external-id", "demo01"])
    assert not (server / "cafe24" / "demo01" / "1").exists()
