import type { CSSProperties, HTMLAttributes, ReactNode } from "react";
import {
  CircleAlert,
  CircleCheck,
  Info,
  LoaderCircle,
  TriangleAlert,
} from "lucide-react";
import styles from "./Display.module.css";

export function Panel({
  title,
  action,
  flat,
  tight,
  small,
  children,
  className,
  ...rest
}: {
  title?: ReactNode;
  action?: ReactNode;
  flat?: boolean;
  tight?: boolean;
  small?: boolean;
  children?: ReactNode;
} & Omit<HTMLAttributes<HTMLElement>, "title">) {
  return (
    <section
      className={[
        styles.panel,
        flat && styles.flat,
        tight && styles.tight,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {(title || action) && (
        <div className={styles.panelHead}>
          {title && (
            <h2
              className={[styles.panelTitle, small && styles.small]
                .filter(Boolean)
                .join(" ")}
            >
              {title}
            </h2>
          )}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export type Tone = "neutral" | "blue" | "green" | "orange" | "red";
export function Badge({
  tone = "neutral",
  dot,
  icon,
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <span className={[styles.badge, styles[tone], dot && styles.dot].join(" ")}>
      {icon}
      {children}
    </span>
  );
}
type NoticeTone = "info" | "progress" | "success" | "warning" | "error";
const noticeIcons: Record<NoticeTone, ReactNode> = {
  info: <Info />,
  progress: <LoaderCircle className={styles.spin} />,
  success: <CircleCheck />,
  warning: <TriangleAlert />,
  error: <CircleAlert />,
};
export function Notice({
  tone = "info",
  title,
  action,
  children,
  role,
}: {
  tone?: NoticeTone;
  title?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
  role?: "status" | "alert";
}) {
  return (
    <div
      className={[styles.notice, styles[tone]].join(" ")}
      role={role ?? (tone === "error" ? "alert" : "status")}
    >
      {noticeIcons[tone]}
      <div className={styles.noticeBody}>
        {title && <strong className={styles.noticeTitle}>{title}</strong>}
        {children && <div>{children}</div>}
      </div>
      {action && <div className={styles.noticeAction}>{action}</div>}
    </div>
  );
}
export function EmptyState({
  emoji,
  image,
  title,
  children,
  action,
}: {
  emoji?: string;
  image?: string;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={styles.empty}>
      {image ? (
        <img className={styles.emptyImage} src={image} alt="" />
      ) : (
        emoji && (
          <span className={styles.emptyArt} aria-hidden="true">
            {emoji}
          </span>
        )
      )}
      <p className={styles.emptyTitle}>{title}</p>
      {children && <p className={styles.emptyText}>{children}</p>}
      {action && <div className={styles.emptyAction}>{action}</div>}
    </div>
  );
}
export function Skeleton({
  width = "100%",
  height = "1rem",
  style,
}: {
  width?: string;
  height?: string;
  style?: CSSProperties;
}) {
  return (
    <span
      className={styles.skeleton}
      style={{ width, height, ...style }}
      aria-hidden="true"
    />
  );
}
export function Facts({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className={styles.facts}>
      {items.map(([term, value], index) => (
        <div key={index}>
          <dt>{term}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
export function Chip({
  href,
  icon,
  children,
  title,
}: {
  href?: string;
  icon?: ReactNode;
  children: ReactNode;
  title?: string;
}) {
  const body = (
    <>
      {icon}
      <span>{children}</span>
    </>
  );
  return href ? (
    <a
      className={styles.chip}
      href={href}
      target="_blank"
      rel="noreferrer"
      title={title}
    >
      {body}
    </a>
  ) : (
    <span className={styles.chip} title={title}>
      {body}
    </span>
  );
}
