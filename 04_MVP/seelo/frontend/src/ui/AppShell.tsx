import type { CSSProperties, ReactNode } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import {
  BriefcaseBusiness,
  ChartColumn,
  House,
  Store,
  UserRound,
} from "lucide-react";
import type { Platform } from "../commerce/schemas";
import { platformNames } from "../commerce/schemas";
import styles from "./AppShell.module.css";

type NavItem = { to: string; label: string; icon: ReactNode };
export type ShellRole = "seller" | "operator" | "both";
export function AppShell({
  email,
  role,
  demo,
}: {
  email?: string;
  // seller: 판매자 메뉴만, operator: 운영 관리만, both: 스토어를 가진 관리자 계정.
  role: ShellRole;
  demo?: {
    persona: "seller" | "operator";
    onPersona: (persona: "seller" | "operator") => void;
    onRestart: () => void;
  };
}) {
  const seller: NavItem[] = [
    { to: "/home", label: "홈", icon: <House aria-hidden="true" /> },
    { to: "/stores", label: "스토어", icon: <Store aria-hidden="true" /> },
    {
      to: "/exposure",
      label: "AI 노출",
      icon: <ChartColumn aria-hidden="true" />,
    },
  ];
  const operator: NavItem = {
    to: "/operator",
    label: "운영 관리",
    icon: <BriefcaseBusiness aria-hidden="true" />,
  };
  const items =
    role === "seller"
      ? seller
      : role === "operator"
        ? [operator]
        : [...seller, operator];
  const home = role === "operator" ? "/operator" : "/home";
  return (
    <>
      <a className={styles.skip} href="#main">
        본문 바로가기
      </a>
      {demo && (
        <div className={styles.demo} role="note">
          <span className={styles.demoLabel}>시연</span>
          <div
            className={styles.persona}
            role="group"
            aria-label="시연 화면 선택"
          >
            {(["seller", "operator"] as const).map((key) => (
              <button
                key={key}
                type="button"
                aria-pressed={demo.persona === key}
                onClick={() => demo.onPersona(key)}
              >
                {key === "seller" ? "사장님 화면" : "운영자 화면"}
              </button>
            ))}
          </div>
          <Link className={styles.demoLink} to="/">
            소개 화면
          </Link>
          <button
            type="button"
            className={styles.demoLink}
            onClick={demo.onRestart}
          >
            처음부터
          </button>
        </div>
      )}
      <header className={styles.bar}>
        <div className={styles.inner}>
          <Link className={styles.brand} to={home} aria-label="seelo 처음 화면">
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
