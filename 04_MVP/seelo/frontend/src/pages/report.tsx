import { useSearchParams } from "react-router-dom";
import { Printer } from "lucide-react";
import {
  useCompare,
  useMeasureRuns,
  useMeasureSets,
  useWorkspace,
} from "../app/commerce";
import { reportPairs } from "../commerce/report";
import { approvedChanges } from "../commerce/rules";
import {
  fieldNames,
  type MeasureRun,
  type MeasureSet,
  type Workspace,
} from "../commerce/schemas";
import { Button } from "../ui/Button";
import { EmptyState, Facts, Notice, Panel } from "../ui/Display";
import { DiffView } from "../ui/DiffView";
import { Page, PageHeader, Stack } from "../ui/Layout";
import { MetricCompare, MetricRows } from "../ui/Metric";
import { day, percent, providerLabels } from "../ui/labels";
import { InvalidPath, QueryState } from "./common";
import { productPath, useIds } from "./product";
import styles from "./report.module.css";

export function ReportPage() {
  const ids = useIds();
  const [params] = useSearchParams();
  const workspace = useWorkspace(ids?.storeId ?? 0, ids?.productId ?? 0);
  const runs = useMeasureRuns(ids?.productId ?? 0);
  const sets = useMeasureSets(ids?.productId ?? 0);
  if (!ids) return <InvalidPath />;
  const before = Number(params.get("before"));
  const after = Number(params.get("after"));
  const chosen =
    Number.isSafeInteger(before) &&
    before > 0 &&
    Number.isSafeInteger(after) &&
    after > 0
      ? (runs.data ?? []).filter((run) => run.id === before || run.id === after)
      : [];
  const pairs =
    chosen.length === 2
      ? [
          {
            key: "chosen",
            before: chosen.find((run) => run.id === before)!,
            after: chosen.find((run) => run.id === after)!,
          },
        ]
      : reportPairs(runs.data ?? []);
  const pending = workspace.isPending || runs.isPending;
  return (
    <Page width="medium" className={styles.report}>
      <PageHeader
        back={{
          to: `${productPath(ids.storeId, ids.productId)}?tab=exposure`,
          label: workspace.data?.product.name ?? "상품",
        }}
        eyebrow="AI 노출 전후 보고서"
        title={workspace.data?.product.name ?? "보고서"}
        description={
          pairs[0]
            ? `${day(pairs[0].before.finishedAt)} → ${day(pairs[0].after.finishedAt)}`
            : undefined
        }
        actions={
          pairs.length ? (
            <Button
              variant="secondary"
              size="sm"
              icon={<Printer aria-hidden="true" />}
              onClick={() => window.print()}
            >
              인쇄·PDF
            </Button>
          ) : undefined
        }
      />
      <QueryState
        pending={pending}
        error={workspace.error ?? runs.error}
        retry={() => {
          void workspace.refetch();
          void runs.refetch();
        }}
      />
      {!pending && workspace.data && pairs.length === 0 && (
        <Panel>
          <EmptyState
            emoji="📊"
            title="정비 후 측정이 끝나면 보고서가 만들어져요"
          >
            정비 전과 같은 질문을 같은 조건으로 다시 물어 비교해요.
          </EmptyState>
        </Panel>
      )}
      {workspace.data && pairs.length > 0 && (
        <Stack>
          <ReportSummary pairs={pairs} />
          {pairs.map((pair) => (
            <ProviderSection
              key={pair.key}
              before={pair.before}
              after={pair.after}
              set={sets.data?.find((set) => set.id === pair.after.setId)}
            />
          ))}
          <ChangesSection workspace={workspace.data} after={pairs[0].after} />
        </Stack>
      )}
    </Page>
  );
}
// 보고서 첫 줄. 공급자별 상품 발견 비율의 전후를 한 문장으로 말한다.
function ReportSummary({
  pairs,
}: {
  pairs: { key: string; before: MeasureRun; after: MeasureRun }[];
}) {
  const lines = pairs.map((pair) => {
    const before = pair.before.summary.totals.rates.identified;
    const after = pair.after.summary.totals.rates.identified;
    const name = providerLabels[pair.after.condition.provider];
    const verb =
      before === null || after === null
        ? "비교할 수 없어요"
        : after > before
          ? "로 늘었어요"
          : after < before
            ? "로 줄었어요"
            : "로 같아요";
    return before === null || after === null
      ? `${name}: 정상 응답이 부족해 ${verb}`
      : `${name} ${percent(before)} → ${percent(after)}${verb}`;
  });
  const up = pairs.some((pair) => {
    const before = pair.before.summary.totals.rates.identified;
    const after = pair.after.summary.totals.rates.identified;
    return before !== null && after !== null && after > before;
  });
  return (
    <div className={styles.summary} role="status">
      <strong>
        {up
          ? "정비 후 AI 답변에 내 상품이 더 자주 나와요"
          : "정비 전후 차이가 아직 크지 않아요"}
      </strong>
      <ul>
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <span>상품 발견: 같은 질문에 대한 답변에 내 상품이 나온 비율</span>
    </div>
  );
}
function ProviderSection({
  before,
  after,
  set,
}: {
  before: MeasureRun;
  after: MeasureRun;
  set?: MeasureSet;
}) {
  const compare = useCompare({ before: before.id, after: after.id });
  const provider = providerLabels[after.condition.provider];
  return (
    <Panel title={provider} aria-label={`${provider} 전후 비교`}>
      <QueryState
        pending={compare.isPending}
        error={compare.error}
        retry={compare.refetch}
        lines={1}
      />
      {compare.data && (
        <div className={styles.body}>
          {!compare.data.sameSnapshot && (
            <Notice tone="info">
              두 회차 사이에 상품 원본이 바뀌었습니다.
            </Notice>
          )}
          {/* 핵심 지표(상품 발견)만 크게, 나머지는 한 줄씩. 상품 화면의 AI 노출 탭과 같은 짜임이다. */}
          <div className={styles.metrics}>
            <MetricCompare
              label="상품 발견"
              before={compare.data.totals.before.rates.identified}
              after={compare.data.totals.after.rates.identified}
              caption={`답변에 내 상품이 나온 비율 · 정상 응답 ${compare.data.totals.before.valid} → ${compare.data.totals.after.valid}`}
            />
            <MetricRows
              rows={[
                {
                  key: "recommended",
                  label: "추천(상위 3)",
                  caption: "추천한 상위 3개에 든 비율",
                  before: compare.data.totals.before.rates.recommended,
                  value: compare.data.totals.after.rates.recommended,
                },
                {
                  key: "cited",
                  label: "상품 링크 인용",
                  caption: "내 상품 주소를 출처로 단 비율",
                  before: compare.data.totals.before.rates.cited,
                  value: compare.data.totals.after.rates.cited,
                },
              ]}
            />
          </div>
          {/* 질문마다 답변에 내 상품이 나온 횟수. 열은 정비 전·후 둘만 둔다. */}
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="전후 비교">
              <caption>
                질문별로 내 상품이 나온 횟수 (나온 횟수/정상 응답)
              </caption>
              <thead>
                <tr>
                  <th scope="col">질문</th>
                  <th scope="col">정비 전</th>
                  <th scope="col">정비 후</th>
                </tr>
              </thead>
              <tbody>
                {compare.data.queries.map((row) => {
                  const question = set?.queries.find(
                    (query) => query.id === row.queryId,
                  );
                  return (
                    <tr key={row.queryId}>
                      <th scope="row">
                        {question?.question ?? row.queryId}
                        {!row.comparable && (
                          <small className={styles.hold}>
                            정상 응답 부족·비교 보류
                          </small>
                        )}
                      </th>
                      <td>
                        {row.before.identified}/{row.before.valid}
                      </td>
                      <td className={styles.afterCell}>
                        {row.after.identified}/{row.after.valid}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Facts
            items={[
              ["모델", after.condition.model],
              ["반복", `질문마다 ${after.condition.repeats}회`],
              ["정비 전 회차", `${before.label} · ${day(before.finishedAt)}`],
              ["정비 후 회차", `${after.label} · ${day(after.finishedAt)}`],
            ]}
          />
        </div>
      )}
    </Panel>
  );
}
function ChangesSection({
  workspace,
  after,
}: {
  workspace: Workspace;
  after: MeasureRun;
}) {
  const plan = workspace.plans.find((item) => item.id === after.planId);
  if (!plan) return null;
  return (
    <Panel title="바뀐 내용">
      <div className={styles.body}>
        {approvedChanges(plan).map((change) => (
          <section
            key={change.field}
            className={styles.change}
            aria-label={fieldNames[change.field]}
          >
            <h3>{fieldNames[change.field]}</h3>
            <DiffView
              before={change.before}
              after={change.proposed}
              beforeLabel="정비 전"
              afterLabel="정비 후"
            />
          </section>
        ))}
        {plan.publication.checked_at && (
          <Facts
            items={[
              ["공개 페이지 확인", day(plan.publication.checked_at)],
              ["PC", plan.publication.pc_matches ? "일치" : "불일치"],
              ["모바일", plan.publication.mobile_matches ? "일치" : "불일치"],
            ]}
          />
        )}
      </div>
    </Panel>
  );
}
