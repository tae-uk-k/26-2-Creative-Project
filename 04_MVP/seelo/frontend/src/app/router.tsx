import "../styles/base.css";
import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { consumeOAuthReturn, safeReturnTo } from "../api/auth";
import { useStores } from "./commerce";
import {
  restartDemo,
  switchDemoPersona,
  useRuntime,
  useSession,
} from "./runtime";
import {
  LoginPage,
  PasswordPage,
  PendingSignupPage,
  SignupPage,
  SignupSentPage,
  VerifyPage,
} from "../pages/auth";
import { AccountPage } from "../pages/account";
import { ExposurePage } from "../pages/exposure";
import { HomePage } from "../pages/home";
import { LandingPage } from "../pages/landing/Landing";
import { PrivacyPage, TermsPage } from "../pages/legal";
import { MeasurePage } from "../pages/measure";
import { OperatorPage } from "../pages/operator";
import { PlanPage } from "../pages/plan";
import { ProductPage } from "../pages/product";
import { ReportPage } from "../pages/report";
import {
  StoreHomePage,
  StoreNewPage,
  StoreSettingsPage,
  StoresPage,
} from "../pages/stores";
import { NotFoundPage, QueryState } from "../pages/common";
import { AppShell, type ShellRole } from "../ui/AppShell";
import { Page } from "../ui/Layout";

export function SessionGuard() {
  const session = useSession();
  const location = useLocation();
  if (session.isPending || session.error)
    return (
      <Page width="medium">
        <QueryState
          pending={session.isPending}
          error={session.error}
          retry={session.refetch}
        />
      </Page>
    );
  if (!session.data)
    return (
      <Navigate
        to={`/login?returnTo=${encodeURIComponent(`${location.pathname}${location.search}${location.hash}`)}`}
        replace
      />
    );
  return <Outlet />;
}
// 운영자에게 내 스토어가 없으면 판매자 메뉴를 숨긴다. 판매자에게는 운영 관리를 보이지 않는다.
function useShellRole(): ShellRole {
  const session = useSession();
  const stores = useStores();
  if (session.data?.role !== "admin") return "seller";
  return stores.data?.length ? "both" : "operator";
}
function ShellLayout() {
  const runtime = useRuntime();
  const session = useSession();
  const navigate = useNavigate();
  const role = useShellRole();
  return (
    <AppShell
      email={session.data?.email}
      role={role}
      demo={
        runtime.mode === "demo"
          ? {
              persona: session.data?.role === "admin" ? "operator" : "seller",
              onPersona: (persona) =>
                void switchDemoPersona(runtime, persona).then(() =>
                  navigate(persona === "operator" ? "/operator" : "/home"),
                ),
              onRestart: restartDemo,
            }
          : undefined
      }
    />
  );
}
// 로그인 전에는 랜딩, 로그인했으면 홈으로 간다. 시연 모드는 발표용으로 랜딩을 그대로 보여 준다.
function Root() {
  const { mode } = useRuntime();
  const session = useSession();
  if (mode === "api" && session.data) return <Navigate to="/home" replace />;
  return <LandingPage signedIn={Boolean(session.data)} />;
}
function Entry() {
  const { mode } = useRuntime();
  const session = useSession();
  const [params] = useSearchParams();
  if (mode === "demo") return <Navigate to="/home" replace />;
  if (session.isPending || session.error)
    return (
      <Page width="narrow">
        <QueryState
          pending={session.isPending}
          error={session.error}
          retry={session.refetch}
        />
      </Page>
    );
  return session.data ? (
    <Navigate to={safeReturnTo(params.get("returnTo"))} replace />
  ) : (
    <LoginPage />
  );
}
// 소셜 로그인은 /home으로 돌아온다. 로그인 전에 보던 화면이 있으면 그곳으로 이어 간다.
function HomeRoute() {
  const [stored] = useState(() => {
    try {
      return sessionStorage.getItem("seelo-oauth-return");
    } catch {
      return null;
    }
  });
  useEffect(() => {
    if (stored !== null) consumeOAuthReturn();
  }, [stored]);
  const target = stored !== null ? safeReturnTo(stored) : "/home";
  const session = useSession();
  const stores = useStores();
  if (target !== "/home") return <Navigate to={target} replace />;
  // 내 스토어가 없는 운영자의 첫 화면은 운영 관리다.
  if (session.data?.role === "admin" && stores.data?.length === 0)
    return <Navigate to="/operator" replace />;
  return <HomePage />;
}
function LegacyProducts() {
  const { storeId = "" } = useParams();
  const location = useLocation();
  return <Navigate to={`/stores/${storeId}${location.search}`} replace />;
}
export function AppRoutes() {
  const { mode } = useRuntime();
  const authPage = (page: React.ReactNode) =>
    mode === "demo" ? <Navigate to="/home" replace /> : page;
  return (
    <Routes>
      <Route index element={<Root />} />
      <Route path="login" element={<Entry />} />
      <Route path="signup" element={authPage(<SignupPage />)} />
      <Route path="signup/sent" element={authPage(<SignupSentPage />)} />
      <Route path="verify-email/:token" element={authPage(<VerifyPage />)} />
      <Route path="password/forgot" element={authPage(<PasswordPage />)} />
      <Route
        path="password/reset/:token"
        element={authPage(<PasswordPage reset />)}
      />
      <Route
        path="signup/kakao-email"
        element={authPage(<PendingSignupPage />)}
      />
      <Route path="signup/terms" element={authPage(<PendingSignupPage />)} />
      <Route path="terms" element={<TermsPage />} />
      <Route path="privacy" element={<PrivacyPage />} />
      <Route element={<SessionGuard />}>
        <Route element={<ShellLayout />}>
          <Route path="home" element={<HomeRoute />} />
          <Route path="stores" element={<StoresPage />} />
          <Route path="stores/new" element={<StoreNewPage />} />
          <Route path="stores/:storeId" element={<StoreHomePage />} />
          <Route
            path="stores/:storeId/settings"
            element={<StoreSettingsPage />}
          />
          <Route path="stores/:storeId/products" element={<LegacyProducts />} />
          <Route
            path="stores/:storeId/products/:productId"
            element={<ProductPage />}
          />
          <Route
            path="stores/:storeId/products/:productId/plans/:planId"
            element={<PlanPage />}
          />
          <Route
            path="stores/:storeId/products/:productId/report"
            element={<ReportPage />}
          />
          <Route
            path="stores/:storeId/products/:productId/measure"
            element={<MeasurePage />}
          />
          <Route path="exposure" element={<ExposurePage />} />
          <Route path="operator" element={<OperatorPage />} />
          <Route path="account" element={<AccountPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
