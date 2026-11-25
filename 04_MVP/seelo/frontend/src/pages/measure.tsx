import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRuntime } from "../app/runtime";
import type { MeasureRun } from "../commerce/schemas";
import { ErrorMessage, QueryState, formValues } from "./common";

const runStatuses: Record<MeasureRun["status"], string> = {
  queued: "대기",
  running: "측정 중",
  completed: "완료",
  partial: "일부 무효",
  failed: "모두 무효",
};
const percent = (value: number | null) =>
  value === null ? "판정 불가" : `${Math.round(value * 100)}%`;

// "ID | 질문" 또는 "ID | 질문군 | 질문" 형식의 줄을 고정 질문으로 읽는다.
function parseQueries(text: string) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split("|").map((part) => part.trim());
      return parts.length >= 3
        ? { id: parts[0], family: parts[1], question: parts.slice(2).join("|") }
        : { id: parts[0], question: parts.slice(1).join("|") };
    });
}
const lines = (value: FormDataEntryValue | undefined) =>
  String(value ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

// 쇼핑몰 AI 노출 진단. 같은 질문 세트·측정 조건으로 정비 전후를 비교한다.
export function MeasureSection({ productId }: { productId: number }) {
  const runtime = useRuntime();
  const sets = useQuery({
    queryKey: ["commerce", "measure-sets", productId] as const,
    queryFn: ({ signal }) => runtime.gateway.measureSets(productId, signal),
  });
  const runs = useQuery({
    queryKey: ["commerce", "measure-runs", productId] as const,
    queryFn: ({ signal }) => runtime.gateway.measureRuns(productId, signal),
    refetchInterval: (query) =>
      query.state.data?.some((run) =>
        ["queued", "running"].includes(run.status),
      )
        ? 5000
        : false,
  });
  const [compare, setCompare] = useState<{ before: number; after: number }>();
  const compared = useQuery({
    queryKey: ["commerce", "measure-compare", compare] as const,
    queryFn: ({ signal }) =>
      runtime.gateway.compareRuns(compare!.before, compare!.after, signal),
    enabled: compare !== undefined,
    retry: false,
  });
  const refresh = () =>
    Promise.all([
      runtime.queryClient.invalidateQueries({
        queryKey: ["commerce", "measure-sets", productId],
      }),
      runtime.queryClient.invalidateQueries({
        queryKey: ["commerce", "measure-runs", productId],
      }),
    ]);
  const createSet = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const values = formValues(form);
      return runtime.gateway.createMeasureSet(productId, {
        name: String(values.name),
        queries: parseQueries(String(values.queries ?? "")),
        targetNames: lines(values.targetNames),
        targetUrls: lines(values.targetUrls),
      });
    },
    onSuccess: refresh,
  });
  const start = useMutation({
    mutationFn: ({ setId, form }: { setId: number; form: HTMLFormElement }) => {
      const values = formValues(form);
      return runtime.gateway.runMeasure(setId, {
        label: String(values.label),
        provider: values.provider === "gemini" ? "gemini" : "openai",
        repeats: Number(values.repeats),
      });
    },
    onSuccess: refresh,
  });
  const submit =
    (handler: (form: HTMLFormElement) => void) =>
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      handler(event.currentTarget);
    };
  return (
    <section aria-label="AI 노출 진단">
      <h2>AI 노출 진단</h2>
      <p>
        고정 질문을 질문마다 새 요청으로 실행하고 원문·출처·발견·추천 순위를
        저장합니다. 호출 실패는 노출 0이 아니라 무효로 표시합니다. 같은 질문
        세트·측정 조건의 회차끼리만 비교합니다.
      </p>
      <QueryState
        pending={sets.isPending}
        error={sets.error}
        retry={sets.refetch}
      />
      {sets.data?.map((set) => (
        <article key={set.id} aria-label={`질문 세트 ${set.name}`}>
          <h3>
            질문 세트: {set.name} ({set.queries.length}문항)
          </h3>
          <p>
            대상 식별: {[...set.targets.names, ...set.targets.urls].join(", ")}
          </p>
          <form
            onSubmit={submit((form) => start.mutate({ setId: set.id, form }))}
          >
            <label>
              회차 이름
              <input name="label" required defaultValue="B0" maxLength={20} />
            </label>
            <label>
              AI
              <select name="provider" defaultValue="openai">
                <option value="openai">ChatGPT(OpenAI)</option>
                <option value="gemini">Gemini</option>
              </select>
            </label>
            <label>
              반복
              <input
                name="repeats"
                type="number"
                min={1}
                max={5}
                defaultValue={3}
              />
            </label>
            <button disabled={start.isPending}>측정 시작</button>
          </form>
        </article>
      ))}
      <ErrorMessage error={start.error} />
      <details open={sets.data?.length === 0}>
        <summary>새 질문 세트</summary>
        <form onSubmit={submit((form) => createSet.mutate(form))}>
          <label>
            세트 이름
            <input name="name" required maxLength={100} />
          </label>
          <label>
            고정 질문 (한 줄에 "ID | 질문" 또는 "ID | 질문군 | 질문")
            <textarea name="queries" required />
          </label>
          <label>
            대상 상품명 (한 줄에 하나, 비우면 등록된 상품명)
            <textarea name="targetNames" />
          </label>
          <label>
            대상 공개 상품 주소 (한 줄에 하나)
            <textarea name="targetUrls" />
          </label>
          <button disabled={createSet.isPending}>질문 세트 만들기</button>
        </form>
        <ErrorMessage error={createSet.error} />
      </details>
      <h3>측정 회차</h3>
      <QueryState
        pending={runs.isPending}
        error={runs.error}
        retry={runs.refetch}
      />
      <table aria-label="측정 회차">
        <thead>
          <tr>
            <th>회차</th>
            <th>AI·모델</th>
            <th>상태</th>
            <th>정상/계획</th>
            <th>무효</th>
            <th>발견</th>
            <th>추천(상위 3)</th>
            <th>상품 링크 인용</th>
          </tr>
        </thead>
        <tbody>
          {runs.data?.map((run) => (
            <tr key={run.id}>
              <th>
                #{run.id} {run.label}
              </th>
              <td>
                {run.condition.provider} · {run.condition.model}
              </td>
              <td>{runStatuses[run.status]}</td>
              <td>
                {run.summary.totals.valid}/{run.summary.totals.planned}
              </td>
              <td>{run.summary.totals.missing}</td>
              <td>
                {run.summary.totals.identified} (
                {percent(run.summary.totals.rates.identified)})
              </td>
              <td>
                {run.summary.totals.recommended} (
                {percent(run.summary.totals.rates.recommended)})
              </td>
              <td>
                {run.summary.totals.cited} (
                {percent(run.summary.totals.rates.cited)})
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {runs.data && runs.data.length >= 2 && (
        <form
          onSubmit={submit((form) => {
            const values = formValues(form);
            setCompare({
              before: Number(values.before),
              after: Number(values.after),
            });
          })}
        >
          <label>
            정비 전 회차
            <select name="before" defaultValue={runs.data.at(-1)!.id}>
              {runs.data.map((run) => (
                <option key={run.id} value={run.id}>
                  #{run.id} {run.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            정비 후 회차
            <select name="after" defaultValue={runs.data[0].id}>
              {runs.data.map((run) => (
                <option key={run.id} value={run.id}>
                  #{run.id} {run.label}
                </option>
              ))}
            </select>
          </label>
          <button>전후 비교</button>
        </form>
      )}
      <ErrorMessage error={compared.error} />
      {compared.data && (
        <table aria-label="전후 비교">
          <thead>
            <tr>
              <th>질문</th>
              <th>전: 발견/정상</th>
              <th>후: 발견/정상</th>
              <th>전: 추천</th>
              <th>후: 추천</th>
            </tr>
          </thead>
          <tbody>
            {compared.data.queries.map((row) => (
              <tr key={row.queryId}>
                <th>
                  {row.queryId}
                  {row.comparable ? "" : " (정상 응답 부족·비교 보류)"}
                </th>
                <td>
                  {row.before.identified}/{row.before.valid}
                </td>
                <td>
                  {row.after.identified}/{row.after.valid}
                </td>
                <td>{row.before.recommended}</td>
                <td>{row.after.recommended}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {compared.data && !compared.data.sameSnapshot && (
        <p>두 회차 사이에 상품 원본이 바뀌었습니다.</p>
      )}
    </section>
  );
}
