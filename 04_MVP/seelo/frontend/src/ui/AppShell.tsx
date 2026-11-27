import type { CSSProperties, ReactNode } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { BriefcaseBusiness, House, Store, UserRound } from "lucide-react";
import type { Platform } from "../commerce/schemas";
import { platformNames } from "../commerce/schemas";
import styles from "./AppShell.module.css";

type NavItem = { to: string; label: string; icon: ReactNode };
export function AppShell({
  email,
  admin,
  demo,
  onReset,
  resetting,
}: {
  email?: string;
  admin: boolean;
  demo: boolean;
  onReset: () => void;
  resetting: boolean;
}) {
  const items: NavItem[] = [
    { to: "/home", label: "홈", icon: <House aria-hidden="true" /> },
    { to: "/stores", label: "스토어", icon: <Store aria-hidden="true" /> },
    ...(admin
      ? [
          {
            to: "/operator",
            label: "운영자",
            icon: <BriefcaseBusiness aria-hidden="true" />,
          },
        ]
      : []),
  ];
  return (
    <>
      <a className={styles.skip} href="#main">
        본문 바로가기
      </a>
      {demo && (
        <div className={styles.demo} role="note">
          <span>
            시연 모드
            <span className={styles.demoLong}>
              {" "}
              · 실제 쇼핑몰과 AI에 연결하지 않습니다
            </span>
          </span>
          <button onClick={onReset} disabled={resetting}>
            조회 캐시 초기화
          </button>
        </div>
      )}
      <header className={styles.bar}>
        <div className={styles.inner}>
          <Link className={styles.brand} to="/home" aria-label="seelo 홈">
            <img src="/images/logo.png" width="78" height="38" alt="seelo" />
          </Link>
          <nav className={styles.nav} aria-label="주요 메뉴">
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} className={styles.navLink}>
                {item.icon}
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className={styles.end}>
            {email && (
              <NavLink
                to="/account"
                className={styles.account}
                aria-label={`계정 ${email}`}
              >
                <span className={styles.avatar} aria-hidden="true">
                  {email[0]?.toUpperCase()}
                </span>
                <span>{email}</span>
              </NavLink>
            )}
          </div>
        </div>
      </header>
      <div className={styles.body}>
        <Outlet />
      </div>
      <nav
        className={styles.mobileNav}
        aria-label="하단 메뉴"
        style={{ "--tabs": items.length + 1 } as CSSProperties}
      >
        {[
          ...items,
          {
            to: "/account",
            label: "계정",
            icon: <UserRound aria-hidden="true" />,
          },
        ].map((item) => (
          <NavLink key={item.to} to={item.to}>
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>
    </>
  );
}
const logos: Record<Platform, string> = {
  smartstore: "/images/smartstore.png",
  cafe24: "/images/cafe24.svg",
};
export function PlatformMark({
  platform,
  size,
}: {
  platform: Platform;
  size?: string;
}) {
  return (
    <span
      className={[styles.platform, styles[platform]].join(" ")}
      style={size ? ({ "--size": size } as CSSProperties) : undefined}
    >
      <img src={logos[platform]} alt={platformNames[platform]} />
    </span>
  );
}
