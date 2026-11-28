// 보고서에 쓸 정비 전·후 회차 짝을 고른다. 같은 질문 세트·같은 측정 조건끼리만 짝짓는다.
import type { MeasureRun } from "./schemas";

export type ReportPair = { key: string; before: MeasureRun; after: MeasureRun };
const finished = (run: MeasureRun) =>
  run.status === "completed" || run.status === "partial";
export const conditionKey = (run: MeasureRun) =>
  [
    run.setId,
    run.condition.provider,
    run.condition.model,
    run.condition.toolOptions,
    run.condition.repeats,
  ].join("|");
// 정비 후 회차(반영한 정비안이 기록된 회차) 중 가장 최근 것과, 그보다 먼저 끝난 정비 전 회차 중
// 가장 가까운 것을 짝짓는다. ChatGPT를 먼저 보여 준다.
export function reportPairs(runs: MeasureRun[]): ReportPair[] {
  const groups = new Map<string, MeasureRun[]>();
  for (const run of runs.filter(finished))
    groups.set(conditionKey(run), [
      ...(groups.get(conditionKey(run)) ?? []),
      run,
    ]);
  const pairs: ReportPair[] = [];
  for (const [key, group] of groups) {
    const byTime = [...group].sort((a, b) =>
      a.createdAt < b.createdAt ? 1 : -1,
    );
    const after = byTime.find((run) => run.planId !== null);
    if (!after) continue;
    const before = byTime.find(
      (run) => run.planId === null && run.createdAt < after.createdAt,
    );
    if (before) pairs.push({ key, before, after });
  }
  return pairs.sort((a, b) =>
    a.after.condition.provider === b.after.condition.provider
      ? 0
      : a.after.condition.provider === "openai"
        ? -1
        : 1,
  );
}
