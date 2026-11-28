import { useMemo, useState } from "react";
import { ArrowRight } from "lucide-react";
import { TextButton } from "./Button";
import styles from "./DiffView.module.css";

// 상품 HTML을 읽을 수 있는 글로 바꾼다. 스크립트를 실행하지 않고 이미지도 불러오지 않는다.
export function readableText(value: string): string {
  if (!/[<&]/.test(value)) return value.trim();
  const doc = new DOMParser().parseFromString(value, "text/html");
  doc
    .querySelectorAll("script, style, noscript, iframe, template")
    .forEach((node) => node.remove());
  doc.querySelectorAll("br").forEach((node) => node.replaceWith("\n"));
  doc.querySelectorAll("li").forEach((node) => node.prepend("• "));
  // 정비안의 사양 목록(dt 이름·dd 값)과 접힘 영역 제목을 한 줄씩 읽히게 한다.
  doc.querySelectorAll("dt").forEach((node) => node.append(": "));
  doc
    .querySelectorAll(
      "p, div, li, h1, h2, h3, h4, h5, h6, section, tr, ul, ol, dl, dd, summary, details",
    )
    .forEach((node) => node.append("\n"));
  return (doc.body.textContent ?? "")
    .replace(/[ \t ]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
// 앞·뒤에서 같은 부분을 빼고 바뀐 가운데만 표시한다. 정비안은 대부분 끝에 정보를 덧붙인다.
export function textDiff(before: string, after: string) {
  let start = 0;
  const max = Math.min(before.length, after.length);
  while (start < max && before[start] === after[start]) start++;
  let end = 0;
  while (
    end < max - start &&
    before[before.length - 1 - end] === after[after.length - 1 - end]
  )
    end++;
  return {
    prefix: before.slice(0, start),
    removed: before.slice(start, before.length - end),
    added: after.slice(start, after.length - end),
    suffix: before.slice(before.length - end),
  };
}
export function DiffView({
  before,
  after,
  beforeLabel = "지금",
  afterLabel = "바뀔 내용",
}: {
  before: string;
  after: string;
  beforeLabel?: string;
  afterLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [raw, setRaw] = useState(false);
  const diff = useMemo(
    () => textDiff(readableText(before), readableText(after)),
    [before, after],
  );
  const long =
    diff.prefix.length + diff.added.length + diff.suffix.length > 420 ||
    diff.prefix.length + diff.removed.length + diff.suffix.length > 420;
  const clamp = long && !open ? styles.clamped : "";
  return (
    <div
      className={[styles.wrap, open && styles.open].filter(Boolean).join(" ")}
    >
      <div className={styles.diff}>
        <div className={styles.side}>
          <span className={styles.sideLabel}>{beforeLabel}</span>
          <div className={[styles.text, clamp].join(" ")}>
            {diff.prefix || diff.removed || diff.suffix ? (
              <>
                {diff.prefix}
                {diff.removed && (
                  <del className={styles.removed}>{diff.removed}</del>
                )}
                {diff.suffix}
              </>
            ) : (
              <em className={styles.empty}>비어 있음</em>
            )}
          </div>
        </div>
        <span className={styles.arrow} aria-hidden="true">
          <ArrowRight />
        </span>
        <div className={[styles.side, styles.after].join(" ")}>
          <span className={styles.sideLabel}>{afterLabel}</span>
          <div className={[styles.text, clamp].join(" ")}>
            {diff.prefix}
            {diff.added && <ins className={styles.added}>{diff.added}</ins>}
            {diff.suffix}
          </div>
        </div>
      </div>
      <div className={styles.foot}>
        {long && (
          <TextButton onClick={() => setOpen((value) => !value)}>
            {open ? "접기" : "전체 보기"}
          </TextButton>
        )}
        <TextButton onClick={() => setRaw((value) => !value)}>
          {raw ? "HTML 닫기" : "HTML 보기"}
        </TextButton>
      </div>
      {raw && (
        <pre className={styles.raw} aria-label="바뀔 HTML">
          {after}
        </pre>
      )}
    </div>
  );
}
