import { type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { FileText, Play, Plus } from "lucide-react";
import {
  measureKeys,
  useMeasureRuns,
  useMeasureSets,
  useWorkspace,
} from "../app/commerce";
import { useRuntime, useSession } from "../app/runtime";
import type { MeasureRun, MeasureSet } from "../commerce/schemas";
import { Button } from "../ui/Button";
import { Badge, Chip, EmptyState, Notice, Panel } from "../ui/Display";
import { Select, TextArea, TextField } from "../ui/Field";
import { Page, PageHeader, Stack } from "../ui/Layout";
import {
  percent,
  providerLabels,
  runLabels,
  runTones,
  when,
} from "../ui/labels";
import { ErrorMessage, InvalidPath, QueryState, formValues } from "./common";
import { productPath, useIds } from "./product";
import styles from "./measure.module.css";

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
// 운영자 전용. 같은 질문을 ChatGPT·Gemini에 여러 번 묻고 정비 전후를 같은 조건으로 비교한다.
export function MeasurePage() {
  const ids = useIds();
  const session = useSession();
  const workspace = useWorkspace(ids?.storeId ?? 0, ids?.productId ?? 0);
  if (!ids) return <InvalidPath />;
  const back = productPath(ids.storeId, ids.productId);
  return (
    <Page>
      <PageHeader
        back={{
          to: `${back}?tab=exposure`,
          label: workspace.data?.product.name ?? "상품",
        }}
        eyebrow="운영 관리"
        title="AI 노출 측정"
      />
      {session.data && session.data.role !== "admin" ? (
        <Notice tone="error">운영자 계정만 측정을 관리할 수 있어요.</Notice>
      ) : (
        <MeasureConsole productId={ids.productId} back={back} />
      )}
    </Page>
  );
}
function MeasureConsole({
  productId,
  back,
}: {
  productId: number;
  back: string;
}) {
  const runtime = useRuntime();
  const sets = useMeasureSets(productId);
  const runs = useMeasureRuns(productId);
  const refresh = () =>
    Promise.all([
      runtime.queryClient.invalidateQueries({
        queryKey: measureKeys.sets(productId),
      }),
      runtime.queryClient.invalidateQueries({
        queryKey: measureKeys.runs(productId),
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
  const submit =
    (handler: (form: HTMLFormElement) => void) =>
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      handler(event.currentTarget);
    };
  return (
    <Stack>
      <QueryState
        pending={sets.isPending}
        error={sets.error}
        retry={sets.refetch}
        lines={1}
      />
      {sets.data?.map((set) => (
        <SetPanel
          key={set.id}
          set={set}
          runs={runs.data ?? []}
          onStarted={refresh}
        />
      ))}
      <Panel small flat>
        <details className={styles.more} open={sets.data?.length === 0}>
          <summary>
            <Plus size={16} aria-hidden="true" /> 새 질문 세트
          </summary>
          <form
            className={styles.form}
            onSubmit={submit((form) => createSet.mutate(form))}
          >
            <TextField label="세트 이름" name="name" required maxLength={100} />
            <TextArea
              label='고정 질문 (한 줄에 "ID | 질문" 또는 "ID | 질문군 | 질문")'
              name="queries"
              required
              rows={5}
              placeholder={
                "G01 | 울 함량 50% 이상 니트를 찾아줘\nG02 | general | 7만원대 라운드넥 니트 추천해줘"
              }
              hint="질문에 상품명이나 상품 주소를 넣지 않아요."
            />
            <TextArea
              label="대상 상품명 (한 줄에 하나, 비우면 등록된 상품명)"
              name="targetNames"
              rows={2}
            />
            <TextArea
              label="대상 공개 상품 주소 (한 줄에 하나)"
              name="targetUrls"
              rows={2}
            />
            <ErrorMessage error={createSet.error} />
            <Button type="submit" loading={createSet.isPending}>
              질문 세트 만들기
            </Button>
          </form>
        </details>
      </Panel>
      <RunsTable runs={runs} back={back} />
    </Stack>
  );
}
function nextLabel(runs: MeasureRun[], setId: number) {
  const count = runs.filter((run) => run.setId === setId).length;
  return count === 0 ? "B0" : count === 1 ? "B1" : `P${count - 1}`;
}
function SetPanel({
  set,
  runs,
  onStarted,
}: {
  set: MeasureSet;
  runs: MeasureRun[];
  onStarted: () => unknown;
}) {
  const runtime = useRuntime();
  const start = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const values = formValues(form);
      return runtime.gateway.runMeasure(set.id, {
        label: String(values.label),
        provider: values.provider === "gemini" ? "gemini" : "openai",
        repeats: Number(values.repeats),
      });
    },
    onSuccess: onStarted,
  });
  return (
    <Panel
      aria-label={`질문 세트 ${set.name}`}
      title={`질문 세트: ${set.name} (${set.queries.length}문항)`}
      small
    >
      <ol className={styles.queries}>
        {set.queries.map((query) => (
          <li key={query.id}>
            <span className={styles.qid}>{query.id}</span>
            {query.question}
          </li>
        ))}
      </ol>
      <div className={styles.targets}>
        {[...set.targets.names, ...set.targets.urls].map((target) => (
          <Chip key={target}>{target}</Chip>
        ))}
      </div>
      <form
        className={styles.runForm}
        onSubmit={(event) => {
          event.preventDefault();
          start.mutate(event.currentTarget);
        }}
      >
        <TextField
          // 회차 목록이 바뀌면 다음 이름을 다시 채운다.
          key={nextLabel(runs, set.id)}
          label="회차 이름"
          name="label"
          required
          maxLength={20}
          // 서버 규칙과 같다(MeasureRunCreate.label). 제출 전에 브라우저가 막는다.
          pattern="[A-Za-z0-9_\-]+"
          title="영문·숫자·-·_만 쓸 수 있어요"
          hint="영문·숫자 (예: B0 정비 전, P1 정비 후)"
          defaultValue={nextLabel(runs, set.id)}
        />
        <Select label="AI" name="provider" defaultValue="openai">
          <option value="openai">ChatGPT(OpenAI)</option>
          <option value="gemini">Gemini</option>
        </Select>
        <TextField
          label="반복"
          name="repeats"
          type="number"
          min={1}
          max={5}
          defaultValue={3}
        />
        <Button
          type="submit"
          size="lg"
          icon={<Play aria-hidden="true" />}
          loading={start.isPending}
        >
          측정 시작
        </Button>
      </form>
      <ErrorMessage error={start.error} />
    </Panel>
  );
}
function RunsTable({
  runs,
  back,
}: {
  runs: ReturnType<typeof useMeasureRuns>;
  back: string;
}) {
  const navigate = useNavigate();
  const data = runs.data ?? [];
  return (
    <Panel title="측정 회차" small>
      <QueryState
        pending={runs.isPending}
        error={runs.error}
        retry={runs.refetch}
        lines={1}
      />
      {runs.data && data.length === 0 && (
        <EmptyState emoji="📊" title="아직 측정한 회차가 없어요" />
      )}
      {data.length > 0 && (
        <div className={styles.tableWrap}>
          <table className={styles.table} aria-label="측정 회차">
            <thead>
              <tr>
                <th scope="col">회차</th>
                <th scope="col">AI·모델</th>
                <th scope="col">상태</th>
                <th scope="col">정상/계획</th>
                <th scope="col">무효</th>
                <th scope="col">발견</th>
                <th scope="col">추천(상위 3)</th>
                <th scope="col">상품 링크 인용</th>
              </tr>
            </thead>
            <tbody>
              {data.map((run) => (
                <tr key={run.id}>
                  <th scope="row">
                    #{run.id} {run.label}
                    <small>{when(run.createdAt)}</small>
                  </th>
                  <td>
                    {providerLabels[run.condition.provider]} ·{" "}
                    {run.condition.model}
                  </td>
                  <td>
                    <Badge tone={runTones[run.status]}>
                      {runLabels[run.status]}
                    </Badge>
                    {run.job?.status === "failed" && " · 실행 실패"}
                    {run.job?.stale && " · 작업 상태 확인 필요"}
                  </td>
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
        </div>
      )}
      {data.length >= 2 && (
        <form
          className={styles.runForm}
          onSubmit={(event) => {
            event.preventDefault();
            // 고른 두 회차를 판매자에게 보이는 보고서 화면에서 바로 비교한다.
            const values = formValues(event.currentTarget);
            navigate(
              `${back}/report?before=${String(values.before)}&after=${String(values.after)}`,
            );
          }}
        >
          <Select
            label="정비 전 회차"
            name="before"
            defaultValue={data.at(-1)!.id}
          >
            {data.map((run) => (
              <option key={run.id} value={run.id}>
                #{run.id} {run.label}
              </option>
            ))}
          </Select>
          <Select label="정비 후 회차" name="after" defaultValue={data[0].id}>
            {data.map((run) => (
              <option key={run.id} value={run.id}>
                #{run.id} {run.label}
              </option>
            ))}
          </Select>
          <Button
            type="submit"
            variant="secondary"
            size="lg"
            icon={<FileText aria-hidden="true" />}
          >
            보고서로 비교
          </Button>
        </form>
      )}
    </Panel>
  );
}
