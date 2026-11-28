import { type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Search } from "lucide-react";
import { useOperatorShops, useOperatorTasks } from "../app/commerce";
import { useSession } from "../app/runtime";
import {
  fieldNames,
  platformNames,
  type OperatorTask,
  type Store,
} from "../commerce/schemas";
import { Button } from "../ui/Button";
import { Badge, EmptyState, Notice, Panel } from "../ui/Display";
import { InlineForm, Select, TextField } from "../ui/Field";
import { Page, PageHeader, Stack } from "../ui/Layout";
import { List, ListRow } from "../ui/List";
import { Tabs } from "../ui/Overlay";
import { PlatformMark } from "../ui/AppShell";
import { managerLabels, managerTones, when } from "../ui/labels";
import { QueryState, formValues } from "./common";
import styles from "./operator.module.css";

const nextNames: Record<OperatorTask["next"], string> = {
  customer_approval: "고객 승인 대기",
  execute: "확인하고 반영",
  manual_edit: "직접 수정",
  check_result: "반영 결과 확인",
};
const statusFilter = (value: string | null) =>
  value && value in managerLabels
    ? (value as Store["managerStatus"])
    : undefined;
type TabKey = OperatorTask["next"] | "delegation" | "shops";
// 운영자 작업함. 운영자가 할 일을 종류별로 모은다. 고객 승인을 대신하지 않는다.
export function OperatorPage() {
  const session = useSession();
  const [params, setParams] = useSearchParams();
  const admin = session.data?.role === "admin";
  const candidate = Number(params.get("page"));
  const page = Number.isSafeInteger(candidate) && candidate > 0 ? candidate : 1;
  const query = (params.get("query") ?? "").slice(0, 200);
  const managerStatus = statusFilter(params.get("managerStatus"));
  const tab = (params.get("tab") as TabKey | null) ?? "execute";
  const shops = useOperatorShops({ page, query, managerStatus }, admin);
  const invitedShops = useOperatorShops(
    { page: 1, query: "", managerStatus: "invited" },
    admin,
  );
  const tasks = useOperatorTasks(admin);
  if (!admin)
    return (
      <Page width="medium">
        <PageHeader title="운영자" />
        <Notice tone="error">
          관리자 계정만 고객 스토어 목록을 볼 수 있습니다.
        </Notice>
      </Page>
    );
  const count = (next: OperatorTask["next"]) =>
    tasks.data?.filter((task) => task.next === next).length;
  const setTab = (key: string) => setParams({ tab: key });
  const search = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    const next: Record<string, string> = { tab: "shops", page: "1" };
    if (String(values.query ?? "").trim())
      next.query = String(values.query).trim();
    if (values.managerStatus) next.managerStatus = String(values.managerStatus);
    setParams(next);
  };
  const visible = (tasks.data ?? []).filter((task) => task.next === tab);
  return (
    <Page>
      <PageHeader
        title="운영 관리"
        description="고객이 승인한 범위만 실행합니다."
      />
      <Stack>
        <Tabs
          label="작업 종류"
          value={tab}
          onChange={setTab}
          items={[
            { key: "execute", label: "반영 대기", count: count("execute") },
            {
              key: "delegation",
              label: "권한 확인",
              count: invitedShops.data?.total,
            },
            {
              key: "manual_edit",
              label: "직접 수정",
              count: count("manual_edit"),
            },
            {
              key: "check_result",
              label: "결과 확인",
              count: count("check_result"),
            },
            {
              key: "customer_approval",
              label: "고객 승인 대기",
              count: count("customer_approval"),
            },
            { key: "shops", label: "고객 스토어" },
          ]}
        />
        {tab === "delegation" ? (
          <>
            <QueryState
              pending={invitedShops.isPending}
              error={invitedShops.error}
              retry={invitedShops.refetch}
              lines={2}
            />
            {invitedShops.data?.shops.length === 0 && (
              <Panel>
                <EmptyState emoji="✅" title="확인할 권한이 없어요" />
              </Panel>
            )}
            {!!invitedShops.data?.shops.length && (
              <List label="권한 확인 대기">
                {invitedShops.data.shops.map((shop) => (
                  <ListRow
                    key={shop.id}
                    to={`/stores/${shop.id}`}
                    media={
                      <PlatformMark platform={shop.platform} size="2.5rem" />
                    }
                    title={shop.name}
                    sub={`${shop.ownerEmail} · ${platformNames[shop.platform]} ${shop.externalId}`}
                    meta={
                      <Badge tone="blue" dot>
                        권한 확인
                      </Badge>
                    }
                  />
                ))}
              </List>
            )}
          </>
        ) : tab === "shops" ? (
          <ShopsTable
            shops={shops}
            query={query}
            managerStatus={managerStatus}
            page={page}
            onSearch={search}
            onPage={(value) =>
              setParams({
                ...Object.fromEntries(params),
                tab: "shops",
                page: String(value),
              })
            }
          />
        ) : (
          <>
            <QueryState
              pending={tasks.isPending}
              error={tasks.error}
              retry={tasks.refetch}
              lines={2}
            />
            {tasks.data && visible.length === 0 && (
              <Panel>
                <EmptyState emoji="✅" title="대기 중인 작업이 없습니다." />
              </Panel>
            )}
            {visible.length > 0 && (
              <List label="작업 대기 목록">
                {visible.map((task) => (
                  <ListRow
                    key={task.planId}
                    to={`/stores/${task.shopId}/products/${task.productId}`}
                    media={
                      <PlatformMark platform={task.platform} size="2.5rem" />
                    }
                    title={`${task.productName} · 정비안 #${task.planId}`}
                    sub={[
                      task.shopName,
                      task.ownerEmail,
                      task.approvedFields.length
                        ? `승인 항목 ${task.approvedFields.map((field) => fieldNames[field]).join(", ")}`
                        : "",
                      task.approvedAt ? when(task.approvedAt) : "",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                    meta={
                      task.next === "execute" && !task.customerApproved ? (
                        <Badge tone="red">고객 승인 기록 없음</Badge>
                      ) : (
                        <Badge
                          tone={
                            task.next === "customer_approval"
                              ? "neutral"
                              : "blue"
                          }
                          dot
                        >
                          {nextNames[task.next]}
                        </Badge>
                      )
                    }
                  />
                ))}
              </List>
            )}
          </>
        )}
      </Stack>
    </Page>
  );
}
function ShopsTable({
  shops,
  query,
  managerStatus,
  page,
  onSearch,
  onPage,
}: {
  shops: ReturnType<typeof useOperatorShops>;
  query: string;
  managerStatus?: Store["managerStatus"];
  page: number;
  onSearch: (event: FormEvent<HTMLFormElement>) => void;
  onPage: (page: number) => void;
}) {
  return (
    <Panel small>
      <form className={styles.search} onSubmit={onSearch} role="search">
        <TextField
          key={query}
          label="검색 (스토어·몰 ID·고객 이메일)"
          name="query"
          defaultValue={query}
          maxLength={200}
        />
        <Select
          key={managerStatus ?? "all"}
          label="관리자 권한"
          name="managerStatus"
          defaultValue={managerStatus ?? ""}
        >
          <option value="">전체</option>
          {Object.entries(managerLabels).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </Select>
        <InlineForm>
          <Button
            type="submit"
            size="lg"
            variant="secondary"
            icon={<Search aria-hidden="true" />}
          >
            조회
          </Button>
        </InlineForm>
      </form>
      <QueryState
        pending={shops.isPending}
        error={shops.error}
        retry={shops.refetch}
        lines={2}
      />
      {shops.data && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">스토어</th>
                <th scope="col">고객</th>
                <th scope="col">관리자 권한</th>
                <th scope="col">상품</th>
                <th scope="col">고객 승인 대기</th>
                <th scope="col">실행 대기</th>
                <th scope="col">수동 편집</th>
                <th scope="col">결과 확인</th>
              </tr>
            </thead>
            <tbody>
              {shops.data.shops.map((shop) => (
                <tr key={shop.id}>
                  <th scope="row">
                    <Link to={`/stores/${shop.id}`}>{shop.name}</Link>
                    <small>
                      {platformNames[shop.platform]} · {shop.externalId}
                      {shop.platform === "cafe24"
                        ? ` · 쇼핑몰 ${shop.shopNo}`
                        : ""}
                    </small>
                  </th>
                  <td>{shop.ownerEmail}</td>
                  <td>
                    <Badge tone={managerTones[shop.managerStatus]}>
                      {managerLabels[shop.managerStatus]}
                    </Badge>
                  </td>
                  <td>{shop.work.products}</td>
                  <td>{shop.work.customerApproval}</td>
                  <td>{shop.work.operatorExecute}</td>
                  <td>{shop.work.manualEdit}</td>
                  <td>{shop.work.checkResult}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {shops.data && shops.data.total > shops.data.pageSize && (
        <div className={styles.pager}>
          <Button
            variant="secondary"
            size="sm"
            disabled={page === 1}
            onClick={() => onPage(page - 1)}
          >
            이전
          </Button>
          <span>{page}페이지</span>
          <Button
            variant="secondary"
            size="sm"
            disabled={page * shops.data.pageSize >= shops.data.total}
            onClick={() => onPage(page + 1)}
          >
            다음
          </Button>
        </div>
      )}
    </Panel>
  );
}
