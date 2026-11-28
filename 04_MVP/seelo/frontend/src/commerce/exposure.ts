// 상품 한 개의 AI 노출 현황. 측정 회차 목록에서 공급자별 최근 값과 정비 전후 짝을 고른다.
import { reportPairs } from "./report";
import type { MeasureRun } from "./schemas";

export type Provider = MeasureRun["condition"]["provider"];
export const providers: Provider[] = ["openai", "gemini"];
const finished = (run: MeasureRun) =>
  run.status === "completed" || run.status === "partial";
export const measuring = (run: MeasureRun) =>
  run.status === "queued" || run.status === "running";

export type ProviderExposure = {
  provider: Provider;
  // 가장 최근에 끝난 회차. 정비 전·후를 가리지 않는다.
  latest: MeasureRun | null;
  // 보고서와 같은 기준(같은 질문 세트·조건)으로 짝지은 정비 전·후 회차.
  before: MeasureRun | null;
  after: MeasureRun | null;
};
export type ProductExposure = {
  providers: ProviderExposure[];
  measuring: boolean;
  measured: boolean;
  report: boolean;
  // 짝지은 회차 중 상품 발견 비율이 오른 공급자가 하나라도 있으면 true.
  improved: boolean;
};
const newestFirst = (a: MeasureRun, b: MeasureRun) =>
  a.createdAt < b.createdAt ? 1 : a.createdAt > b.createdAt ? -1 : 0;
export function productExposure(runs: MeasureRun[]): ProductExposure {
  const pairs = reportPairs(runs);
  const sorted = [...runs].sort(newestFirst);
  const items = providers.map((provider) => {
    const pair = pairs.find(
      (value) => value.after.condition.provider === provider,
    );
    return {
      provider,
      latest:
        sorted.find(
          (run) => run.condition.provider === provider && finished(run),
        ) ?? null,
      before: pair?.before ?? null,
      after: pair?.after ?? null,
    };
  });
  return {
    providers: items,
    measuring: runs.some(measuring),
    measured: runs.some(finished),
    report: pairs.length > 0,
    improved: items.some((item) => {
      const before = item.before?.summary.totals.rates.identified;
      const after = item.after?.summary.totals.rates.identified;
      return (
        before !== null &&
        before !== undefined &&
        after !== null &&
        after !== undefined &&
        after > before
      );
    }),
  };
}
