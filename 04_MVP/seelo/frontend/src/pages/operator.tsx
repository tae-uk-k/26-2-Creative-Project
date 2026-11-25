import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useOperatorShops, useOperatorTasks } from "../app/commerce";
import { useSession } from "../app/runtime";
import {
  fieldNames,
  platformNames,
  type OperatorTask,
  type Store,
} from "../commerce/schemas";
import { QueryState, formValues } from "./common";

const managerNames: Record<Store["managerStatus"], string> = {
  not_requested: "초대 전",
  invited: "초대 확인 대기",
  verified: "권한 확인됨",
  revoked: "권한 해제됨",
};
const nextNames: Record<OperatorTask["next"], string> = {
  customer_approval: "고객 승인 대기",
  execute: "운영자 실행 대기",
  manual_edit: "관리자 수동 편집 필요",
  check_result: "저장 결과 확인 필요",
};
const statusFilter = (value: string | null) =>
  value && value in managerNames
    ? (value as Store["managerStatus"])
    : undefined;

// 운영자용 고객 스토어·위임 확인·작업 대기. 조회만 하고 고객 승인을 대신하지 않는다.
export function OperatorPage() {
  const session = useSession();
  const [params, setParams] = useSearchParams();
  const admin = session.data?.role === "admin";
  const candidate = Number(params.get("page"));
  const page = Number.isSafeInteger(candidate) && candidate > 0 ? candidate : 1;
  const query = (params.get("query") ?? "").slice(0, 200);
  const managerStatus = statusFilter(params.get("managerStatus"));
  const shops = useOperatorShops({ page, query, managerStatus }, admin);
  const tasks = useOperatorTasks(admin);
  const [taskFilter, setTaskFilter] = useState<OperatorTask["next"] | "all">(
    "all",
  );
  if (!admin)
    return (
      <main>
        <h1>운영자</h1>
        <p role="alert">관리자 계정만 고객 스토어 목록을 볼 수 있습니다.</p>
      </main>
    );
  const search = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = formValues(event.currentTarget);
    const next: Record<string, string> = { page: "1" };
    if (String(values.query ?? "").trim())
      next.query = String(values.query).trim();
    if (values.managerStatus) next.managerStatus = String(values.managerStatus);
    setParams(next);
  };
  const visible = (tasks.data ?? []).filter(
    (task) => taskFilter === "all" || task.next === taskFilter,
  );
  return (
    <main>
      <h1>운영자 고객 업무</h1>
      <p>
        고객이 승인한 범위만 실행합니다. 정비안 승인은 고객 계정에서만
        가능합니다.
      </p>
      <h2>작업 대기</h2>
      <label>
        작업 종류
        <select
          value={taskFilter}
          onChange={(event) =>
            setTaskFilter(event.target.value as typeof taskFilter)
          }
        >
          <option value="all">전체</option>
          {Object.entries(nextNames).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <QueryState
        pending={tasks.isPending}
        error={tasks.error}
        retry={tasks.refetch}
      />
      <ul aria-label="작업 대기 목록">
        {visible.map((task) => (
          <li key={task.planId}>
            <Link
              to={`/stores/${task.shopId}/products/${task.productId}?plan=${task.planId}`}
            >
              {task.shopName} · {task.productName} · 정비안 #{task.planId}
            </Link>{" "}
            · {nextNames[task.next]} · {platformNames[task.platform]} ·{" "}
            {task.ownerEmail}
            {task.next === "execute" && !task.customerApproved
              ? " · 고객 승인 기록 없음(실행 불가)"
              : ""}
            {task.approvedFields.length > 0 &&
              ` · 승인 항목: ${task.approvedFields.map((field) => fieldNames[field]).join(", ")}`}
          </li>
        ))}
      </ul>
      {tasks.data && visible.length === 0 && <p>대기 중인 작업이 없습니다.</p>}
      <h2>고객 스토어</h2>
      {shops.data && shops.data.invited > 0 && (
        <p role="status">초대 확인 대기 {shops.data.invited}건</p>
      )}
      <form onSubmit={search}>
        <label>
          검색 (스토어·몰 ID·고객 이메일)
          <input
            key={query}
            name="query"
            defaultValue={query}
            maxLength={200}
          />
        </label>
        <label>
          관리자 권한
          <select
            key={managerStatus ?? "all"}
            name="managerStatus"
            defaultValue={managerStatus ?? ""}
          >
            <option value="">전체</option>
            {Object.entries(managerNames).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button>조회</button>
      </form>
      <QueryState
        pending={shops.isPending}
        error={shops.error}
        retry={shops.refetch}
      />
      <table>
        <thead>
          <tr>
            <th>스토어</th>
            <th>고객</th>
            <th>관리자 권한</th>
            <th>상품</th>
            <th>고객 승인 대기</th>
            <th>실행 대기</th>
            <th>수동 편집</th>
            <th>결과 확인</th>
          </tr>
        </thead>
        <tbody>
          {shops.data?.shops.map((shop) => (
            <tr key={shop.id}>
              <th>
                <Link to={`/stores/${shop.id}/products`}>{shop.name}</Link> (
                {platformNames[shop.platform]} · {shop.externalId}
                {shop.platform === "cafe24" ? ` · 쇼핑몰 ${shop.shopNo}` : ""})
              </th>
              <td>{shop.ownerEmail}</td>
              <td>{managerNames[shop.managerStatus]}</td>
              <td>{shop.work.products}</td>
              <td>{shop.work.customerApproval}</td>
              <td>{shop.work.operatorExecute}</td>
              <td>{shop.work.manualEdit}</td>
              <td>{shop.work.checkResult}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        disabled={page === 1}
        onClick={() =>
          setParams({ ...Object.fromEntries(params), page: String(page - 1) })
        }
      >
        이전
      </button>
      <span> {page}페이지 </span>
      <button
        disabled={!shops.data || page * shops.data.pageSize >= shops.data.total}
        onClick={() =>
          setParams({ ...Object.fromEntries(params), page: String(page + 1) })
        }
      >
        다음
      </button>
    </main>
  );
}
