"""API가 내려주는 한국어 라벨(16 3장)."""

MAP_LABEL = {"google": "Google 지도", "kakao": "카카오맵"}
SOURCE_LABEL = {
    "google": "Google 지도",
    "kakao": "카카오맵",
    "naver": "네이버 지도",
    "website": "공식 웹사이트",
    "instagram": "인스타그램",
    "web": "외부 사이트",
}
AI_LABEL = {"openai": "ChatGPT", "gemini": "Gemini"}

COLLECTED_ROW_LABEL = {
    "name": "가게 이름",
    "address": "주소",
    "phone": "전화",
    "hours": "영업시간",
    "website": "웹사이트",
    "price": "가격대",
    "category": "업종",
    "menu": "메뉴",
    "intro": "소개",
    "amenities": "편의 정보",
    "instagram": "인스타그램",
}

PRICE_LEVEL_LABEL = {
    "PRICE_LEVEL_FREE": "무료",
    "PRICE_LEVEL_INEXPENSIVE": "저렴",
    "PRICE_LEVEL_MODERATE": "보통",
    "PRICE_LEVEL_EXPENSIVE": "비쌈",
    "PRICE_LEVEL_VERY_EXPENSIVE": "매우 비쌈",
}

ATTENTION_REASON_LABEL = {
    "verification_required": "Google 비즈니스 프로필 소유권 인증이 필요해요",
    "under_review": "Google이 프로필을 검토하고 있어요. 검토가 끝나면 다시 확인할게요",
    "duplicate_profile": "같은 가게 프로필이 따로 있어요. Google에서 중복 프로필을 정리해 주세요",
    "no_owner_authority": "카카오 매장관리 대표 권한이 필요해요",
    "guideline_violation": "프로필이 Google 지침 문제로 제한돼 있어요",
    "store_not_visible": "seelo 계정에서 가게가 보이지 않아요. 초대한 계정과 권한을 확인해 주세요",
    "other": "권한을 확인하고 있어요. seelo 팀이 연락드릴게요",
}

FIX_LOG_STATUS_LABEL = {
    "queued": "정비 중",
    "applied": "완료",
    "pending_reflection": "반영 대기",
    "manual_required": "seelo 팀 처리 중",
    "manual_done": "완료",
    "disconnected": "연결 끊김",
}

MANUAL_REASON_LABEL = {
    "automation_blocked": "자동화 차단(로그인·보안 확인)",
    "write_failed": "저장 실패",
    "not_reflected_24h": "24시간 동안 반영 안 됨",
    "kakao_fix_disabled": "카카오 자동 정비 꺼짐",
    "api_unsupported": "API가 지원하지 않는 칸",
    "automation_disabled": "자동 정비 꺼짐",
}

ADMIN_FILTER_LABEL = {
    "requested": "대기",
    "approved": "승인",
    "connect_waiting": "연결 대기",
    "plan_waiting": "정비안 확인 대기",
    "fixing": "정비 중",
    "manual_required": "수동 처리 필요",
    "remeasure_waiting": "재측정 대기",
    "report_ready": "보고서 완료",
    "rejected": "거절",
    "failed": "실패",
}

CATEGORY_LABEL = {
    "map_missing": "지도에 정보 없음",
    "source_mismatch": "출처끼리 정보 다름",
    "english_missing": "영문 정보 부족",
    "condition_missing": "질문 조건 정보 부족",
    "ai_wrong": "AI가 틀리게 말함",
}

GUIDE_NAME = "가게 이름은 seelo가 바꾸지 않아요. {map} 관리 화면에서 직접 고쳐 주세요."
GUIDE_ADDRESS = (
    "주소는 seelo가 바꾸지 않아요. {map}에서 주소 변경을 직접 신청해 주세요(카카오는 사업자등록증 필요)."
)
GUIDE_CATEGORY = "업종은 seelo가 바꾸지 않아요. {map} 관리 화면에서 직접 고쳐 주세요."
GUIDE_KAKAO_PHONE = "카카오맵 전화번호는 파트너센터에서 직접 고쳐 주세요."
NOTE_DIFFERS = "지금 지도 값이 달라요(사장님이 바꿨거나 아직 반영 전)"
NOTICE_NO_GUARANTEE = (
    "추천 순위나 노출을 보장하지 않습니다. AI 답변은 모델 업데이트나 다른 가게의 변화로도 달라질 수 있어요."
)
HEADLINE_CHANGE = "{ai} 추천 등장률이 {before}%에서 {after}%로 바뀌었어요."
HEADLINE_NO_CHANGE = "이번 측정에서는 큰 변화가 없었어요."
ACCOUNT_DELETE_CONFIRM_TEXT = "탈퇴합니다"
