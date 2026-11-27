import { useEffect, type HTMLAttributes, type ReactNode } from "react";
import { ChevronLeft } from "lucide-react";
import { TextLink } from "./Button";
import styles from "./Layout.module.css";

export function Page({
  width,
  children,
  className,
  ...rest
}: {
  width?: "narrow" | "medium";
  children: ReactNode;
} & HTMLAttributes<HTMLElement>) {
  return (
    <main
      id="main"
      className={[styles.page, width && styles[width], className]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </main>
  );
}
export function PageHeader({
  back,
  eyebrow,
  title,
  description,
  actions,
  children,
}: {
  back?: { to: string; label: string };
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  // 화면 제목을 브라우저 탭 제목에도 쓴다.
  useEffect(() => {
    if (typeof title !== "string") return;
    const before = document.title;
    document.title = `${title} · seelo`;
    return () => {
      document.title = before;
    };
  }, [title]);
  return (
    <header className={styles.header}>
      {back && (
        <TextLink className={styles.back} to={back.to}>
          <ChevronLeft aria-hidden="true" />
          {back.label}
        </TextLink>
      )}
      <div className={styles.headRow}>
        <div className={styles.titleBlock}>
          {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
          <h1 className={styles.title}>{title}</h1>
          {description && <p className={styles.description}>{description}</p>}
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>
      {children}
    </header>
  );
}
export function Stack({
  children,
  className,
  ...rest
}: { children: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={[styles.stack, className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}
// 본문과 오른쪽 보조 정보. 좁은 화면에서는 위아래로 쌓는다.
export function Split({ main, aside }: { main: ReactNode; aside: ReactNode }) {
  return (
    <div className={styles.split}>
      <div className={styles.stack}>{main}</div>
      <aside>{aside}</aside>
    </div>
  );
}
export function CardGrid({
  children,
  label,
}: {
  children: ReactNode;
  label?: string;
}) {
  return (
    <ul className={styles.grid} aria-label={label}>
      {children}
    </ul>
  );
}
export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className={styles.sectionTitle}>{children}</h2>;
}
