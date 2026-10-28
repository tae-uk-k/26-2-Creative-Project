import json
import os
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "demo_store.json"


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        JSON_AS_ASCII=False,
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )

    if test_config:
        app.config.update(test_config)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/demo")
    def demo():
        demo_data = load_demo_data()
        return render_template(
            "demo.html",
            example=demo_data["store"],
            measurement=demo_data["measurement"],
        )

    @app.get("/store/demo")
    def store_preview():
        demo_data = load_demo_data()
        return render_template("store_preview.html", store=demo_data["publicPage"])

    @app.post("/api/demo/analyze")
    def analyze():
        body = request.get_json(silent=True) or {}
        errors = validate_store_input(body)
        if errors:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": {
                            "code": "INVALID_INPUT",
                            "message": "입력한 가게 정보를 확인해 주세요.",
                            "fields": errors,
                        },
                    }
                ),
                400,
            )

        demo_data = load_demo_data()
        report = {
            "id": demo_data["reportId"],
            "isDemo": True,
            "store": {
                **demo_data["store"],
                "nameKo": body["storeName"].strip(),
                "categoryKo": body["category"].strip(),
                "areaKo": body["area"].strip(),
                "submittedUrl": body["primaryUrl"].strip(),
            },
            "measurement": demo_data["measurement"],
            "before": demo_data["before"],
            "issues": demo_data["issues"],
            "improvements": demo_data["improvements"],
            "after": demo_data["after"],
            "disclaimer": demo_data["disclaimer"],
        }
        return jsonify(
            {
                "ok": True,
                "isDemo": True,
                "message": "시연용 진단이 완료되었습니다.",
                "report": report,
            }
        )

    @app.post("/api/demo/approve")
    def approve():
        body = request.get_json(silent=True) or {}
        report_id = str(body.get("reportId", "")).strip()
        description = str(body.get("englishDescription", "")).strip()

        if report_id != load_demo_data()["reportId"]:
            return jsonify_error("REPORT_NOT_FOUND", "시연 보고서를 찾을 수 없습니다.")
        if len(description) < 30:
            return jsonify_error(
                "INVALID_DESCRIPTION",
                "영문 소개는 30자 이상 입력해 주세요.",
            )

        return jsonify(
            {
                "ok": True,
                "isDemo": True,
                "message": "영문 소개 문안이 승인되었습니다.",
                "previewUrl": "/store/demo",
            }
        )

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify_error("REQUEST_TOO_LARGE", "요청 데이터가 너무 큽니다.", 413)

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify_error(
            "INTERNAL_ERROR",
            "시연 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
            500,
        )

    return app


def load_demo_data():
    with DATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_store_input(body):
    errors = {}
    required_fields = {
        "storeName": "가게명을 입력해 주세요.",
        "category": "업종을 입력해 주세요.",
        "area": "지역을 입력해 주세요.",
        "primaryUrl": "대표 채널 링크를 입력해 주세요.",
    }

    for field, message in required_fields.items():
        if not str(body.get(field, "")).strip():
            errors[field] = message

    for field in ("primaryUrl", "naverUrl", "instagramUrl"):
        value = str(body.get(field, "")).strip()
        if value and not is_valid_http_url(value):
            errors[field] = "https://로 시작하는 올바른 링크를 입력해 주세요."

    return errors


def is_valid_http_url(value):
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def jsonify_error(code, message, status=400):
    return jsonify({"ok": False, "error": {"code": code, "message": message}}), status


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(
        host="127.0.0.1",
        port=port,
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
