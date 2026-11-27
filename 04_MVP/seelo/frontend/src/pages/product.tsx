import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowRight,
  FileText,
  Link2,
  MessageSquareText,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import {
  useCommand,
  useImportProduct,
  useMeasureRuns,
  useWorkspace,
} from "../app/commerce";
import { useSession } from "../app/runtime";
import {
  phaseIsError,
  productStep,
  productSteps,
  workspacePhase,
  type ProductPhase,
} from "../commerce/progress";
import { reportPairs } from "../commerce/report";
import {
  approvedChanges,
  customerApproved,
  isRunning,
  jobMessage,
  latestPlan,
} from "../commerce/rules";
import {
  factInputSchema,
  factNames,
  fieldNames,
  generateSchema,
  unavailableReasons,
  type Command,
  type Plan,
  type Workspace,
} from "../commerce/schemas";
import { Button, ButtonLink, TextButton } from "../ui/Button";
import { Badge, Chip, Notice, Panel } from "../ui/Display";
import { readableText } from "../ui/DiffView";
import { Checkbox, Select, TextArea, TextField } from "../ui/Field";
import { Page, PageHeader, Split } from "../ui/Layout";
import { List, ListRow } from "../ui/List";
import { MetricValue } from "../ui/Metric";
import { ConfirmDialog } from "../ui/Overlay";
import { Stepper, Timeline } from "../ui/Steps";
import { PlatformMark } from "../ui/AppShell";
import {
  methodLabels,
  planLabels,
  planTones,
  providerLabels,
  sourceLabels,
  when,
} from "../ui/labels";
import { ErrorMessage, InvalidPath, QueryState, formValues } from "./common";
import styles from "./product.module.css";

const countWord = (value: number) =>
  ["", "한", "두", "세", "네", "다섯"][value] ?? String(value);
const sourceUrls = (value: FormDataEntryValue | undefined) =>
  String(value ?? "")
    .split(/\r?\n/)
    .map((url) => url.trim())
    .filter(Boolean);
export function productPath(storeId: number, productId: number) {
  return `/stores/${storeId}/products/${productId}`;
}
export function useIds() {
  const params = useParams();
  const storeId = Number(params.storeId);
  const productId = Number(params.productId);
  const valid =
    Number.isSafeInteger(storeId) &&
    storeId > 0 &&
    Number.isSafeInteger(productId) &&
    productId > 0;
  return valid ? { storeId, productId } : null;
}
export function ProductPage() {
  const ids = useIds();
  const workspace = useWorkspace(ids?.storeId ?? 0, ids?.productId ?? 0);
  if (!ids) return <InvalidPath />;
  return (
    <Page>
      <QueryState
        pending={workspace.isPending}
        error={workspace.error}
        retry={workspace.refetch}
      />
      {workspace.data && (
        <ProductView
          key={`${latestPlan(workspace.data)?.id ?? "none"}/${workspace.data.product.snapshotHash}`}
          workspace={workspace.data}
          refresh={() => void workspace.refetch()}
          refreshing={workspace.isFetching}
        />
      )}
    </Page>
  );
}
type Viewer = { owner: boolean; admin: boolean };
function useViewer(workspace: Workspace): Viewer {
  const session = useSession();
  return {
    // 시연·로그인 확인 전에는 소유자로 본다. 서버가 같은 검사를 다시 한다.
    owner: !session.data || session.data.id === workspace.store.ownerId,
    admin: session.data?.role === "admin",
  };
}
function ProductView({
  workspace,
  refresh,
  refreshing,
}: {
  workspace: Workspace;
  refresh: () => void;
  refreshing: boolean;
}) {
  const { store, product } = workspace;
  const phase = workspacePhase(workspace);
  const viewer = useViewer(workspace);
  const command = useCommand(store.id, product.id);
  const [error, setError] = useState<unknown>(null);
  const run = async (value: Command): Promise<boolean> => {
    setError(null);
    try {
      await command.run(value);
      return true;
    } catch (error) {
      setError(error);
      return false;
    }
  };
  const ctx: StepContext = {
    workspace,
    plan: latestPlan(workspace),
    viewer,
    busy: command.isPending || isRunning(workspace),
    pending: command.isPending,
    run,
  };
  return (
    <>
      <PageHeader
        back={{ to: `/stores/${store.id}`, label: store.name }}
        eyebrow={
          <>
            <PlatformMark platform={store.platform} size="1.75rem" />
            상품번호 {product.externalId}
          </>
        }
        title={product.name}
        actions={
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw aria-hidden="true" />}
            loading={refreshing}
            onClick={refresh}
          >
            최신 상태
          </Button>
        }
      >
        <Stepper
          label="상품 정비 단계"
          steps={productSteps}
          current={productStep(phase)}
          error={phaseIsError(phase)}
        />
      </PageHeader>
      <Split
        main={
          <>
            <ErrorMessage error={error} />
            <PhaseCard phase={phase} ctx={ctx} />
            {ctx.plan &&
              ctx.plan.changes.length > 0 &&
              !["questions", "review"].includes(phase) && (
                <PlanSummary ctx={ctx} plan={ctx.plan} />
              )}
          </>
        }
        aside={
          <>
            <FactsPanel workspace={workspace} />
            <ExposurePanel workspace={workspace} viewer={viewer} />
            <HistoryPanel workspace={workspace} />
            {viewer.owner && <AdvancedPanel ctx={ctx} />}
            <SourcePanel workspace={workspace} />
          </>
        }
      />
    </>
  );
}
type StepContext = {
  workspace: Workspace;
  plan: Plan | undefined;
  viewer: Viewer;
  busy: boolean;
  pending: boolean;
  run: (value: Command) => Promise<boolean>;
};
function Hero({
  emoji,
  tone,
  title,
  text,
  children,
}: {
  emoji: string;
  tone?: "blue" | "green" | "orange" | "red";
  title: ReactNode;
  text?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <Panel aria-label="지금 할 일">
      <div className={styles.hero}>
        <div className={styles.heroHead}>
          <span
            className={[styles.art, tone && styles[tone]]
              .filter(Boolean)
              .join(" ")}
            aria-hidden="true"
          >
            {emoji}
          </span>
          <div>
            <h2 className={styles.heroTitle}>{title}</h2>
            {text && <p className={styles.heroText}>{text}</p>}
          </div>
        </div>
        {children}
      </div>
    </Panel>
  );
}
function PhaseCard({ phase, ctx }: { phase: ProductPhase; ctx: StepContext }) {
  const { workspace, plan, viewer, busy, run } = ctx;
  const prepare = () => void run({ action: "prepare", sourceUrls: [] });
  const planLink = plan
    ? `${productPath(workspace.store.id, workspace.product.id)}/plans/${plan.id}`
    : "";
  switch (phase) {
    case "start":
      return (
        <Hero
          emoji="🔍"
          title="AI가 상품 정보를 조사할게요"
          text="상세페이지와 본문 속 공개 자료를 먼저 읽고, 필요한 정보만 여쭤봐요."
        >
          {viewer.owner ? (
            <StartForm ctx={ctx} />
          ) : (
            <Notice>판매자가 시작하면 AI가 조사해요.</Notice>
          )}
        </Hero>
      );
    case "preparing":
      return (
        <Hero
          emoji="🧠"
          tone="blue"
          title="AI가 정비안을 만들고 있어요"
          text="화면을 떠나도 계속 진행돼요."
        >
          <Timeline
            label="AI 준비 진행"
            items={[
              {
                key: "research",
                title: "상품 자료 조사",
                state: "current",
                busy: true,
              },
              { key: "needs", title: "필요한 정보 판단", state: "todo" },
              { key: "plan", title: "정비안 만들기", state: "todo" },
            ]}
          />
        </Hero>
      );
    case "prepare_failed":
      return (
        <Hero
          emoji="⚠️"
          tone="red"
          title="조사를 마치지 못했어요"
          text={jobMessage(workspace.product.prepareJob?.errorCode)}
        >
          {viewer.owner && (
            <div className={styles.actions}>
              <Button loading={ctx.pending} disabled={busy} onClick={prepare}>
                다시 조사하기
              </Button>
            </div>
          )}
        </Hero>
      );
    case "questions":
      return <QuestionsCard ctx={ctx} plan={plan!} />;
    case "review":
      return (
        <Hero
          emoji="📝"
          tone="blue"
          title="정비안이 준비됐어요"
          text={`${plan!.changes.length}개 항목을 바꿔요. 바뀌는 내용을 확인하고 승인해 주세요.`}
        >
          <ChangeChips plan={plan!} />
          <div className={styles.actions}>
            {viewer.owner ? (
              <ButtonLink
                to={planLink}
                size="lg"
                iconRight={<ArrowRight aria-hidden="true" />}
              >
                정비안 확인하기
              </ButtonLink>
            ) : (
              <ButtonLink to={planLink} variant="secondary">
                정비안 보기
              </ButtonLink>
            )}
          </div>
          {!viewer.owner && <Notice>판매자 승인을 기다려요.</Notice>}
        </Hero>
      );
    case "nothing":
      return (
        <Hero
          emoji="👌"
          title="지금 바꿀 내용이 없어요"
          text="공식 자료 주소를 주면 더 조사할 수 있어요."
        >
          {viewer.owner && <StartForm ctx={ctx} again />}
        </Hero>
      );
    case "waiting":
    case "manual":
      return viewer.admin && customerApproved(workspace, plan!) ? (
        <OperatorApply ctx={ctx} plan={plan!} />
      ) : (
        <Hero emoji="🛠️" tone="blue" title="seelo가 확인하고 반영할게요">
          <Timeline
            label="반영 진행"
            items={[
              { key: "approve", title: "승인", state: "done" },
              {
                key: "check",
                title: "seelo 확인",
                state: "current",
                busy: true,
              },
              { key: "apply", title: "쇼핑몰 반영", state: "todo" },
              { key: "public", title: "공개 페이지 확인", state: "todo" },
            ]}
          />
        </Hero>
      );
    case "applying":
      return (
        <Hero emoji="⏳" tone="blue" title="쇼핑몰에 반영하고 있어요">
          <Timeline
            label="반영 진행"
            items={[
              { key: "approve", title: "승인", state: "done" },
              { key: "check", title: "seelo 확인", state: "done" },
              {
                key: "apply",
                title: "쇼핑몰 반영",
                state: "current",
                busy: true,
              },
              { key: "public", title: "공개 페이지 확인", state: "todo" },
            ]}
          />
        </Hero>
      );
    case "check":
      return (
        <Hero
          emoji="🔎"
          tone="orange"
          title="반영 결과를 확인하고 있어요"
          text={
            plan?.job?.errorCode ? jobMessage(plan.job.errorCode) : undefined
          }
        >
          {viewer.admin && (
            <div className={styles.actions}>
              <Button
                loading={ctx.pending}
                onClick={() => void run({ action: "verify", planId: plan!.id })}
              >
                반영 결과 다시 확인
              </Button>
            </div>
          )}
        </Hero>
      );
    case "problem":
      return (
        <Hero
          emoji="⚠️"
          tone="red"
          title="쇼핑몰에 반영하지 못했어요"
          text={
            jobMessage(plan?.job?.errorCode) || "seelo가 원인을 확인할게요."
          }
        />
      );
    case "conflict":
      return <ConflictCard ctx={ctx} />;
    case "unpublished":
      return (
        <Hero
          emoji="✅"
          tone="green"
          title="쇼핑몰에 반영했어요"
          text="공개 페이지에 보이는지 확인하고 있어요."
        >
          {viewer.admin && <PublicationForm ctx={ctx} plan={plan!} />}
          {viewer.admin && <RollbackAction ctx={ctx} plan={plan!} />}
        </Hero>
      );
    case "published":
      return <PublishedCard ctx={ctx} plan={plan!} />;
    case "rolled_back":
      return (
        <Hero emoji="↩️" title="수정 전으로 되돌렸어요">
          {viewer.owner && (
            <div className={styles.actions}>
              <Button loading={ctx.pending} disabled={busy} onClick={prepare}>
                다시 정비하기
              </Button>
            </div>
          )}
          {viewer.admin && plan && <PublicationForm ctx={ctx} plan={plan} />}
        </Hero>
      );
  }
}
function StartForm({
  ctx,
  again = false,
}: {
  ctx: StepContext;
  again?: boolean;
}) {
  const active = ctx.workspace.plans.some((plan) =>
    ["approved", "applying", "pending_reflection", "uncertain"].includes(
      plan.status,
    ),
  );
  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        void ctx.run({
          action: "prepare",
          sourceUrls: sourceUrls(formValues(event.currentTarget).sourceUrls),
        });
      }}
    >
      <details className={styles.more} open={again}>
        <summary>공식 자료 주소 추가 (선택)</summary>
        <TextArea
          label="추가 공식 자료 주소 (한 줄에 하나·최대 3개)"
          name="sourceUrls"
          placeholder="https://제조사.com/제품"
        />
      </details>
      <div className={styles.actions}>
        <Button
          type="submit"
          size="lg"
          icon={<Sparkles aria-hidden="true" />}
          loading={ctx.pending}
          disabled={ctx.busy || active}
        >
          {again ? "다시 조사하기" : "AI가 조사하고 정비안 만들기"}
        </Button>
      </div>
    </form>
  );
}
function ChangeChips({ plan }: { plan: Plan }) {
  return (
    <ul className={styles.changeList} aria-label="바뀌는 항목">
      {plan.changes.map((change) => (
        <li key={change.field} className={styles.changeItem}>
          {fieldNames[change.field]}
          <Badge tone={change.method === "manual" ? "orange" : "blue"}>
            {methodLabels[change.method]}
          </Badge>
        </li>
      ))}
    </ul>
  );
}
function QuestionsCard({ ctx, plan }: { ctx: StepContext; plan: Plan }) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    // 답변을 저장하면 같은 기본 흐름으로 정비안을 다시 만든다.
    void ctx
      .run({
        action: "answers",
        answers: Object.fromEntries(
          Object.entries(values).filter(([, value]) => String(value).trim()),
        ),
      })
      .then((saved) => saved && ctx.run({ action: "prepare", sourceUrls: [] }));
  };
  return (
    <Hero
      emoji="💬"
      tone="orange"
      title={`${countWord(plan.questions.length)} 가지만 알려 주세요`}
      text="자료에서 확인하지 못한 정보예요. 답하면 정비안을 다시 만들어요."
    >
      {ctx.viewer.owner ? (
        <form className={styles.questions} onSubmit={submit}>
          {plan.questions.map((question, index) => (
            <div key={question.field} className={styles.question}>
              <span className={styles.qIndex}>질문 {index + 1}</span>
              <TextField
                label={question.text}
                name={question.field}
                maxLength={1000}
                placeholder={
                  ["nutrition", "serving"].includes(question.field)
                    ? "숫자와 단위를 함께 적어 주세요 (예: 30g)"
                    : undefined
                }
              />
            </div>
          ))}
          <div className={styles.actions}>
            <Button
              type="submit"
              size="lg"
              loading={ctx.pending}
              disabled={ctx.busy}
              icon={<MessageSquareText aria-hidden="true" />}
            >
              답변 저장
            </Button>
          </div>
        </form>
      ) : (
        <Notice>판매자 답변을 기다려요.</Notice>
      )}
    </Hero>
  );
}
function ConflictCard({ ctx }: { ctx: StepContext }) {
  const { workspace } = ctx;
  const importer = useImportProduct(workspace.store.id);
  const navigate = useNavigate();
  return (
    <Hero
      emoji="🔄"
      tone="red"
      title="상품 정보가 바뀌었어요"
      text="승인한 뒤 쇼핑몰에서 상품이 바뀌어 반영하지 않았어요. 다시 불러와 새로 정비해요."
    >
      <div className={styles.actions}>
        <Button
          loading={importer.isPending}
          onClick={() =>
            void importer
              .mutateAsync({ externalId: workspace.product.externalId })
              .then((result) => {
                if (result.kind === "job")
                  navigate(
                    `/stores/${workspace.store.id}?job=${result.job.id}`,
                  );
                else void ctx.run({ action: "prepare", sourceUrls: [] });
              })
              .catch(() => undefined)
          }
        >
          상품 다시 불러오기
        </Button>
      </div>
      <ErrorMessage error={importer.error} />
    </Hero>
  );
}
function PublishedCard({ ctx, plan }: { ctx: StepContext; plan: Plan }) {
  const runs = useMeasureRuns(ctx.workspace.product.id);
  const ready = reportPairs(runs.data ?? []).length > 0;
  const base = productPath(ctx.workspace.store.id, ctx.workspace.product.id);
  return (
    <Hero
      emoji="🎉"
      tone="green"
      title="반영을 마쳤어요"
      text={
        ready
          ? "정비 전후 AI 노출을 비교한 보고서가 준비됐어요."
          : `${when(plan.publication.checked_at)} 공개 페이지에서 확인했어요. 정비 후 측정이 끝나면 보고서를 보여 드려요.`
      }
    >
      <div className={styles.actions}>
        {ready && (
          <ButtonLink
            to={`${base}/report`}
            size="lg"
            icon={<FileText aria-hidden="true" />}
          >
            보고서 보기
          </ButtonLink>
        )}
      </div>
      {ctx.viewer.admin && <RollbackAction ctx={ctx} plan={plan} />}
    </Hero>
  );
}
function PlanSummary({ ctx, plan }: { ctx: StepContext; plan: Plan }) {
  const base = productPath(ctx.workspace.store.id, ctx.workspace.product.id);
  const fields =
    plan.approval?.fields ?? plan.changes.map((change) => change.field);
  return (
    <Panel
      title="이번 정비안"
      small
      action={
        <ButtonLink
          to={`${base}/plans/${plan.id}`}
          variant="secondary"
          size="sm"
        >
          자세히
        </ButtonLink>
      }
    >
      <ul className={styles.changeList}>
        {plan.changes
          .filter((change) => fields.includes(change.field))
          .map((change) => (
            <li key={change.field} className={styles.changeItem}>
              {fieldNames[change.field]}
              <Badge tone={planTones[plan.status]}>
                {planLabels[plan.status]}
              </Badge>
            </li>
          ))}
      </ul>
    </Panel>
  );
}
// 운영자: 판매자가 승인한 정비안을 확인하고 반영한다. 수동 항목은 직접 고친 뒤 기록한다.
function OperatorApply({ ctx, plan }: { ctx: StepContext; plan: Plan }) {
  const { workspace } = ctx;
  const changes = approvedChanges(plan);
  const manual = changes.some((change) => change.method === "manual");
  const base = productPath(workspace.store.id, workspace.product.id);
  const blocked =
    !manual &&
    (!workspace.store.automaticWritesEnabled ||
      workspace.product.automaticWritesEnabled === false);
  return (
    <Panel title="운영자 · 확인하고 반영" className={styles.operator}>
      <div className={styles.hero}>
        <p className={styles.muted}>
          판매자가 {when(plan.approvedAt)}에 {changes.length}개 항목을
          승인했어요.
        </p>
        <ul className={styles.changeList}>
          {changes.map((change) => (
            <li key={change.field} className={styles.changeItem}>
              {fieldNames[change.field]}
              <Badge tone={change.method === "manual" ? "orange" : "blue"}>
                {methodLabels[change.method]}
              </Badge>
            </li>
          ))}
        </ul>
        {blocked && (
          <Notice tone="warning" title="자동 수정이 꺼져 있어요">
            서버 설정(COMMERCE_WRITES_ENABLED·COMMERCE_WRITE_TARGETS)에서 이
            상품을 허용해야 반영할 수 있어요.
          </Notice>
        )}
        {plan.status === "manual_required" ? (
          <ManualForm ctx={ctx} plan={plan} />
        ) : (
          <div className={styles.actions}>
            <ButtonLink to={`${base}/plans/${plan.id}`} variant="secondary">
              바뀌는 내용 보기
            </ButtonLink>
            <Button
              loading={ctx.pending}
              disabled={ctx.busy || blocked}
              onClick={() => void ctx.run({ action: "apply", planId: plan.id })}
            >
              {manual ? "수동 편집 요청" : "승인한 변경 적용"}
            </Button>
          </div>
        )}
      </div>
    </Panel>
  );
}
function ManualForm({ ctx, plan }: { ctx: StepContext; plan: Plan }) {
  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        const values = formValues(event.currentTarget);
        if (values.confirmed !== "on") return;
        void ctx.run({
          action: "manual-result",
          planId: plan.id,
          values: Object.fromEntries(
            approvedChanges(plan).map((change) => [
              change.field,
              change.proposed,
            ]),
          ),
          note: String(values.note),
        });
      }}
    >
      <Checkbox
        name="confirmed"
        required
        label="관리 화면에 승인한 모든 값을 저장하고 재조회했습니다."
      />
      <TextArea label="작업 기록" name="note" required maxLength={1000} />
      <Button
        type="submit"
        loading={ctx.pending}
        disabled={ctx.busy || ctx.workspace.store.managerStatus !== "verified"}
      >
        수동 편집 결과 기록
      </Button>
    </form>
  );
}
function PublicationForm({ ctx, plan }: { ctx: StepContext; plan: Plan }) {
  return (
    <details className={styles.more} open>
      <summary>운영자 · 공개 페이지 확인 기록</summary>
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          const values = formValues(event.currentTarget);
          void ctx.run({
            action: "publication",
            planId: plan.id,
            pcUrl: String(values.pcUrl),
            mobileUrl: String(values.mobileUrl),
            pcMatches: values.pcMatches === "on",
            mobileMatches: values.mobileMatches === "on",
            note: String(values.note),
          });
        }}
      >
        <TextField label="PC 주소" name="pcUrl" type="url" required />
        <TextField label="모바일 주소" name="mobileUrl" type="url" required />
        <div>
          <Checkbox name="pcMatches" label="PC 값 일치" />
          <Checkbox name="mobileMatches" label="모바일 값 일치" />
        </div>
        <TextArea label="확인 기록" name="note" required maxLength={1000} />
        <Button type="submit" loading={ctx.pending} disabled={ctx.busy}>
          공개 반영 확인 기록
        </Button>
      </form>
    </details>
  );
}
export function RollbackAction({
  ctx,
  plan,
}: {
  ctx: Pick<StepContext, "workspace" | "pending" | "run">;
  plan: Plan;
}) {
  const [open, setOpen] = useState(false);
  if (plan.status !== "applied" || !customerApproved(ctx.workspace, plan))
    return null;
  return (
    <>
      <div className={styles.actions}>
        <TextButton onClick={() => setOpen(true)}>
          수정 전으로 되돌리기
        </TextButton>
      </div>
      <ConfirmDialog
        open={open}
        title="수정 전으로 되돌릴까요?"
        confirmLabel="원본 값 복구"
        danger
        busy={ctx.pending}
        onClose={() => setOpen(false)}
        onConfirm={() =>
          void ctx
            .run({ action: "rollback", planId: plan.id, confirmed: true })
            .then(() => setOpen(false))
        }
      >
        <p>
          승인한 {approvedChanges(plan).length}개 항목을 반영 전 값으로
          되돌려요. 그 뒤에 판매자가 같은 칸을 바꿨다면 되돌리지 않고 멈춰요.
        </p>
      </ConfirmDialog>
    </>
  );
}
function FactsPanel({ workspace }: { workspace: Workspace }) {
  const facts = workspace.product.facts;
  return (
    <Panel title="확인한 정보" small aria-label="확인한 정보">
      {facts.length ? (
        <ul className={styles.factList}>
          {facts.map((fact) => (
            <li key={fact.key} className={styles.fact}>
              <span className={styles.factLabel}>{factNames[fact.key]}</span>
              <span className={styles.factValue}>
                {fact.value}
                {fact.quantities?.length
                  ? ` (${fact.quantities.map((q) => `${q.amount}${q.unit}`).join(", ")})`
                  : ""}
              </span>
              {fact.source_url ? (
                <Chip
                  href={fact.source_url}
                  icon={<Link2 aria-hidden="true" />}
                  title={fact.source_url}
                >
                  {new URL(fact.source_url).hostname}
                </Chip>
              ) : (
                <Chip icon={<MessageSquareText aria-hidden="true" />}>
                  판매자 답변
                </Chip>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.muted}>AI가 조사하면 여기에 쌓여요.</p>
      )}
    </Panel>
  );
}
function ExposurePanel({
  workspace,
  viewer,
}: {
  workspace: Workspace;
  viewer: Viewer;
}) {
  const runs = useMeasureRuns(workspace.product.id);
  const base = productPath(workspace.store.id, workspace.product.id);
  const pairs = reportPairs(runs.data ?? []);
  const latest = ["openai", "gemini"]
    .map((provider) =>
      runs.data?.find(
        (run) =>
          run.condition.provider === provider &&
          ["completed", "partial"].includes(run.status),
      ),
    )
    .filter((run) => run !== undefined);
  const measuring = runs.data?.some((run) =>
    ["queued", "running"].includes(run.status),
  );
  return (
    <Panel
      title="AI 노출"
      small
      action={
        viewer.admin ? (
          <ButtonLink to={`${base}/measure`} variant="secondary" size="sm">
            측정 관리
          </ButtonLink>
        ) : undefined
      }
    >
      <div className={styles.metrics}>
        {measuring && (
          <Notice tone="progress">ChatGPT·Gemini에 묻는 중이에요</Notice>
        )}
        {latest.map((run) => (
          <MetricValue
            key={run.id}
            label={`${providerLabels[run.condition.provider]} · 상품 발견`}
            value={run.summary.totals.rates.identified}
            caption={`${run.planId ? "정비 후" : "정비 전"} · ${when(run.finishedAt)}`}
          />
        ))}
        {!latest.length && !measuring && (
          <p className={styles.muted}>
            seelo가 정비 전 측정을 준비하고 있어요.
          </p>
        )}
        {pairs.length > 0 && (
          <ButtonLink
            to={`${base}/report`}
            block
            icon={<FileText aria-hidden="true" />}
          >
            전후 보고서
          </ButtonLink>
        )}
      </div>
    </Panel>
  );
}
function HistoryPanel({ workspace }: { workspace: Workspace }) {
  if (workspace.plans.length === 0) return null;
  const base = productPath(workspace.store.id, workspace.product.id);
  const latestId = latestPlan(workspace)?.id;
  return (
    <Panel title="정비안 기록" small>
      <List label="정비안 이력">
        {workspace.plans.map((plan) => (
          <ListRow
            key={plan.id}
            to={`${base}/plans/${plan.id}`}
            title={`정비안 #${plan.id}`}
            sub={`${plan.changes.length}개 항목`}
            meta={
              plan.status === "draft" && plan.id !== latestId ? (
                <Badge>지난 초안</Badge>
              ) : (
                <Badge tone={planTones[plan.status]}>
                  {planLabels[plan.status]}
                </Badge>
              )
            }
          />
        ))}
      </List>
    </Panel>
  );
}
// 기본 흐름은 AI가 정한다. 근거를 직접 넣거나 정비 범위를 고르는 일은 접어 둔다.
function AdvancedPanel({ ctx }: { ctx: StepContext }) {
  const { workspace, busy, run } = ctx;
  const support = workspace.product.fieldSupport;
  const active = workspace.plans.some((plan) =>
    ["approved", "applying", "pending_reflection", "uncertain"].includes(
      plan.status,
    ),
  );
  const [error, setError] = useState<unknown>(null);
  return (
    <Panel small flat>
      <details className={styles.more}>
        <summary>직접 보완·범위 지정</summary>
        <div className={styles.moreBody}>
          <form
            className={styles.form}
            onSubmit={(event) => {
              event.preventDefault();
              void run({
                action: "research",
                sourceUrls: sourceUrls(
                  formValues(event.currentTarget).sourceUrls,
                ),
              });
            }}
          >
            <TextArea
              label="조사할 공식 자료 주소 (한 줄에 하나·최대 3개)"
              name="sourceUrls"
            />
            <Button type="submit" variant="secondary" disabled={busy}>
              자료 조사만 다시 실행
            </Button>
          </form>
          <form
            className={styles.form}
            onSubmit={(event) => {
              event.preventDefault();
              if (busy) return;
              setError(null);
              try {
                const fact = factInputSchema.parse({
                  ...formValues(event.currentTarget),
                  identity: workspace.product.identity,
                });
                void run({ action: "facts", facts: [fact] });
              } catch (error) {
                setError(error);
              }
            }}
          >
            <Select label="정보 종류" name="key">
              {Object.entries(factNames).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </Select>
            <TextField
              label="확인한 값"
              name="value"
              required
              maxLength={1000}
            />
            <TextField label="근거 주소" name="sourceUrl" type="url" required />
            <TextArea
              label="값이 포함된 인용문"
              name="quote"
              required
              maxLength={4000}
            />
            <ErrorMessage error={error} />
            <Button type="submit" variant="secondary" disabled={busy}>
              근거 저장
            </Button>
          </form>
          <form
            className={styles.form}
            onSubmit={(event) => {
              event.preventDefault();
              if (busy) return;
              const data = new FormData(event.currentTarget);
              setError(null);
              try {
                const input = generateSchema.parse({
                  fields: data.getAll("fields"),
                  requiredFacts: data.getAll("requiredFacts"),
                  useAi: data.get("useAi") === "on",
                  allowEditorConversion:
                    data.get("allowEditorConversion") === "on",
                });
                void run({ action: "generate", ...input });
              } catch (error) {
                setError(error);
              }
            }}
          >
            <fieldset className={styles.fieldset} disabled={busy || active}>
              <legend>변경할 필드</legend>
              {support.automatic.map((field) => (
                <Checkbox
                  key={field}
                  name="fields"
                  value={field}
                  defaultChecked={field === "description"}
                  label={fieldNames[field]}
                />
              ))}
              {support.manual.map((field) => (
                <Checkbox
                  key={field}
                  name="fields"
                  value={field}
                  label={`${fieldNames[field]} (운영자 직접 수정)`}
                />
              ))}
              {support.unavailable.map((item) => (
                <Checkbox
                  key={item.field}
                  disabled
                  label={`${fieldNames[item.field]} · ${unavailableReasons[item.reason] ?? item.reason}`}
                />
              ))}
            </fieldset>
            <fieldset className={styles.fieldset} disabled={busy || active}>
              <legend>자료에서 확인할 필수 사실</legend>
              {Object.entries(factNames).map(([key, label]) => (
                <Checkbox
                  key={key}
                  name="requiredFacts"
                  value={key}
                  label={label}
                />
              ))}
            </fieldset>
            <Checkbox
              name="useAi"
              defaultChecked
              disabled={busy || active}
              label="AI로 확인한 사실의 순서 정렬"
            />
            {support.conditions.description ===
              "editor_conversion_approval" && (
              <Checkbox
                name="allowEditorConversion"
                disabled={busy || active}
                label="상세설명 API 적용 시 HTML 형식 전환을 허용합니다."
              />
            )}
            <Button type="submit" variant="secondary" disabled={busy || active}>
              선택한 항목으로 정비안 생성
            </Button>
          </form>
        </div>
      </details>
    </Panel>
  );
}
function SourcePanel({ workspace }: { workspace: Workspace }) {
  const { product } = workspace;
  return (
    <Panel small flat>
      <details className={styles.more}>
        <summary>불러온 원본</summary>
        <div className={styles.moreBody}>
          <p className={styles.muted}>
            {sourceLabels[product.snapshotSource]} · {when(product.collectedAt)}
          </p>
          <p className={styles.muted}>모델·옵션: {product.identity}</p>
          {Object.entries(product.fields).map(([field, value]) => (
            <div key={field} style={{ display: "grid", gap: "0.4rem" }}>
              <span className={styles.factLabel}>
                {fieldNames[field as keyof typeof fieldNames] ?? field}
              </span>
              <div className={styles.source}>
                {readableText(value) || "비어 있음"}
              </div>
            </div>
          ))}
        </div>
      </details>
    </Panel>
  );
}
