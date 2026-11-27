import { useQueries } from "@tanstack/react-query";
import { ArrowRight, BriefcaseBusiness, Plus } from "lucide-react";
import {
  keys,
  useOperatorShops,
  useOperatorTasks,
  useStores,
} from "../app/commerce";
import { useRuntime, useSession } from "../app/runtime";
import { storeReady, summaryState } from "../commerce/progress";
import type { Product, Store } from "../commerce/schemas";
import { ButtonLink } from "../ui/Button";
import { Badge, EmptyState, Panel } from "../ui/Display";
import { CardGrid, Page, PageHeader, SectionTitle, Stack } from "../ui/Layout";
import { Card, CardTop, List, ListRow } from "../ui/List";
import { PlatformMark } from "../ui/AppShell";
import { QueryState } from "./common";
import styles from "./home.module.css";

type Todo = {
  key: string;
  emoji: string;
  title: string;
  sub: string;
  to: string;
  rank: number;
};
const productPath = (product: Product) =>
  `/stores/${product.shopId}/products/${product.id}`;
// 판매자 홈. 알림 대신 지금 해야 할 일을 행동 하나씩 카드로 모은다.
export function HomePage() {
  const runtime = useRuntime();
  const session = useSession();
  const stores = useStores();
  const ready = (stores.data ?? []).filter(storeReady);
  const products = useQueries({
    queries: ready.map((store) => ({
      queryKey: keys.products(store.id, { page: 1, query: "" }),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        runtime.gateway.products(store.id, { page: 1, query: "" }, signal),
    })),
  });
  const admin = session.data?.role === "admin";
  const storeName = (id: number) =>
    stores.data?.find((store) => store.id === id)?.name ?? "";
  const todos: Todo[] = [];
  const progress: {
    product: Product;
    label: string;
    tone: ReturnType<typeof summaryState>["tone"];
  }[] = [];
  for (const store of stores.data ?? []) {
    if (storeReady(store)) continue;
    if (store.editingMode === "browser" && store.managerStatus === "invited")
      continue;
    todos.push({
      key: `store-${store.id}`,
      emoji: "🔑",
      title:
        store.editingMode !== "browser"
          ? "API 연결을 마쳐 주세요"
          : store.managerStatus === "revoked"
            ? "연결이 끊겼어요. 다시 권한을 주세요"
            : "권한 위임을 마쳐 주세요",
      sub: store.name,
      to: `/stores/${store.id}`,
      rank: 0,
    });
  }
  for (const page of products) {
    for (const product of page.data?.items ?? []) {
      const state = summaryState(product);
      const sub = `${product.name} · ${storeName(product.shopId)}`;
      if (state.sellerAction === "answer")
        todos.push({
          key: `p-${product.id}`,
          emoji: "💬",
          title: `질문 ${product.summary?.questions ?? ""}개에 답해 주세요`,
          sub,
          to: productPath(product),
          rank: 1,
        });
      else if (state.sellerAction === "approve")
        todos.push({
          key: `p-${product.id}`,
          emoji: "📝",
          title: "정비안을 승인해 주세요",
          sub,
          to: `${productPath(product)}/plans/${product.summary?.planId}`,
          rank: 2,
        });
      else if (state.sellerAction === "report")
        todos.push({
          key: `p-${product.id}`,
          emoji: "📊",
          title: "보고서가 준비됐어요",
          sub,
          to: `${productPath(product)}/report`,
          rank: 3,
        });
      else if (state.sellerAction === "start")
        todos.push({
          key: `p-${product.id}`,
          emoji: "🔍",
          title:
            state.tone === "red"
              ? `${state.label} · 다시 시작해 주세요`
              : "AI 정비를 시작하세요",
          sub,
          to: productPath(product),
          rank: 4,
        });
      else progress.push({ product, label: state.label, tone: state.tone });
    }
  }
  todos.sort((a, b) => a.rank - b.rank);
  const waiting = (stores.data ?? []).filter(
    (store) =>
      store.editingMode === "browser" && store.managerStatus === "invited",
  );
  const loading = stores.isPending || products.some((query) => query.isPending);
  return (
    <Page>
      <PageHeader
        title="오늘 할 일"
        actions={
          stores.data?.length ? (
            <ButtonLink
              to="/stores/new"
              variant="secondary"
              icon={<Plus aria-hidden="true" />}
            >
              스토어 연결
            </ButtonLink>
          ) : undefined
        }
      />
      <QueryState
        pending={loading}
        error={stores.error}
        retry={stores.refetch}
        lines={2}
      />
      {admin && <OperatorShortcut />}
      {!loading && stores.data?.length === 0 && (
        <Panel>
          <EmptyState
            image="/images/stores-studio.webp"
            title="스토어를 연결하고 시작하세요"
            action={
              <ButtonLink to="/stores/new" size="lg">
                스토어 연결
              </ButtonLink>
            }
          >
            주소를 넣고 권한을 주면, AI가 상품 정보를 조사해 정비안을 만들어요.
          </EmptyState>
        </Panel>
      )}
      {!loading && !!stores.data?.length && (
        <Stack>
          {todos.length ? (
            <CardGrid label="지금 할 일">
              {todos.map((todo) => (
                <Card key={todo.key} to={todo.to}>
                  <CardTop>
                    <span className={styles.emoji} aria-hidden="true">
                      {todo.emoji}
                    </span>
                    <span className={styles.todoText}>
                      <strong>{todo.title}</strong>
                      <span>{todo.sub}</span>
                    </span>
                  </CardTop>
                  <span className={styles.go}>
                    바로 하기 <ArrowRight size={16} aria-hidden="true" />
                  </span>
                </Card>
              ))}
            </CardGrid>
          ) : (
            <Panel>
              <EmptyState emoji="☕" title="지금 할 일은 없어요">
                seelo가 진행하는 일은 아래에서 볼 수 있어요.
              </EmptyState>
            </Panel>
          )}
          {(progress.length > 0 || waiting.length > 0) && (
            <section aria-label="진행 중">
              <SectionTitle>진행 중</SectionTitle>
              <List label="진행 중 목록">
                {waiting.map((store: Store) => (
                  <ListRow
                    key={`s-${store.id}`}
                    to={`/stores/${store.id}`}
                    media={
                      <PlatformMark platform={store.platform} size="2.5rem" />
                    }
                    title={store.name}
                    sub="권한 확인"
                    meta={
                      <Badge tone="blue" dot>
                        확인 중
                      </Badge>
                    }
                  />
                ))}
                {progress.map(({ product, label, tone }) => (
                  <ListRow
                    key={product.id}
                    to={productPath(product)}
                    title={product.name}
                    sub={storeName(product.shopId)}
                    meta={
                      <Badge tone={tone} dot>
                        {label}
                      </Badge>
                    }
                  />
                ))}
              </List>
            </section>
          )}
        </Stack>
      )}
    </Page>
  );
}
function OperatorShortcut() {
  const tasks = useOperatorTasks(true);
  // 작업함과 같은 기준이다. 권한 확인 대기 스토어도 운영자가 할 일이다.
  const invited = useOperatorShops(
    { page: 1, query: "", managerStatus: "invited" },
    true,
  );
  const count =
    (tasks.data?.filter((task) => task.next !== "customer_approval").length ??
      0) + (invited.data?.total ?? 0);
  return (
    <div style={{ marginBottom: "1rem" }}>
      <Panel tight flat>
        <div className={styles.shortcut}>
          <span>
            <BriefcaseBusiness size={18} aria-hidden="true" /> 운영자 작업{" "}
            <b>{count}</b>건
          </span>
          <ButtonLink to="/operator" size="sm" variant="secondary">
            작업함 열기
          </ButtonLink>
        </div>
      </Panel>
    </div>
  );
}
