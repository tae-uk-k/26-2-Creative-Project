"""17 4장 오프라인 API 계약: 실제 라우터 일치·결정적 출력·비밀 값 미포함."""

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts import export_openapi
from scripts.seed_demo import DEMO_PASSWORD
from seelo.config import Settings
from seelo.main import create_app


def test_schema_matches_all_live_routes_and_refs():
    schema = export_openapi.schema()
    assert schema == create_app(with_queue=False).openapi()
    assert (
        "/api/fix/report" in schema["paths"]
        and "/api/admin/fix-requests/{request_id}/remeasure-now" in schema["paths"]
    )
    assert "ReportContent" in schema["components"]["schemas"]

    def refs(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k == "$ref":
                    target = schema
                    for part in v.removeprefix("#/").split("/"):
                        target = target[part]
                else:
                    refs(v)
        elif isinstance(value, list):
            for v in value:
                refs(v)

    refs(schema)
    assert DEMO_PASSWORD not in json.dumps(schema)


def test_checked_in_contract_is_current():
    """API 변경 뒤 재생성 누락을 잡는다(17 4장)."""
    assert export_openapi.DEFAULT_OUTPUT.is_file()
    assert export_openapi.export(export_openapi.DEFAULT_OUTPUT, check=True)


def test_export_and_check_are_deterministic_and_non_mutating(tmp_path):
    output = tmp_path / "contract.json"
    assert export_openapi.export(output, check=True) is False and not output.exists()
    assert export_openapi.export(output)
    content = output.read_bytes()
    stamp = output.stat().st_mtime_ns
    assert export_openapi.export(output)
    assert output.stat().st_mtime_ns == stamp and output.read_bytes() == content
    assert export_openapi.main(["--output", str(output), "--check"]) == 0
    output.write_text("{}", encoding="utf-8")
    assert export_openapi.main(["--output", str(output), "--check"]) == 1
    assert output.read_text() == "{}"


def test_cli_works_without_settings_file_or_credentials(tmp_path):
    script = Path(export_openapi.__file__).resolve()
    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper() not in {name.upper() for name in Settings.model_fields}
    }
    output = tmp_path / "offline.json"
    result = subprocess.run(
        [sys.executable, str(script), "--output", str(output)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["paths"]
    assert DEMO_PASSWORD not in result.stdout + result.stderr
