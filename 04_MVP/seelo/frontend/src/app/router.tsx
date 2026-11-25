import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Link,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useSearchParams,
} from "react-router-dom";
import { consumeOAuthReturn, peekOAuthReturn, safeReturnTo } from "../api/auth";
import { useLogout, useRuntime, useSession } from "./runtime";
import {
  LoginPage,
  PasswordPage,
  PendingSignupPage,
  SignupPage,
  VerifyPage,
} from "../pages/auth";
import { ProductsPage, StoresPage, WorkspacePage } from "../pages/commerce";
import { OperatorPage } from "../pages/operator";
import { ErrorMessage, QueryState } from "../pages/common";

export function SessionGuard() {
  const session = useSession();
  const location = useLocation();
  if (session.isPending || session.error)
    return (
      <QueryState
        pending={session.isPending}
        error={session.error}
        retry={session.refetch}
      />
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
function Layout() {
  const { mode } = useRuntime();
  const session = useSession();
  const logout = useLogout();
  return (
    <>
      {mode === "demo" && (
        <p role="note">
          시연 모드 · 메모리의 고정 자료입니다. 실제 계정·상품·AI에 연결하지
          않습니다. 새로고침하면 초기화됩니다.
        </p>
      )}
      <nav>
        <Link to="/stores">seelo 기능 확인</Link>{" "}
        {session.data?.role === "admin" && (
          <>
            <Link to="/operator">운영자 고객 업무</Link>{" "}
          </>
        )}
        {session.data && (
          <>
            <span>{session.data.email}</span>{" "}
            <button disabled={logout.isPending} onClick={() => logout.mutate()}>
              {mode === "demo" ? "조회 캐시 초기화" : "로그아웃"}
            </button>
          </>
        )}
      </nav>
      <ErrorMessage error={logout.error} />
      <Outlet />
    </>
  );
}
function Entry() {
  const { mode } = useRuntime();
  const session = useSession();
  const [params] = useSearchParams();
  if (mode === "demo") return <Navigate to="/stores" replace />;
  if (session.isPending || session.error)
    return (
      <QueryState
        pending={session.isPending}
        error={session.error}
        retry={session.refetch}
      />
    );
  return session.data ? (
    <Navigate to={safeReturnTo(params.get("returnTo"))} replace />
  ) : (
    <LoginPage />
  );
}
function OAuthReturn() {
  const [path] = useState(peekOAuthReturn);
  useEffect(() => {
    consumeOAuthReturn();
  }, []);
  return <Navigate to={path} replace />;
}
export function AppRoutes() {
  const { mode } = useRuntime();
  const authPage = (page: React.ReactNode) =>
    mode === "demo" ? <Navigate to="/stores" replace /> : page;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/stores" replace />} />
        <Route path="home" element={<OAuthReturn />} />
        <Route path="login" element={<Entry />} />
        <Route path="signup" element={authPage(<SignupPage />)} />
        <Route
          path="signup/sent"
          element={authPage(
            <main>
              <h1>이메일 인증 대기</h1>
              <p>이메일의 인증 링크를 열어 가입을 완료해 주세요.</p>
              <Link to="/login">로그인</Link>
            </main>,
          )}
        />
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
        <Route element={<SessionGuard />}>
          <Route path="stores" element={<StoresPage />} />
          <Route path="operator" element={<OperatorPage />} />
          <Route path="stores/:storeId/products" element={<ProductsPage />} />
          <Route
            path="stores/:storeId/products/:productId"
            element={<WorkspacePage />}
          />
        </Route>
        <Route
          path="*"
          element={
            <main>
              <h1>페이지를 찾을 수 없습니다.</h1>
              <Link to="/stores">스토어 목록</Link>
            </main>
          }
        />
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
