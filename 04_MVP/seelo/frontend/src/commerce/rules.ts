import { ApiError } from "../api/client";
import {
  factInputSchema,
  generateSchema,
  publicUrl,
  type Command,
  type Field,
  type Plan,
  type Workspace,
} from "./schemas";
const reject = (message: string): never => {
  throw new ApiError(409, "INVALID_STATE", message);
};
export function selectableFields(workspace: Workspace): Field[] {
  const { automatic, manual } = workspace.product.fieldSupport;
  return [...automatic, ...manual];
}
export function latestPlan(workspace: Workspace): Plan | undefined {
  return workspace.plans.reduce<Plan | undefined>(
    (latest, plan) => (!latest || latest.id < plan.id ? plan : latest),
    undefined,
  );
}
// 저장 중이거나 관리 화면 작업이 대기·실행 중이면 새 명령을 막고 상태를 다시 조회한다.
export function isRunning(workspace: Workspace): boolean {
  const prepare = workspace.product.prepareJob;
  if (
    prepare &&
    ["queued", "running"].includes(prepare.status) &&
    !prepare.stale
  )
    return true;
  return workspace.plans.some(
    (plan) =>
      plan.status === "applying" ||
      Boolean(
        plan.job &&
        ["queued", "running"].includes(plan.job.status) &&
        !plan.job.stale,
      ),
  );
}
export const jobErrors: Record<string, string> = {
  login_required:
    "담당자 브라우저 로그인이 만료됐습니다. 운영자가 다시 로그인한 뒤 실행해 주세요.",
  captcha: "보안 문자 확인이 필요합니다. 운영자가 직접 해결해야 합니다.",
  security_check:
    "플랫폼 보안 확인이 필요합니다. 운영자가 직접 해결해야 합니다.",
  shop_identity_mismatch:
    "열린 관리 화면의 스토어가 등록한 스토어와 다릅니다. 저장 전에 멈췄습니다.",
  shop_not_delegated: "위임 목록에서 이 스토어를 찾지 못했습니다.",
  shop_selection_ambiguous:
    "위임 목록에 같은 값의 스토어가 여러 개라 선택하지 않았습니다.",
  product_identity_mismatch: "열린 상품번호가 요청한 상품과 다릅니다.",
  browser_source_changed:
    "관리 화면의 원본이 승인 후 바뀌었습니다. 다시 수집해 주세요.",
  commerce_source_changed:
    "상품 원본이 승인 후 바뀌었습니다. 다시 수집해 주세요.",
  protected_field_changed:
    "가격·재고 등 보호 항목이 바뀌어 저장하지 않았습니다.",
  unexpected_screen: "예상과 다른 관리 화면이라 멈췄습니다.",
  selectors_missing: "이 화면의 자동화 설정이 없습니다.",
  stalled:
    "작업이 오래 멈춰 중단 처리했습니다. 저장 여부는 재조회로 확인합니다.",
  disconnected: "연결 해제로 실행하지 않았습니다.",
  manager_verification_required: "관리자 위임 권한 확인이 필요합니다.",
  internal_error: "작업 중 오류가 났습니다. 운영자가 기록을 확인합니다.",
  commerce_ai_unavailable: "AI 연결·모델 설정을 확인해 주세요.",
  unverifiable_extraction:
    "AI가 원문에 없는 내용을 냈습니다. 저장하지 않고 멈췄습니다.",
  active_plan: "승인·저장 중인 정비안이 있어 새로 만들지 않았습니다.",
  no_automatic_fields:
    "현재 수정 방식에서 자동 저장할 수 있는 항목이 없습니다.",
};
export function jobMessage(code: string | null | undefined): string {
  return code ? (jobErrors[code] ?? `작업 실패: ${code}`) : "";
}
export function planById(
  workspace: Workspace,
  planId: number | undefined,
): Plan | undefined {
  return planId === undefined
    ? latestPlan(workspace)
    : workspace.plans.find((plan) => plan.id === planId);
}
export const verifiableStatuses: Plan["status"][] = [
  "applying",
  "pending_reflection",
  "uncertain",
  "applied",
  "rolled_back",
];
export function editingLabel(workspace: Workspace): string {
  return workspace.product.fieldSupport.mode === "browser"
    ? "관리 화면"
    : "API";
}
export function publicationComplete(plan: Plan): boolean {
  return Boolean(
    plan.publication.pc_matches &&
    plan.publication.mobile_matches &&
    plan.publication.checked_at,
  );
}
export function approvedChanges(plan: Plan) {
  return plan.changes.filter((change) =>
    (plan.approval?.fields ?? []).includes(change.field),
  );
}
export function validChanges(
  workspace: Workspace,
  plan: Plan,
  fields: Field[] = plan.changes.map((change) => change.field),
): boolean {
  return (
    plan.snapshotHash === workspace.product.snapshotHash &&
    fields.length > 0 &&
    new Set(fields).size === fields.length &&
    fields.every((field) =>
      plan.changes.some((change) => change.field === field),
    ) &&
    plan.changes
      .filter((change) => fields.includes(change.field))
      .every(
        (change) =>
          (change.method === "manual"
            ? selectableFields(workspace).includes(change.field)
            : workspace.product.fieldSupport.automatic.includes(
                change.field,
              )) &&
          change.before === (workspace.product.fields[change.field] ?? "") &&
          change.before !== change.proposed &&
          change.evidence.length > 0 &&
          change.evidence.every(
            (fact) =>
              fact.identity.trim() === workspace.product.identity.trim() &&
              fact.quote.includes(fact.value) &&
              (fact.source === "owner_answer" ||
                (fact.source_url !== null &&
                  publicUrl.safeParse(fact.source_url).success)),
          ),
      )
  );
}
export function stageOf(workspace: Workspace): string {
  const plan = latestPlan(workspace);
  if (!plan) return "원본 수집 완료 · 근거 수집·정비안 생성 대기";
  const labels: Record<Plan["status"], string> = {
    draft: "정비안 승인 대기",
    approved: "승인 완료 · 적용 대기",
    no_changes: "변경 없음 · 보완·보류 확인",
    applying: "저장 중 · 상태 조회 필요",
    applied: publicationComplete(plan)
      ? `저장·${editingLabel(workspace)} 재조회·PC·모바일 확인 완료`
      : `저장·${editingLabel(workspace)} 재조회 완료 · 공개 반영 미확인`,
    pending_reflection: "저장 후 재조회 값 불일치 · 확인 필요",
    uncertain: "저장 결과 미확인 · 재전송 없이 조회 필요",
    conflict: "원본 변경 충돌 · 다시 수집 필요",
    rejected: "저장 요청 실패",
    manual_required: "관리자 수동 편집 필요",
    manual_recorded: publicationComplete(plan)
      ? "수동 편집 기록·PC·모바일 확인 완료"
      : "수동 편집 기록됨 · 공개 반영 미확인",
    rolled_back: publicationComplete(plan)
      ? "원본 값 복구·공개 반영 확인 완료"
      : "원본 값 복구됨 · 공개 반영 미확인",
    superseded: "새 정비안으로 대체됨",
  };
  return labels[plan.status];
}
export type Viewer = { isAdmin: boolean; userId?: number };
// 고객(스토어 소유자)이 정비안을 승인한다. 운영자는 고객이 승인한 정비안만 실행한다.
export function isOwner(workspace: Workspace, viewer: Viewer): boolean {
  return (
    viewer.userId === undefined || viewer.userId === workspace.store.ownerId
  );
}
export function customerApproved(workspace: Workspace, plan: Plan): boolean {
  return plan.approval?.approvedBy === workspace.store.ownerId;
}
export function validateCommand(
  workspace: Workspace,
  command: Command,
  viewerOrAdmin: Viewer | boolean = false,
): void {
  const viewer: Viewer =
    typeof viewerOrAdmin === "boolean"
      ? { isAdmin: viewerOrAdmin }
      : viewerOrAdmin;
  const { product } = workspace;
  const plan = latestPlan(workspace);
  if (isRunning(workspace) && command.action !== "verify")
    reject("저장 중입니다. 최신 상태를 먼저 확인해 주세요.");
  // 자료 보완·정비안 생성·승인은 고객 계정에서 한다. 서버도 같은 소유자 검사를 한다.
  if (
    ["research", "facts", "answers", "generate", "prepare"].includes(
      command.action,
    ) &&
    !isOwner(workspace, viewer)
  )
    reject("고객 계정에서 진행하는 단계입니다.");
  if (command.action === "prepare") {
    if (command.sourceUrls.length > 3)
      reject("추가 자료 주소는 3개까지 입력해 주세요.");
    command.sourceUrls.forEach((url) => publicUrl.parse(url));
    if (
      workspace.plans.some((plan) =>
        ["approved", "applying", "pending_reflection", "uncertain"].includes(
          plan.status,
        ),
      )
    )
      reject("진행 중인 정비안이 있습니다.");
    return;
  }
  if (command.action === "research") {
    if (command.sourceUrls.length > 3)
      reject("추가 자료 주소는 3개까지 입력해 주세요.");
    command.sourceUrls.forEach((url) => publicUrl.parse(url));
    return;
  }
  if (command.action === "facts") {
    if (!command.facts.length || command.facts.length > 30)
      reject("근거는 1~30개를 입력해 주세요.");
    for (const fact of command.facts) {
      factInputSchema.parse(fact);
      if (fact.identity.trim() !== product.identity.trim())
        reject("상품·모델·옵션이 같은 근거가 필요합니다.");
    }
    return;
  }
  if (command.action === "answers") {
    const entries = Object.entries(command.answers);
    if (
      !plan ||
      entries.length < 1 ||
      entries.length > 3 ||
      entries.some(
        ([key, value]) =>
          !value?.trim() ||
          value.length > 1000 ||
          !plan.questions.some((question) => question.field === key),
      )
    )
      reject("현재 질문의 답변을 확인해 주세요.");
    return;
  }
  if (command.action === "generate") {
    generateSchema.parse(command);
    const selectable = selectableFields(workspace);
    if (command.fields.some((field) => !selectable.includes(field)))
      reject("현재 수정 방식에서 지원하는 항목만 선택해 주세요.");
    if (
      workspace.plans.some((plan) =>
        ["approved", "applying", "pending_reflection", "uncertain"].includes(
          plan.status,
        ),
      )
    )
      reject("진행 중인 정비안이 있습니다.");
    return;
  }
  // 승인은 최신 정비안만 받는다. 저장 확인·복구·기록은 이력에서 고른 정비안도 대상으로 한다.
  const target = planById(workspace, command.planId);
  if (!target || (command.action === "approve" && target.id !== plan?.id))
    reject("현재 정비안을 다시 조회해 주세요.");
  return validatePlanCommand(workspace, target!, command, viewer);
}
function validatePlanCommand(
  workspace: Workspace,
  plan: Plan,
  command: Exclude<
    Command,
    { action: "research" | "facts" | "answers" | "generate" | "prepare" }
  >,
  viewer: Viewer,
): void {
  const { store, product } = workspace;
  const isAdmin = viewer.isAdmin;
  if (command.action === "approve" && !isOwner(workspace, viewer))
    reject("정비안 승인은 스토어 소유자만 할 수 있습니다.");
  if (
    (command.action === "apply" || command.action === "rollback") &&
    !isOwner(workspace, viewer) &&
    (!isAdmin || !customerApproved(workspace, plan))
  )
    reject("고객이 승인한 정비안만 운영자가 실행할 수 있습니다.");
  if (command.action === "approve") {
    const fields = command.fields ?? plan.changes.map((change) => change.field);
    if (
      plan.status !== "draft" ||
      command.snapshotHash !== product.snapshotHash ||
      !validChanges(workspace, plan, fields)
    )
      reject("원본·근거·변경 범위를 다시 확인해 주세요.");
    if (
      store.platform === "smartstore" &&
      plan.changes.some(
        (change) =>
          fields.includes(change.field) &&
          change.field === "description" &&
          change.method === "api",
      ) &&
      !command.editorConversionConfirmed
    )
      reject("상세설명의 HTML 전환을 별도로 확인해 주세요.");
    return;
  }
  if (command.action === "publication") {
    if (
      !isAdmin ||
      !["applied", "manual_recorded", "rolled_back"].includes(plan.status)
    )
      reject("관리자의 공개 반영 확인이 필요합니다.");
    publicUrl.parse(command.pcUrl);
    publicUrl.parse(command.mobileUrl);
    if (!command.note.trim()) reject("확인 기록을 입력해 주세요.");
    return;
  }
  if (command.action === "manual-result") {
    const expected = Object.fromEntries(
      approvedChanges(plan).map((change) => [change.field, change.proposed]),
    );
    if (
      !isAdmin ||
      store.managerStatus !== "verified" ||
      !Object.keys(expected).length ||
      !["approved", "manual_required"].includes(plan.status) ||
      !command.note.trim() ||
      Object.keys(expected).length !== Object.keys(command.values).length ||
      Object.entries(expected).some(
        ([key, value]) => command.values[key] !== value,
      )
    )
      reject("관리 권한과 승인한 값의 수동 편집 결과를 확인해 주세요.");
    return;
  }
  if (command.action === "verify") {
    if (!verifiableStatuses.includes(plan.status))
      reject("저장 요청 이력이 필요합니다.");
    return;
  }
  if (command.action === "rollback") {
    if (!command.confirmed || plan.status !== "applied")
      reject("저장이 확인된 변경만 원본 값으로 복구할 수 있습니다.");
  } else {
    if (plan.status !== "approved") reject("정비안 승인이 필요합니다.");
    if (approvedChanges(plan).some((change) => change.method === "manual"))
      return;
  }
  if (!approvedChanges(plan).length)
    reject("서버에서 승인한 필드 목록을 확인하지 못했습니다.");
  if (!store.automaticWritesEnabled)
    reject("서버의 상품 자동 수정이 꺼져 있습니다.");
  if (product.automaticWritesEnabled === false)
    reject("이 상품의 자동 수정이 허용되지 않았습니다.");
  if (product.snapshotSource === "browser") {
    if (store.managerStatus !== "verified")
      reject("관리자 위임 권한 확인이 필요합니다.");
  } else if (product.fieldSupport.mode === "browser") {
    reject("관리자 화면에서 직접 수집한 원본이 필요합니다.");
  } else if (
    !["authorized", "read_verified", "write_verified"].includes(
      store.apiStatus,
    ) ||
    product.snapshotSource !== "api"
  ) {
    reject("상품을 수정할 API 연결과 직접 수집한 원본이 필요합니다.");
  }
}
