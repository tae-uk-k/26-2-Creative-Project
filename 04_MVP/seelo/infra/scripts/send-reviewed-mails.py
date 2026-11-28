"""승인된 검토본 10통만 운영 API의 SMTP 어댑터로 보낸다. 일반 큐는 소비하지 않는다.

서버 root로 실행한다. sending/uncertain 상태는 자동 재발송하지 않는다.
SMTP 수락은 받은편지함 도착 확인과 다르다.
"""

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

APPROVED_RECIPIENT = "xodnrdl0606@gmail.com"
EXPECTED_TYPES = {
    "verify_email",
    "password_reset",
    "diagnosis_result",
    "fix_requested",
    "fix_decided",
    "map_connection",
    "fix_plan_ready",
    "manual_required",
    "fix_completed",
    "report_ready",
}
SEND = """
import asyncio,json,sys
from seelo.integrations.mailer import SmtpMailer
payload=json.load(sys.stdin)
asyncio.run(SmtpMailer().send(to=[payload['to']],subject=payload['subject'],text=payload['text'],html=payload['html']))
print(json.dumps({'smtp_accepted':True}))
"""


def send(
    review_file: Path, approved_hash: str, recipient: str, state_dir: Path
) -> dict:
    if recipient != APPROVED_RECIPIENT:
        raise ValueError("unapproved_recipient")
    payload = review_file.read_bytes()
    if hashlib.sha256(payload).hexdigest() != approved_hash:
        raise ValueError("unapproved_preview")
    messages = json.loads(payload)
    if len(messages) != 10 or {m["type"] for m in messages} != EXPECTED_TYPES:
        raise ValueError("unexpected_message_types")
    if any(
        not m["subject"].startswith("[seelo 수신시험]")
        or "https://seelo.invalid" not in m["text"]
        for m in messages
    ):
        raise ValueError("not_test_content")
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    for message in messages:
        path = state_dir / (message["type"] + ".json")
        if path.exists():
            previous = json.loads(path.read_text())
            if (
                previous.get("status") == "smtp_accepted"
                and previous.get("preview_sha256") == approved_hash
            ):
                continue
            raise RuntimeError("previous_attempt_requires_delivery_review")
        receipt = {
            "type": message["type"],
            "status": "sending",
            "preview_sha256": approved_hash,
            "recipient_sha256": hashlib.sha256(recipient.encode()).hexdigest(),
            "attempted_at": datetime.now(UTC).isoformat(),
        }
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt, indent=2))
        path.chmod(0o600)
        try:
            result = subprocess.run(
                [
                    "/usr/local/sbin/seelo-compose",
                    "exec",
                    "-T",
                    "api",
                    "python",
                    "-c",
                    SEND,
                ],
                input=json.dumps({**message, "to": recipient}),
                text=True,
                capture_output=True,
                timeout=45,
            )
            accepted = (
                result.returncode == 0
                and json.loads(result.stdout).get("smtp_accepted") is True
            )
        except (subprocess.TimeoutExpired, ValueError):
            accepted = False
        receipt["status"] = "smtp_accepted" if accepted else "uncertain"
        path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(
            json.dumps({"type": message["type"], "status": receipt["status"]}),
            flush=True,
        )
        if not accepted:
            raise RuntimeError("delivery_review_required_before_retry")
    return {
        "smtp_accepted": 10,
        "recipient_count": 1,
        "inbox_verified": False,
        "general_email_worker_enabled": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-file", type=Path, required=True)
    parser.add_argument("--approved-sha256", required=True)
    parser.add_argument("--to", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            send(args.review_file, args.approved_sha256, args.to, args.state_dir)
        )
    )
