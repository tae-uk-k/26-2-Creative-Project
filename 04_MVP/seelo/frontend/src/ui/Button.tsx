import type {
  AnchorHTMLAttributes,
  ButtonHTMLAttributes,
  ReactNode,
} from "react";
import { Link, type LinkProps } from "react-router-dom";
import { LoaderCircle } from "lucide-react";
import styles from "./Button.module.css";

type Look = {
  variant?:
    "primary" | "secondary" | "tertiary" | "ghost" | "danger" | "dangerSoft";
  size?: "sm" | "md" | "lg";
  block?: boolean;
  icon?: ReactNode;
  iconRight?: ReactNode;
};
function classes({ variant = "primary", size = "md", block }: Look) {
  return [
    styles.button,
    variant !== "primary" && styles[variant],
    size !== "md" && styles[size],
    block && styles.block,
  ]
    .filter(Boolean)
    .join(" ");
}
function Content({
  icon,
  iconRight,
  children,
}: {
  icon?: ReactNode;
  iconRight?: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      {icon}
      {children}
      {iconRight}
    </>
  );
}
export function Button({
  variant,
  size,
  block,
  icon,
  iconRight,
  loading = false,
  className,
  children,
  disabled,
  type = "button",
  ...rest
}: Look &
  ButtonHTMLAttributes<HTMLButtonElement> & {
    loading?: boolean;
  }) {
  return (
    <button
      type={type}
      className={[
        classes({ variant, size, block }),
        loading && styles.loading,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      <Content icon={icon} iconRight={iconRight}>
        {children}
      </Content>
      {loading && (
        <span className={styles.spinner} aria-hidden="true">
          <LoaderCircle />
        </span>
      )}
    </button>
  );
}
export function ButtonLink({
  variant,
  size,
  block,
  icon,
  iconRight,
  className,
  children,
  ...rest
}: Look & LinkProps) {
  return (
    <Link
      className={[classes({ variant, size, block }), className]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      <Content icon={icon} iconRight={iconRight}>
        {children}
      </Content>
    </Link>
  );
}
// 외부 페이지(플랫폼 관리자 등)는 새 탭으로 연다.
export function ExternalButton({
  variant,
  size,
  block,
  icon,
  iconRight,
  className,
  children,
  ...rest
}: Look & AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a
      className={[classes({ variant, size, block }), className]
        .filter(Boolean)
        .join(" ")}
      target="_blank"
      rel="noreferrer"
      {...rest}
    >
      <Content icon={icon} iconRight={iconRight}>
        {children}
      </Content>
    </a>
  );
}
export function TextLink({
  className,
  children,
  ...rest
}: LinkProps & { children: ReactNode }) {
  return (
    <Link
      className={[styles.textLink, className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </Link>
  );
}
export function TextButton({
  className,
  children,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type={type}
      className={[styles.textLink, className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </button>
  );
}
