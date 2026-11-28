"""메일 10종 렌더링(10 4장, 16 1장).

- 본문은 templates/email/{type}.txt.j2 하나만 쓰고, HTML은 같은 본문을 _base.html.j2에 넣어 만든다
  (텍스트와 HTML 내용이 달라지지 않게).
- 변수가 빠지면 StrictUndefined로 렌더 오류가 난다(빈 메일 방지).
- 사장님 메일에는 로그인이 필요한 화면 링크와 요약만 넣는다. 바꾼 값 원문·고쳐야 할 점 내용 금지.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from seelo.config import get_settings
from seelo.domain.labels import MANUAL_REASON_LABEL, MAP_LABEL
from seelo.errors import PROVIDER_LABEL

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates" / "email"
FOOTER = "\n\n— seelo\n이 메일은 발신 전용이에요."

_txt_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=False,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
_html_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True, undefined=StrictUndefined)


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text: str
    html: str
    link: str | None


def _rate_text(rate: float | None) -> str:
    return "측정하지 못함" if rate is None else f"{float(rate) * 100:.1f}%"


def _kst_date_text(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.month}월 {d.day}일"


def _url(path: str) -> str:
    return get_settings().app_base_url.rstrip("/") + path


def _ctx_verify_email(p: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    return {"link": _url(f"/verify-email/{s['token']}")}


def _ctx_password_reset(p: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    social = p.get("social_provider")
    if social:
        return {"social": True, "provider_label": PROVIDER_LABEL[social], "link": _url("/login")}
    return {"social": False, "link": _url(f"/password/reset/{s['token']}")}


def _ctx_diagnosis_result(p: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    completed = p["result"] == "completed"
    return {
        "completed": completed,
        "openai_rate_text": _rate_text(p.get("openai_rate")) if completed else "",
        "gemini_rate_text": _rate_text(p.get("gemini_rate")) if completed else "",
        "link": _url(f"/diagnosis/{p['run_id']}") if completed else _url("/home"),
    }


def _ctx_fix_requested(p: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": p["request_id"],
        "store_name": p["store_name"],
        "link": _url(f"/admin/fix-requests/{p['request_id']}"),
    }


def _ctx_fix_decided(p: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    approved = p["decision"] == "approved"
    return {
        "approved": approved,
        "reject_reason": p.get("reject_reason") or "",
        "link": _url("/fix/connect") if approved else _url("/fix"),
    }


def _ctx_map_connection(p: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    return {
        "connected": p["kind"] == "connected",
        "provider_label": MAP_LABEL[p["provider"]],
        "link": _url("/fix/connect"),
    }


def _ctx_fix_plan_ready(p: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider_label": MAP_LABEL[p["provider"]],
        "item_count": p["item_count"],
        "link": _url(f"/fix/plans/{p['plan_id']}"),
    }


def _ctx_manual_required(p: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    items = [
        {
            "provider_label": MAP_LABEL.get(i["provider"], i["provider"]),
            "field_label": i["field_label"],
            "reason_label": MANUAL_REASON_LABEL.get(i["reason"], i["reason"]),
        }
        for i in p["items"]
    ]
    return {
        "request_id": p["request_id"],
        "items": items,
        "link": _url(f"/admin/fix-requests/{p['request_id']}"),
    }


def _ctx_fix_completed(p: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    return {
        "changed_fields": list(p["changed_fields"]) or ["없음"],  # 모든 칸이 연결 끊김이면 바꾼 칸이 없다
        "remeasure_date_text": _kst_date_text(p["remeasure_date"]),
        "link": _url("/fix"),
    }


def _ctx_report_ready(p: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
    return {"link": _url("/fix/report")}


Ctx = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]

CONTEXTS: dict[str, Ctx] = {
    "verify_email": _ctx_verify_email,
    "password_reset": _ctx_password_reset,
    "diagnosis_result": _ctx_diagnosis_result,
    "fix_requested": _ctx_fix_requested,
    "fix_decided": _ctx_fix_decided,
    "map_connection": _ctx_map_connection,
    "fix_plan_ready": _ctx_fix_plan_ready,
    "manual_required": _ctx_manual_required,
    "fix_completed": _ctx_fix_completed,
    "report_ready": _ctx_report_ready,
}

SUBJECTS: dict[str, Callable[[dict[str, Any]], str]] = {
    "verify_email": lambda c: "[seelo] 이메일 인증을 완료해 주세요",
    "password_reset": lambda c: "[seelo] 로그인 방법 안내" if c["social"] else "[seelo] 비밀번호 재설정 안내",
    "diagnosis_result": lambda c: (
        "[seelo] 무료 진단 결과가 나왔어요" if c["completed"] else "[seelo] 측정을 끝내지 못했어요"
    ),
    "fix_requested": lambda c: "[seelo 관리자] 새 자동 정비 신청",
    "fix_decided": lambda c: (
        "[seelo] 자동 정비 신청이 승인됐어요"
        if c["approved"]
        else "[seelo] 자동 정비 신청이 승인되지 않았어요"
    ),
    "map_connection": lambda c: (
        f"[seelo] {c['provider_label']} 연결이 완료됐어요"
        if c["connected"]
        else "[seelo] 초대가 아직 오지 않았어요"
    ),
    "fix_plan_ready": lambda c: "[seelo] 바꿀 내용을 확인해 주세요",
    "manual_required": lambda c: "[seelo 관리자] 수동 처리가 필요해요",
    "fix_completed": lambda c: "[seelo] 정비를 마쳤어요",
    "report_ready": lambda c: "[seelo] 전후 비교 보고서가 준비됐어요",
}


def render_email(type_: str, params: dict[str, Any], secret: dict[str, Any] | None = None) -> RenderedEmail:
    """KeyError(필수 값 없음)·jinja2 오류는 그대로 올린다(재시도해도 소용없는 오류)."""
    ctx = CONTEXTS[type_](params, secret or {})
    body = _txt_env.get_template(f"{type_}.txt.j2").render(**ctx).strip()
    paragraphs = [p.splitlines() for p in body.split("\n\n") if p.strip()]
    html = _html_env.get_template("_base.html.j2").render(
        subject=SUBJECTS[type_](ctx), paragraphs=paragraphs, link=ctx.get("link")
    )
    return RenderedEmail(subject=SUBJECTS[type_](ctx), text=body + FOOTER, html=html, link=ctx.get("link"))
