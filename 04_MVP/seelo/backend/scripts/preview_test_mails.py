"""메일 10종의 검토본만 생성한다. SMTP 연결·큐 등록·계정 생성 기능은 없다."""

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seelo.config import get_settings  # noqa: E402
from seelo.services.email_render import render_email  # noqa: E402

SAMPLES = {
    "verify_email": ({}, {"token": "TEST-NOT-A-VALID-TOKEN"}),
    "password_reset": ({"social_provider": None}, {"token": "TEST-NOT-A-VALID-TOKEN"}),
    "diagnosis_result": ({"result": "completed", "run_id": 0, "openai_rate": 0.2, "gemini_rate": None}, None),
    "fix_requested": ({"request_id": 0, "store_name": "수신시험 전용 가상 가게"}, None),
    "fix_decided": ({"decision": "rejected", "reject_reason": "시험용 문구"}, None),
    "map_connection": ({"kind": "connected", "provider": "kakao"}, None),
    "fix_plan_ready": ({"plan_id": 0, "provider": "google", "item_count": 3}, None),
    "manual_required": (
        {
            "request_id": 0,
            "items": [
                {"provider": "google", "field_label": "영업시간", "reason": "automation_blocked"},
            ],
        },
        None,
    ),
    "fix_completed": ({"changed_fields": ["시험용 영업시간"], "remeasure_date": "2026-11-30"}, None),
    "report_ready": ({"report_id": 0}, None),
}
BANNER = "[수신시험] 모든 가게·결과·변경 내역은 가상 예시입니다. 링크는 작동하지 않는 시험 주소입니다."


def build(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    # 예약 도메인 .invalid만 쓴다. 실제 계정 인증·관리 화면 링크를 시험 메일에 넣지 않는다.
    get_settings().app_base_url = "https://seelo.invalid"
    messages = []
    sections = []
    for kind, (params, secret) in SAMPLES.items():
        rendered = render_email(kind, params, secret)
        subject = "[seelo 수신시험] " + rendered.subject.removeprefix("[seelo] ")
        text = BANNER + "\n\n" + rendered.text
        message = {
            "type": kind,
            "subject": subject,
            "text": text,
            "html": "<p>" + html.escape(BANNER) + "</p>" + rendered.html,
        }
        messages.append(message)
        sections.append(
            "<section><h2>"
            + html.escape(kind + " — " + subject)
            + "</h2><pre>"
            + html.escape(text)
            + "</pre></section>"
        )
    payload = (json.dumps(messages, ensure_ascii=False, indent=2) + "\n").encode()
    (output / "messages.json").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    review = {
        "count": len(messages),
        "preview_sha256": digest,
        "sent": 0,
        "external_connections": False,
        "links": "https://seelo.invalid",
    }
    (output / "review.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
    (output / "index.html").write_text(
        '<!doctype html><html lang="ko"><meta charset="utf-8"><title>seelo 메일 수신시험 검토본</title>'
        "<style>body{max-width:900px;margin:40px auto;font:16px/1.65 sans-serif;color:#223}"
        "section{border:1px solid #ccd;border-radius:12px;padding:24px;margin:24px 0}"
        "pre{white-space:pre-wrap;font:inherit}h2{font-size:18px}</style>"
        "<h1>메일 10종 수신시험 검토본</h1><p>아직 발송하지 않았습니다. 모든 내용은 시험용 예시입니다.</p>"
        + "".join(sections)
        + "</html>",
        encoding="utf-8",
    )
    return review


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output)))
