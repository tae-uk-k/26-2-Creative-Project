import type { CSSProperties, ReactNode } from "react";
import { Check, LoaderCircle, X } from "lucide-react";
import styles from "./Steps.module.css";

export type StepState = "done" | "current" | "todo" | "error";
// 가로 단계 표시. 좁은 화면에서는 "3/7 · 단계 이름"으로 줄인다.
export function Stepper({
  steps,
  current,
  error = false,
  label,
}: {
  steps: string[];
  current: number;
  error?: boolean;
  label: string;
}) {
  const state = (index: number): StepState =>
    index < current
      ? "done"
      : index === current
        ? error
          ? "error"
          : "current"
        : "todo";
  return (
    <div aria-label={label} role="group">
      <ol
        className={styles.stepper}
        style={{ "--count": steps.length } as CSSProperties}
      >
        {steps.map((step, index) => (
          <li
            key={step}
            className={[styles.step, styles[state(index)]].join(" ")}
            aria-current={index === current ? "step" : undefined}
          >
            <span className={styles.bar} />
            <span className={styles.stepLabel}>{step}</span>
          </li>
        ))}
      </ol>
      <p className={styles.compact} aria-hidden="true">
        <b>
          {Math.min(current + 1, steps.length)}/{steps.length}
        </b>{" "}
        · {steps[Math.min(current, steps.length - 1)]}
      </p>
    </div>
  );
}
export type TimelineItem = {
  key: string;
  title: ReactNode;
  text?: ReactNode;
  state: StepState;
  busy?: boolean;
  content?: ReactNode;
};
// 세로 진행 목록. 연결 안내·AI 준비처럼 순서가 있는 일을 보여 준다.
export function Timeline({
  items,
  label,
  guide = false,
}: {
  items: TimelineItem[];
  label: string;
  // 안내 순서(따라 할 일)는 모든 단계를 같은 굵기로 보여 준다.
  guide?: boolean;
}) {
  return (
    <ol
      className={[styles.timeline, guide && styles.guide]
        .filter(Boolean)
        .join(" ")}
      aria-label={label}
    >
      {items.map((item, index) => (
        <li
          key={item.key}
          className={[styles.item, styles[item.state]].join(" ")}
          aria-current={item.state === "current" ? "step" : undefined}
        >
          <span className={styles.marker} aria-hidden="true">
            {item.state === "done" ? (
              <Check />
            ) : item.state === "error" ? (
              <X />
            ) : item.busy ? (
              <LoaderCircle className={styles.spin} />
            ) : (
              index + 1
            )}
          </span>
          <div className={styles.itemBody}>
            <span className={styles.itemTitle}>{item.title}</span>
            {item.text && <span className={styles.itemText}>{item.text}</span>}
            {item.content && (
              <div className={styles.itemContent}>{item.content}</div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
