import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import styles from "./List.module.css";

export function List({
  label,
  children,
}: {
  label?: string;
  children: ReactNode;
}) {
  return (
    <ul className={styles.list} aria-label={label}>
      {children}
    </ul>
  );
}
// 목록의 한 줄. 누르면 다음 화면으로 간다. 오른쪽에는 상태 하나만 둔다.
export function ListRow({
  to,
  media,
  title,
  sub,
  meta,
}: {
  to?: string;
  media?: ReactNode;
  title: ReactNode;
  sub?: ReactNode;
  meta?: ReactNode;
}) {
  const body = (
    <>
      {media && <span className={styles.media}>{media}</span>}
      <span className={styles.text}>
        <span className={styles.title}>{title}</span>
        {sub && <span className={styles.sub}>{sub}</span>}
      </span>
      {(meta || to) && (
        <span className={styles.meta}>
          {meta}
          {to && <ChevronRight className={styles.chevron} aria-hidden="true" />}
        </span>
      )}
    </>
  );
  return (
    <li>
      {to ? (
        <Link className={styles.row} to={to}>
          {body}
        </Link>
      ) : (
        <div className={styles.row}>{body}</div>
      )}
    </li>
  );
}
export function Card({ to, children }: { to?: string; children: ReactNode }) {
  return (
    <li>
      {to ? (
        <Link className={styles.card} to={to}>
          {children}
        </Link>
      ) : (
        <div className={styles.card}>{children}</div>
      )}
    </li>
  );
}
export function CardTop({ children }: { children: ReactNode }) {
  return <div className={styles.cardTop}>{children}</div>;
}
