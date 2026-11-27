import type { ReactNode } from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { percent } from "./labels";
import styles from "./Metric.module.css";

const width = (value: number | null | undefined) =>
  `${Math.max(0, Math.min(1, value ?? 0)) * 100}%`;
// 정비 전후 비율을 막대로 나란히 보여 준다. 판정할 수 없는 값은 0%로 그리지 않는다.
export function MetricCompare({
  label,
  before,
  after,
  caption,
}: {
  label: ReactNode;
  before: number | null;
  after: number | null;
  caption?: ReactNode;
}) {
  const known = before !== null && after !== null;
  const change = known ? Math.round((after - before) * 100) : null;
  return (
    <div className={styles.metric}>
      <div className={styles.label}>
        <span>{label}</span>
        {change !== null && (
          <span
            className={[
              styles.delta,
              change > 0 ? styles.up : change < 0 ? styles.down : styles.flat,
            ].join(" ")}
          >
            {change > 0 ? (
              <ArrowUpRight aria-hidden="true" />
            ) : change < 0 ? (
              <ArrowDownRight aria-hidden="true" />
            ) : null}
            {change > 0
              ? `+${change}%p`
              : change < 0
                ? `${change}%p`
                : "변화 없음"}
          </span>
        )}
      </div>
      <div className={styles.values}>
        <span className={styles.before}>{percent(before)}</span>
        <ArrowRight className={styles.arrow} size={18} aria-hidden="true" />
        <span className={styles.after}>{percent(after)}</span>
      </div>
      <div className={styles.bars} aria-hidden="true">
        <div className={styles.track}>
          {before !== null && (
            <span
              className={[styles.fill, styles.fillBefore].join(" ")}
              style={{ width: width(before) }}
            />
          )}
        </div>
        <div className={styles.track}>
          {after !== null && (
            <span
              className={[styles.fill, styles.fillAfter].join(" ")}
              style={{ width: width(after) }}
            />
          )}
        </div>
      </div>
      {caption && <span className={styles.caption}>{caption}</span>}
    </div>
  );
}
export function MetricValue({
  label,
  value,
  caption,
}: {
  label: ReactNode;
  value: number | null;
  caption?: ReactNode;
}) {
  return (
    <div className={styles.metric}>
      <div className={styles.label}>{label}</div>
      <span className={[styles.after, styles.single].join(" ")}>
        {percent(value)}
      </span>
      <div className={styles.track} aria-hidden="true">
        {value !== null && (
          <span
            className={[styles.fill, styles.fillAfter].join(" ")}
            style={{ width: width(value) }}
          />
        )}
      </div>
      {caption && <span className={styles.caption}>{caption}</span>}
    </div>
  );
}
