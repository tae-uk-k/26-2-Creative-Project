import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CircleCheck, Link2, MessageSquareText } from "lucide-react";
import { useCommand, useWorkspace, useWrites } from "../app/commerce";
import { useSession } from "../app/runtime";
import {
  approvedChanges,
  customerApproved,
  isRunning,
  latestPlan,
  validChanges,
} from "../commerce/rules";
import {
  factNames,
  fieldNames,
  type FactKey,
  type Field,
  type Plan,
  type Workspace,
} from "../commerce/schemas";
import { Button, ButtonLink } from "../ui/Button";
import { Badge, Chip, Notice, Panel } from "../ui/Display";
import { DiffView } from "../ui/DiffView";
import { Checkbox } from "../ui/Field";
import { Page, PageHeader, Stack } from "../ui/Layout";
import { ActionBar, ConfirmDialog } from "../ui/Overlay";
import { Timeline } from "../ui/Steps";
import { methodLabels, planLabels, planTones, when } from "../ui/labels";
import { ErrorMessage, InvalidPath, QueryState } from "./common";
import { RollbackAction, productPath, useIds } from "./product";
import styles from "./product.module.css";

export function PlanPage() {
  const ids = useIds();
  const { planId = "" } = useParams();
  const id = Number(planId);
  const workspace = useWorkspace(ids?.storeId ?? 0, ids?.productId ?? 0);
  if (!ids || !Number.isSafeInteger(id) || id <= 0) return <InvalidPath />;
  const plan = workspace.data?.plans.find((item) => item.id === id);
  return (
    <Page width="medium">
      <QueryState
        pending={workspace.isPending}
        error={workspace.error}
        retry={workspace.refetch}
      />
      {workspace.data && !plan && (
        <Notice
          tone="error"
          action={
            <ButtonLink
              to={productPath(ids.storeId, ids.productId)}
              size="sm"
              variant="secondary"
            >
              상품으로
            </ButtonLink>
          }
        >
          정비안을 찾지 못했어요.
        </Notice>
      )}
      {workspace.data && plan && (
        <PlanReview
          key={`${plan.id}/${plan.status}`}
          workspace={workspace.data}
          plan={plan}
        />
      )}
    </Page>
  );
}
function PlanReview({ workspace, plan }: { workspace: Workspace; plan: Plan }) {
  const session = useSession();
  const navigate = useNavigate();
  const command = useCommand(workspace.store.id, workspace.product.id);
  const owner = !session.data || session.data.id === workspace.store.ownerId;
  const latest = latestPlan(workspace)?.id === plan.id;
  const editable = latest && plan.status === "draft" && owner;
  const [selected, setSelected] = useState<Field[]>(
    plan.approval?.fields ?? plan.changes.map((change) => change.field),
  );
  const [editorConfirmed, setEditorConfirmed] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const back = productPath(workspace.store.id, workspace.product.id);
  const editorConsent =
    workspace.store.platform === "smartstore" &&
    plan.changes.some(
      (change) =>
        selected.includes(change.field) &&
        change.field === "description" &&
        change.method === "api",
    );
  const valid =
    validChanges(workspace, plan, selected) &&
    !(editorConsent && !editorConfirmed);
  const busy = command.isPending || isRunning(workspace);
  const shown =
    plan.status === "draft"
      ? plan.changes
      : plan.changes.filter((change) =>
          (plan.approval?.fields ?? []).includes(change.field),
        );
  const approve = () =>
    void command
      .run({
        action: "approve",
        planId: plan.id,
        snapshotHash: workspace.product.snapshotHash,
        fields: selected,
        editorConversionConfirmed: editorConfirmed,
      })
      .then(() => navigate(back))
      .catch(() => setConfirm(false));
  return (
    <>
      <PageHeader
        back={{ to: back, label: workspace.product.name }}
        eyebrow={
          <>
            <span>정비안 #{plan.id}</span>
            <Badge tone={planTones[plan.status]} dot>
              {planLabels[plan.status]}
            </Badge>
            {!latest && <Badge>이전 정비안</Badge>}
          </>
        }
        title={editable ? "바뀌는 내용을 확인해 주세요" : "정비안"}
        description={
          editable ? "반영하지 않을 항목은 선택을 풀어 주세요." : undefined
        }
      />
      <Stack>
        {plan.questions.length > 0 && latest && (
          <Notice
            tone="warning"
            title={`답하지 않은 질문 ${plan.questions.length}개`}
            action={
              <ButtonLink to={back} size="sm" variant="secondary">
                답하러 가기
              </ButtonLink>
            }
          >
            답하면 더 정확한 정비안을 다시 만들어요.
          </Notice>
        )}
        {latest && plan.status === "draft" && !owner && (
          <Notice>고객 승인 대기 · 운영자는 승인할 수 없습니다.</Notice>
        )}
        {shown.map((change) => {
          const checked = selected.includes(change.field);
          return (
            <Panel
              key={change.field}
              aria-label={fieldNames[change.field]}
              title={
                <span
                  style={{
                    display: "inline-flex",
                    gap: "0.5rem",
                    alignItems: "center",
                  }}
                >
                  {fieldNames[change.field]}
                  <Badge tone={change.method === "manual" ? "orange" : "blue"}>
                    {methodLabels[change.method]}
                  </Badge>
                </span>
              }
              action={
                editable ? (
                  <Checkbox
                    aria-label={`${fieldNames[change.field]} 승인 선택`}
                    label="반영"
                    checked={checked}
                    disabled={busy}
                    onChange={(event) =>
                      setSelected((current) =>
                        event.target.checked
                          ? [...current, change.field]
                          : current.filter((field) => field !== change.field),
                      )
                    }
                  />
                ) : undefined
              }
            >
              <div
                style={{
                  display: "grid",
                  gap: "1rem",
                  opacity: editable && !checked ? 0.45 : 1,
                }}
              >
                <DiffView before={change.before} after={change.proposed} />
                <div
                  style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}
                >
                  {change.evidence.map((fact) =>
                    fact.source_url ? (
                      <Chip
                        key={fact.key}
                        href={fact.source_url}
                        icon={<Link2 aria-hidden="true" />}
                        title={fact.quote}
                      >
                        {factNames[fact.key]}: {fact.value}
                      </Chip>
                    ) : (
                      <Chip
                        key={fact.key}
                        icon={<MessageSquareText aria-hidden="true" />}
                        title="판매자 답변"
                      >
                        {factNames[fact.key]}: {fact.value}
                      </Chip>
                    ),
                  )}
                </div>
                {editable &&
                  change.field === "description" &&
                  change.method === "api" &&
                  workspace.store.platform === "smartstore" && (
                    <Checkbox
                      checked={editorConfirmed}
                      onChange={(event) =>
                        setEditorConfirmed(event.target.checked)
                      }
                      label="스마트에디터 대신 HTML 형식으로 바뀌는 것을 확인했어요."
                    />
                  )}
              </div>
            </Panel>
          );
        })}
        {plan.deferred.length > 0 && (
          <Panel title="아직 확인하지 못한 정보" small flat>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
              {plan.deferred.map((key) => (
                <Chip key={key}>
                  {key.startsWith("fact:")
                    ? factNames[key.slice(5) as FactKey]
                    : (fieldNames[key as Field] ?? key)}
                </Chip>
              ))}
            </div>
          </Panel>
        )}
        {plan.status !== "draft" && (
          <WriteHistory plan={plan} workspace={workspace} />
        )}
        {session.data?.role === "admin" && (
          <RollbackAction
            ctx={{
              workspace,
              pending: command.isPending,
              run: (value) =>
                command.run(value).then(
                  () => true,
                  () => false,
                ),
            }}
            plan={plan}
          />
        )}
        <ErrorMessage error={command.error} />
      </Stack>
      {editable && (
        <ActionBar
          summary={
            <>
              <b>{selected.length}개</b> 항목을 승인합니다
            </>
          }
        >
          <Button
            size="lg"
            icon={<CircleCheck aria-hidden="true" />}
            disabled={busy || !valid}
            onClick={() => setConfirm(true)}
          >
            승인하기
          </Button>
        </ActionBar>
      )}
      <ConfirmDialog
        open={confirm}
        title={`${selected.length}개 항목을 승인할까요?`}
        confirmLabel="정비안 승인"
        busy={command.isPending}
        onConfirm={approve}
        onClose={() => setConfirm(false)}
      >
        <p>{selected.map((field) => fieldNames[field]).join(", ")}</p>
        <p>
          seelo가 확인한 뒤 쇼핑몰에 반영해요. 가격·재고·옵션은 바꾸지 않아요.
        </p>
      </ConfirmDialog>
    </>
  );
}
function WriteHistory({
  plan,
  workspace,
}: {
  plan: Plan;
  workspace: Workspace;
}) {
  const writes = useWrites(plan.id);
  const items = [
    plan.approvedAt && {
      key: "approved",
      title: customerApproved(workspace, plan) ? "판매자 승인" : "승인",
      text: `${when(plan.approvedAt)} · ${approvedChanges(plan).length}개 항목`,
      state: "done" as const,
    },
    ...(writes.data ?? []).map((write) => ({
      key: `write-${write.id}`,
      title: write.action === "apply" ? "쇼핑몰 반영" : "수정 전으로 되돌림",
      text: `${when(write.createdAt)} · ${planLabels[write.status as Plan["status"]] ?? write.status}`,
      state: (write.errorCode ? "error" : "done") as "error" | "done",
    })),
    plan.publication.checked_at && {
      key: "publication",
      title: "공개 페이지 확인",
      text: `${when(plan.publication.checked_at)} · PC ${plan.publication.pc_matches ? "일치" : "불일치"} · 모바일 ${plan.publication.mobile_matches ? "일치" : "불일치"}`,
      state: (plan.publication.pc_matches && plan.publication.mobile_matches
        ? "done"
        : "error") as "error" | "done",
    },
  ].filter(Boolean) as {
    key: string;
    title: string;
    text: string;
    state: "done" | "error";
  }[];
  return (
    <Panel title="기록" small>
      <ErrorMessage error={writes.error} />
      {items.length ? (
        <Timeline label={`정비안 #${plan.id}의 쓰기 이력`} items={items} />
      ) : (
        <p className={styles.muted}>쓰기 이력이 없습니다.</p>
      )}
    </Panel>
  );
}
