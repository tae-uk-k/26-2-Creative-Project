import { useQueries } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ChevronRight, FileText, FlaskConical } from "lucide-react";
import {
  keys,
  useMeasureRuns,
  useMeasureRunsMany,
  useStores,
} from "../app/commerce";
import { useRuntime } from "../app/runtime";
import {
  productExposure,
  type ProductExposure,
  type ProviderExposure,
} from "../commerce/exposure";
import { storeReady } from "../commerce/progress";
import type {
  MeasureRun,
  Product,
  ProductPage as ProductList,
  Store,
  Workspace,
} from "../commerce/schemas";
import { ButtonLink } from "../ui/Button";
import { EmptyState, Notice, Panel } from "../ui/Display";
import { Page, PageHeader, Stack } from "../ui/Layout";
import { MetricCompare, MetricRows, MetricValue } from "../ui/Metric";
import { PlatformMark } from "../ui/AppShell";
import { day, percent, providerLabels } from "../ui/labels";
import { QueryState } from "./common";
import styles from "./exposure.module.css";

const productLink = (product: Product) =>
  `/stores/${product.shopId}/products/${product.id}`;
// 요약이 없으면(이전 서버) 측정 여부를 알 수 없으므로 회차를 조회한다.
const maybeMeasured = (product: Product) =>
  !product.summary || product.summary.measure.runs > 0;
const empty = productExposure([]);

// 판매자 메뉴의 AI 노출. 상품마다 숫자 하나만 보여 주고, 자세한 내용은 상품을 눌러 본다.
export function ExposurePage() {
  const runtime = useRuntime();
  const stores = useStores();
  const ready = (stores.data ?? []).filter(storeReady);
  const pages = useQueries({
    queries: ready.map((store) => ({
      queryKey: keys.products(store.id, { page: 1, query: "" }),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        runtime.gateway.products(store.id, { page: 1, query: "" }, signal),
    })),
  });
  const products = pages.flatMap((page) => page.data?.items ?? []);
  const exposures = useExposures(products);
  const loading =
    stores.isPending ||
    pages.some((page) => page.isPending) ||
    exposures.pending;
  return (
    <Page width="medium">
      <PageHeader
        title="AI 노출"
        description="고객이 물을 만한 질문을 ChatGPT·Gemini에 했을 때, 답변에 내 상품이 나온 비율이에요."
      />
      <QueryState
        pending={loading}
        error={stores.error ?? pages.find((page) => page.error)?.error}
        retry={() => {
          void stores.refetch();
          pages.forEach((page) => void page.refetch());
        }}
        lines={3}
      />
      {!loading && ready.length === 0 && (
        <Panel>
          <EmptyState
            emoji="📡"
            title="연결을 마친 스토어가 없어요"
            action={
              <ButtonLink to="/stores" size="lg">
                스토어 보기
              </ButtonLink>
            }
          >
            스토어 연결을 마치고 상품을 불러오면 여기에서 볼 수 있어요.
          </EmptyState>
        </Panel>
      )}
      {!loading && ready.length > 0 && (
        <Stack>
          <Summary exposures={[...exposures.byId.values()]} />
          {ready.map((store, index) => (
            <StoreGroup
              key={store.id}
              store={store}
              page={pages[index]?.data}
              exposures={exposures.byId}
              single={ready.length === 1}
            />
          ))}
        </Stack>
      )}
    </Page>
  );
}
function useExposures(products: Product[]) {
  const ids = products.filter(maybeMeasured).map((product) => product.id);
  const runs = useMeasureRunsMany(ids);
  const byId = new Map<number, ProductExposure>();
  ids.forEach((id, index) => {
    const data = runs[index]?.data;
    if (data) byId.set(id, productExposure(data));
  });
  return { byId, pending: runs.some((query) => query.isPending) };
}
// 숫자 여러 개 대신 지금 상태를 한 문장으로 말한다.
function Summary({ exposures }: { exposures: ProductExposure[] }) {
  const measured = exposures.filter((value) => value.measured).length;
  const compared = exposures.filter((value) => value.report).length;
  const improved = exposures.filter((value) => value.improved).length;
  const [title, text] =
    measured === 0
      ? [
          "아직 측정한 상품이 없어요",
          "seelo가 정비 전에 한 번, 정비를 반영한 뒤에 한 번 측정해요.",
        ]
      : compared === 0
        ? [
            `${measured}개 상품의 정비 전 측정을 마쳤어요`,
            "정비를 반영하면 같은 질문으로 다시 측정해 비교해요.",
          ]
        : improved > 0
          ? [
              `${improved}개 상품이 AI 답변에 더 자주 나와요`,
              `정비 전후를 비교한 상품 ${compared}개 기준이에요.`,
            ]
          : [
              "정비 전후 차이가 아직 없어요",
              `정비 전후를 비교한 상품 ${compared}개 기준이에요.`,
            ];
  return (
    <div className={styles.summary} role="status">
      <strong>{title}</strong>
      <span>{text}</span>
    </div>
  );
}
function StoreGroup({
  store,
  page,
  exposures,
  single,
}: {
  store: Store;
  page?: ProductList;
  exposures: Map<number, ProductExposure>;
  single: boolean;
}) {
  if (!page) return null;
  return (
    <section aria-label={`${store.name} AI 노출`} className={styles.group}>
      {!single && (
        <h2 className={styles.storeTitle}>
          <PlatformMark platform={store.platform} size="1.5rem" />
          {store.name}
        </h2>
      )}
      {page.items.length === 0 ? (
        <Panel>
          <EmptyState emoji="📦" title="아직 불러온 상품이 없어요" />
        </Panel>
      ) : (
        <ul className={styles.list} aria-label={`${store.name} 상품별 노출`}>
          <li className={styles.head} aria-hidden="true">
            <span>상품</span>
            <span>ChatGPT</span>
            <span>Gemini</span>
          </li>
          {page.items.map((product) => (
            <ExposureRow
              key={product.id}
              product={product}
              exposure={exposures.get(product.id) ?? empty}
            />
          ))}
        </ul>
      )}
      {page.total > page.items.length && (
        <p className={styles.more}>
          처음 {page.items.length}개 상품만 보여요. 나머지는{" "}
          <Link to={`/stores/${store.id}`}>스토어</Link>에서 상품을 찾아 열어
          주세요.
        </p>
      )}
    </section>
  );
}
function rowNote(exposure: ProductExposure) {
  if (exposure.measuring) return "측정하고 있어요";
  const run = exposure.providers.find((item) => item.after)?.after;
  if (run) return `정비 후 ${day(run.finishedAt)} 측정`;
  const latest = exposure.providers.find((item) => item.latest)?.latest;
  return latest ? `정비 전 ${day(latest.finishedAt)} 측정` : null;
}
function ExposureRow({
  product,
  exposure,
}: {
  product: Product;
  exposure: ProductExposure;
}) {
  const note = rowNote(exposure);
  return (
    <li>
      <Link className={styles.row} to={`${productLink(product)}?tab=exposure`}>
        <span className={styles.name}>
          <strong>{product.name}</strong>
          {note && <span>{note}</span>}
        </span>
        {exposure.measured ? (
          exposure.providers.map((item) => (
            <ProviderValue key={item.provider} item={item} />
          ))
        ) : (
          <span className={styles.pending}>
            {exposure.measuring ? "측정 중" : "측정 전"}
          </span>
        )}
        <ChevronRight className={styles.chevron} aria-hidden="true" />
      </Link>
    </li>
  );
}
// 공급자 하나의 상품 발견 비율. 전후 짝이 있으면 정비 후 값과 변화를, 없으면 최근 값을 보여 준다.
function ProviderValue({ item }: { item: ProviderExposure }) {
  const label = providerLabels[item.provider];
  const before = item.before?.summary.totals.rates.identified ?? null;
  const after = item.after?.summary.totals.rates.identified ?? null;
  const run = item.after ?? item.latest;
  const change =
    item.before && before !== null && after !== null
      ? Math.round((after - before) * 100)
      : null;
  return (
    <span className={styles.value}>
      <span className={styles.cellLabel}>{label}</span>
      <span className={run ? styles.number : styles.none}>
        {run ? percent(run.summary.totals.rates.identified) : "-"}
      </span>
      {change !== null && (
        <span
          className={[
            styles.delta,
            change > 0 ? styles.up : change < 0 ? styles.down : "",
          ].join(" ")}
        >
          {change > 0
            ? `+${change}%p`
            : change < 0
              ? `${change}%p`
              : "변화 없음"}
        </span>
      )}
    </span>
  );
}
const rates = [
  ["identified", "상품 발견", "답변에 내 상품이 나온 비율"],
  ["recommended", "추천(상위 3)", "추천한 상위 3개에 든 비율"],
  ["cited", "상품 링크 인용", "내 상품 주소를 출처로 단 비율"],
] as const;
// 상품 화면의 AI 노출 탭. 운영자에게만 측정 관리로 가는 길을 둔다.
export function ProductExposure({
  workspace,
  admin,
}: {
  workspace: Workspace;
  admin: boolean;
}) {
  const runs = useMeasureRuns(workspace.product.id);
  const base = productLink(workspace.product);
  const exposure = productExposure(runs.data ?? []);
  const measureLink = admin ? (
    <ButtonLink
      to={`${base}/measure`}
      variant="secondary"
      size="lg"
      icon={<FlaskConical aria-hidden="true" />}
    >
      측정 관리
    </ButtonLink>
  ) : null;
  return (
    <Stack>
      <QueryState
        pending={runs.isPending}
        error={runs.error}
        retry={runs.refetch}
        lines={2}
      />
      {runs.data && (
        <>
          {exposure.measuring && (
            <Notice tone="progress">ChatGPT·Gemini에 묻는 중이에요</Notice>
          )}
          {!exposure.measured && !exposure.measuring ? (
            <Panel>
              <EmptyState
                emoji="📊"
                title="아직 측정한 결과가 없어요"
                action={measureLink ?? undefined}
              >
                {admin
                  ? "질문 세트를 만들고 정비 전 측정을 시작하세요."
                  : "seelo가 정비 전에 한 번, 반영한 뒤에 한 번 측정해요."}
              </EmptyState>
            </Panel>
          ) : (
            <>
              <div className={styles.providers}>
                {exposure.providers.map((item) => (
                  <ProviderPanel key={item.provider} item={item} />
                ))}
              </div>
              <div className={styles.actions}>
                {exposure.report && (
                  <ButtonLink
                    to={`${base}/report`}
                    size="lg"
                    icon={<FileText aria-hidden="true" />}
                  >
                    전후 보고서 보기
                  </ButtonLink>
                )}
                {measureLink}
              </div>
            </>
          )}
        </>
      )}
    </Stack>
  );
}
function ProviderPanel({ item }: { item: ProviderExposure }) {
  const label = providerLabels[item.provider];
  const period = (run: MeasureRun) =>
    `${run.planId === null ? "정비 전" : "정비 후"} ${day(run.finishedAt)}`;
  return (
    <Panel
      title={label}
      small
      aria-label={`${label} 노출`}
      action={
        item.before && item.after ? (
          <span className={styles.period}>
            {day(item.before.finishedAt)} → {day(item.after.finishedAt)}
          </span>
        ) : item.latest ? (
          <span className={styles.period}>{period(item.latest)}</span>
        ) : undefined
      }
    >
      {item.before || item.latest ? (
        <div className={styles.detail}>
          {/* 핵심 지표 하나만 크게 보여 주고 나머지 둘은 한 줄씩 둔다. */}
          {item.before && item.after ? (
            <MetricCompare
              label={rates[0][1]}
              before={item.before.summary.totals.rates.identified}
              after={item.after.summary.totals.rates.identified}
              caption={rates[0][2]}
            />
          ) : (
            <MetricValue
              label={rates[0][1]}
              value={item.latest!.summary.totals.rates.identified}
              caption={rates[0][2]}
            />
          )}
          <MetricRows
            rows={rates.slice(1).map(([key, name, caption]) => ({
              key,
              label: name,
              caption,
              value: (item.after ?? item.latest)!.summary.totals.rates[key],
              ...(item.after && item.before
                ? { before: item.before.summary.totals.rates[key] }
                : {}),
            }))}
          />
        </div>
      ) : (
        <p className={styles.muted}>아직 측정하지 않았어요.</p>
      )}
    </Panel>
  );
}
