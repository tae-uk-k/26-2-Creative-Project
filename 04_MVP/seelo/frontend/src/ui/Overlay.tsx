import { useEffect, useId, useRef, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Button } from "./Button";
import styles from "./Overlay.module.css";

// 되돌리기 어려운 행동 전에 결과를 보여 주고 확인받는다.
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = "닫기",
  danger,
  busy,
  confirmDisabled,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: ReactNode;
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const titleId = useId();
  const box = useRef<HTMLDivElement>(null);
  const before = useRef<Element | null>(null);
  useEffect(() => {
    if (!open) return;
    before.current = document.activeElement;
    box.current
      ?.querySelector<HTMLElement>(
        "input, textarea, select, button:not([data-cancel])",
      )
      ?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      if (before.current instanceof HTMLElement) before.current.focus();
    };
  }, [open, busy, onClose]);
  if (!open) return null;
  return (
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <div
        ref={box}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <h2 id={titleId} className={styles.dialogTitle}>
          {title}
        </h2>
        {children && <div className={styles.dialogBody}>{children}</div>}
        <div className={styles.dialogActions}>
          <Button
            variant="secondary"
            size="lg"
            onClick={onClose}
            disabled={busy}
            data-cancel
          >
            {cancelLabel}
          </Button>
          <Button
            variant={danger ? "danger" : "primary"}
            size="lg"
            loading={busy}
            disabled={confirmDisabled}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
export type TabItem = {
  key: string;
  label: ReactNode;
  count?: number;
};
function Count({ value }: { value?: number }) {
  return value === undefined ? null : (
    <span
      className={[styles.count, value === 0 && styles.zero]
        .filter(Boolean)
        .join(" ")}
    >
      {value}
    </span>
  );
}
// 같은 화면 안에서 보기를 바꾸는 탭.
export function Tabs({
  items,
  value,
  onChange,
  label,
}: {
  items: TabItem[];
  value: string;
  onChange: (key: string) => void;
  label: string;
}) {
  return (
    <div className={styles.tabs} role="tablist" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          role="tab"
          aria-selected={item.key === value}
          className={styles.tab}
          onClick={() => onChange(item.key)}
        >
          {item.label}
          <Count value={item.count} />
        </button>
      ))}
    </div>
  );
}
// 주소가 다른 화면으로 이동하는 탭.
export function LinkTabs({
  items,
  label,
}: {
  items: (TabItem & { to: string; end?: boolean })[];
  label: string;
}) {
  return (
    <nav className={styles.tabs} aria-label={label}>
      {items.map((item) => (
        <NavLink
          key={item.key}
          to={item.to}
          end={item.end}
          className={styles.tab}
        >
          {item.label}
          <Count value={item.count} />
        </NavLink>
      ))}
    </nav>
  );
}
// 화면 아래에 붙는 주 행동 막대. 선택한 항목 수와 주 행동을 함께 보여 준다.
export function ActionBar({
  summary,
  children,
}: {
  summary?: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      <div className={styles.actionSpacer} aria-hidden="true" />
      <div className={styles.actionBar}>
        {summary && <div className={styles.actionSummary}>{summary}</div>}
        {children}
      </div>
    </>
  );
}
