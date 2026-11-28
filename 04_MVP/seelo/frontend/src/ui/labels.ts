// 화면 문구 기준 한 곳. 상태 이름·작업 이름·배지 색을 여기서만 정한다.
import type {
  Job,
  MeasureRun,
  Plan,
  Product,
  Store,
} from "../commerce/schemas";
import type { Tone } from "./Display";

export const managerLabels: Record<Store["managerStatus"], string> = {
  not_requested: "초대 전",
  invited: "확인 중",
  verified: "연결됨",
  revoked: "연결 끊김",
};
export const managerTones: Record<Store["managerStatus"], Tone> = {
  not_requested: "neutral",
  invited: "blue",
  verified: "green",
  revoked: "red",
};
export const apiLabels: Record<Store["apiStatus"], string> = {
  not_connected: "미연결",
  authorized: "인증됨",
  read_verified: "조회 확인됨",
  write_verified: "저장 확인됨",
  revoked: "인증 해제됨",
};
export const planLabels: Record<Plan["status"], string> = {
  draft: "승인 대기",
  no_changes: "바꿀 내용 없음",
  approved: "seelo 확인 중",
  applying: "반영 중",
  applied: "반영 완료",
  pending_reflection: "반영 확인 중",
  uncertain: "결과 확인 중",
  conflict: "상품이 바뀜",
  rejected: "반영 실패",
  manual_required: "직접 수정 중",
  manual_recorded: "직접 수정 완료",
  rolled_back: "되돌림",
  superseded: "새 정비안으로 대체",
};
export const planTones: Record<Plan["status"], Tone> = {
  draft: "blue",
  no_changes: "neutral",
  approved: "blue",
  applying: "blue",
  applied: "green",
  pending_reflection: "orange",
  uncertain: "orange",
  conflict: "red",
  rejected: "red",
  manual_required: "orange",
  manual_recorded: "green",
  rolled_back: "neutral",
  superseded: "neutral",
};
// 운영자 작업함에서 쓰는 이름. 운영자가 다음에 할 일을 기준으로 부른다.
export const operatorPlanLabels: Partial<Record<Plan["status"], string>> = {
  approved: "확인하고 반영",
  manual_required: "직접 수정",
  applying: "반영 결과 확인",
  pending_reflection: "반영 결과 확인",
  uncertain: "반영 결과 확인",
};
export const jobKinds: Record<Job["kind"], string> = {
  collect: "상품 불러오기",
  apply: "쇼핑몰 반영",
  rollback: "되돌리기",
  verify: "반영 결과 확인",
  catalog: "상품 목록 불러오기",
  prepare: "AI 정비 준비",
  forget_session: "담당자 세션 정리",
  measure: "AI 노출 측정",
};
export const methodLabels: Record<"browser" | "api" | "manual", string> = {
  browser: "자동 반영",
  api: "자동 반영(API)",
  manual: "운영자 직접 수정",
};
export const sourceLabels: Record<Product["snapshotSource"], string> = {
  browser: "관리자 화면에서 불러옴",
  api: "API로 불러옴",
  seller_supplied: "직접 입력한 원본",
};
export const runLabels: Record<MeasureRun["status"], string> = {
  queued: "대기",
  running: "측정 중",
  completed: "완료",
  partial: "일부 무효",
  failed: "모두 무효",
};
export const runTones: Record<MeasureRun["status"], Tone> = {
  queued: "neutral",
  running: "blue",
  completed: "green",
  partial: "orange",
  failed: "red",
};
export const providerLabels: Record<"openai" | "gemini", string> = {
  openai: "ChatGPT",
  gemini: "Gemini",
};
export const percent = (value: number | null | undefined) =>
  value === null || value === undefined
    ? "판정 불가"
    : `${Math.round(value * 100)}%`;
const formatter = new Intl.DateTimeFormat("ko-KR", {
  month: "long",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const dayFormatter = new Intl.DateTimeFormat("ko-KR", {
  year: "numeric",
  month: "long",
  day: "numeric",
});
export const when = (value: string | null | undefined) =>
  value ? formatter.format(new Date(value)) : "";
export const day = (value: string | null | undefined) =>
  value ? dayFormatter.format(new Date(value)) : "";
