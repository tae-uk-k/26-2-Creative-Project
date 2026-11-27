import {
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import styles from "./Field.module.css";

type Frame = { label: ReactNode; hint?: ReactNode; error?: ReactNode };
function Wrap({
  id,
  label,
  hint,
  error,
  hideLabel,
  children,
}: Frame & { id: string; hideLabel?: boolean; children: ReactNode }) {
  return (
    <div className={styles.field}>
      <label
        htmlFor={id}
        className={hideLabel ? "visually-hidden" : styles.label}
      >
        {label}
      </label>
      {children}
      {hint && !error && (
        <span id={`${id}-hint`} className={styles.hint}>
          {hint}
        </span>
      )}
      {error && (
        <span id={`${id}-error`} className={styles.error} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
const described = (id: string, hint?: ReactNode, error?: ReactNode) =>
  error ? `${id}-error` : hint ? `${id}-hint` : undefined;
export function TextField({
  label,
  hint,
  error,
  hideLabel,
  id: given,
  className,
  ...rest
}: Frame & { hideLabel?: boolean } & InputHTMLAttributes<HTMLInputElement>) {
  const auto = useId();
  const id = given ?? auto;
  return (
    <Wrap id={id} label={label} hint={hint} error={error} hideLabel={hideLabel}>
      <input
        id={id}
        className={[styles.control, className].filter(Boolean).join(" ")}
        aria-invalid={error ? true : undefined}
        aria-describedby={described(id, hint, error)}
        {...rest}
      />
    </Wrap>
  );
}
export function TextArea({
  label,
  hint,
  error,
  hideLabel,
  id: given,
  className,
  ...rest
}: Frame & {
  hideLabel?: boolean;
} & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const auto = useId();
  const id = given ?? auto;
  return (
    <Wrap id={id} label={label} hint={hint} error={error} hideLabel={hideLabel}>
      <textarea
        id={id}
        className={[styles.control, className].filter(Boolean).join(" ")}
        aria-invalid={error ? true : undefined}
        aria-describedby={described(id, hint, error)}
        {...rest}
      />
    </Wrap>
  );
}
export function Select({
  label,
  hint,
  error,
  hideLabel,
  id: given,
  className,
  children,
  ...rest
}: Frame & {
  hideLabel?: boolean;
} & SelectHTMLAttributes<HTMLSelectElement>) {
  const auto = useId();
  const id = given ?? auto;
  return (
    <Wrap id={id} label={label} hint={hint} error={error} hideLabel={hideLabel}>
      <select
        id={id}
        className={[styles.control, className].filter(Boolean).join(" ")}
        aria-invalid={error ? true : undefined}
        aria-describedby={described(id, hint, error)}
        {...rest}
      >
        {children}
      </select>
    </Wrap>
  );
}
export function Checkbox({
  label,
  className,
  ...rest
}: { label: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={[styles.check, className].filter(Boolean).join(" ")}>
      <input type="checkbox" {...rest} />
      <span>{label}</span>
    </label>
  );
}
// 입력 칸 옆에 버튼 하나를 붙인다(상품 추가, 검색 등).
export function InlineForm({ children }: { children: ReactNode }) {
  return <div className={styles.withAction}>{children}</div>;
}
