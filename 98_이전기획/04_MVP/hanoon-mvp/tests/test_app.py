import json
from pathlib import Path

import pytest

from app import create_app


@pytest.fixture()
def client():
    app = create_app({"TESTING": True})
    return app.test_client()


@pytest.mark.parametrize("path", ["/", "/demo", "/store/demo"])
def test_pages_render(client, path):
    response = client.get(path)
    assert response.status_code == 200


def test_analyze_returns_demo_report(client):
    response = client.post(
        "/api/demo/analyze",
        json={
            "storeName": "망원 골목국수",
            "category": "한식당",
            "area": "서울 마포구 망원동",
            "primaryUrl": "https://example.com/store",
            "naverUrl": "",
            "instagramUrl": "",
        },
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["ok"] is True
    assert data["isDemo"] is True
    assert len(data["report"]["issues"]) == 3


def test_analyze_rejects_missing_required_field(client):
    response = client.post(
        "/api/demo/analyze",
        json={"storeName": "", "category": "한식당", "area": "서울", "primaryUrl": ""},
    )
    data = response.get_json()

    assert response.status_code == 400
    assert data["error"]["code"] == "INVALID_INPUT"
    assert "storeName" in data["error"]["fields"]


def test_analyze_rejects_invalid_url(client):
    response = client.post(
        "/api/demo/analyze",
        json={
            "storeName": "망원 골목국수",
            "category": "한식당",
            "area": "서울",
            "primaryUrl": "not-a-url",
        },
    )
    assert response.status_code == 400
    assert "primaryUrl" in response.get_json()["error"]["fields"]


def test_approve_returns_preview_url(client):
    response = client.post(
        "/api/demo/approve",
        json={
            "reportId": "demo-mangwon-noodle",
            "englishDescription": "A clear English store description that is long enough for the demo.",
        },
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["previewUrl"] == "/store/demo"


def test_demo_data_has_required_sections():
    data_path = Path(__file__).parents[1] / "data" / "demo_store.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    required = {"store", "measurement", "before", "after", "issues", "improvements", "publicPage"}
    assert required.issubset(data.keys())
