// 스토어·상품이 지금 어느 단계에 있는지 계산한다. 화면은 이 값으로 다음 행동 하나를 고른다.
import { latestPlan, publicationComplete } from "./rules";
import type { Plan, Product, Store, Workspace } from "./schemas";

export const storeSteps = ["주소 등록", "권한 위임", "seelo 확인", "상품 정비"];
export const apiStoreSteps = ["주소 등록", "API 연결", "상품 정비"];
// 상품을 불러오고 수정할 수 있는 상태인지. 관리자 화면 방식은 위임 확인, API 방식은 인증이 필요하다.
export function storeReady(store: Store): boolean {
  return store.editingMode === "browser"
    ? store.managerStatus === "verified"
    : ["authorized", "read_verified", "write_verified"].includes(
        store.apiStatus,
      );
}
export function storeStage(store: Store): number {
  if (store.editingMode !== "browser") return storeReady(store) ? 2 : 1;
  if (store.managerStatus === "verified") return 3;
  if (store.managerStatus === "invited") return 2;
  return 1;
}
export const productSteps = [
  "상품 불러오기",
  "AI 조사",
  "정보 보완",
  "승인",
  "쇼핑몰 반영",
  "공개 확인",
];
export type ProductPhase =
  | "start"
  | "preparing"
  | "prepare_failed"
  | "questions"
  | "review"
  | "nothing"
  | "waiting"
  | "applying"
  | "check"
  | "manual"
  | "problem"
  | "conflict"
  | "published"
  | "unpublished"
  | "rolled_back";
const active = (product: Product) =>
  Boolean(
    product.prepareJob &&
    ["queued", "running"].includes(product.prepareJob.status) &&
    !product.prepareJob.stale,
  );
export function productPhase(
  product: Product,
  plan: Plan | undefined,
): ProductPhase {
  if (active(product)) return "preparing";
  if (
    product.prepareJob &&
    (product.prepareJob.status === "failed" || product.prepareJob.stale) &&
    (!plan || plan.status === "superseded")
  )
    return "prepare_failed";
  if (!plan || plan.status === "superseded") return "start";
  switch (plan.status) {
    case "draft":
      return plan.questions.length ? "questions" : "review";
    case "no_changes":
      return plan.questions.length ? "questions" : "nothing";
    case "approved":
      return "waiting";
    case "applying":
      return "applying";
    case "pending_reflection":
    case "uncertain":
      return "check";
    case "manual_required":
      return "manual";
    case "rejected":
      return "problem";
    case "conflict":
      return "conflict";
    case "applied":
    case "manual_recorded":
      return publicationComplete(plan) ? "published" : "unpublished";
    case "rolled_back":
      return "rolled_back";
  }
}
const phaseStep: Record<ProductPhase, number> = {
  start: 1,
  preparing: 1,
  prepare_failed: 1,
  questions: 2,
  nothing: 2,
  review: 3,
  waiting: 4,
  applying: 4,
  check: 4,
  manual: 4,
  problem: 4,
  conflict: 4,
  unpublished: 5,
  published: 6,
  rolled_back: 6,
};
export function productStep(phase: ProductPhase): number {
  return phaseStep[phase];
}
export function phaseIsError(phase: ProductPhase): boolean {
  return ["prepare_failed", "problem", "conflict"].includes(phase);
}
export function workspacePhase(workspace: Workspace): ProductPhase {
  return productPhase(workspace.product, latestPlan(workspace));
}
export type SummaryState = {
  label: string;
  tone: "neutral" | "blue" | "green" | "orange" | "red";
  // 판매자가 지금 해야 하는 일이 있으면 true. 홈의 할 일 목록에 올린다.
  sellerAction: "answer" | "approve" | "start" | "report" | null;
};
// 상품 목록의 요약으로 상태 이름과 판매자의 다음 행동을 정한다.
export function summaryState(product: Product): SummaryState {
  const summary = product.summary;
  if (!summary)
    return { label: "정비 전", tone: "neutral", sellerAction: null };
  const reportReady = summary.measure.baseline && summary.measure.followUp;
  if (
    summary.prepare &&
    ["queued", "running"].includes(summary.prepare.status) &&
    !summary.prepare.stale
  )
    return { label: "AI 조사 중", tone: "blue", sellerAction: null };
  switch (summary.planStatus) {
    case null:
    case "superseded":
      return summary.prepare?.status === "failed"
        ? { label: "조사 실패", tone: "red", sellerAction: "start" }
        : { label: "정비 전", tone: "neutral", sellerAction: "start" };
    case "draft":
      return summary.questions
        ? { label: "답변 필요", tone: "orange", sellerAction: "answer" }
        : { label: "승인 필요", tone: "blue", sellerAction: "approve" };
    case "no_changes":
      return summary.questions
        ? { label: "답변 필요", tone: "orange", sellerAction: "answer" }
        : { label: "바꿀 내용 없음", tone: "neutral", sellerAction: null };
    case "approved":
      return { label: "seelo 확인 중", tone: "blue", sellerAction: null };
    case "applying":
    case "pending_reflection":
    case "uncertain":
    case "manual_required":
      return { label: "반영 중", tone: "blue", sellerAction: null };
    case "conflict":
      return { label: "상품이 바뀜", tone: "red", sellerAction: "start" };
    case "rejected":
      return { label: "반영 실패", tone: "red", sellerAction: null };
    case "applied":
    case "manual_recorded":
      if (reportReady)
        return {
          label: "보고서 준비됨",
          tone: "green",
          sellerAction: "report",
        };
      return summary.published
        ? { label: "반영 완료", tone: "green", sellerAction: null }
        : { label: "공개 확인 중", tone: "blue", sellerAction: null };
    case "rolled_back":
      return { label: "되돌림", tone: "neutral", sellerAction: null };
    default:
      return { label: "확인 중", tone: "neutral", sellerAction: null };
  }
}
