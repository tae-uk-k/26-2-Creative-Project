import { type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  consumeOAuthReturn,
  rememberOAuthReturn,
  safeReturnTo,
} from "../api/auth";
import { acceptSession, useLogin, useRuntime } from "../app/runtime";
import { ErrorMessage, formValues, QueryState } from "./common";

function PasswordFields() {
  return (
    <>
      <label>
        새 비밀번호
        <input
          name="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          maxLength={128}
        />
      </label>
      <label>
        비밀번호 확인
        <input
          name="passwordConfirm"
          type="password"
          autoComplete="new-password"
          required
        />
      </label>
    </>
  );
}
function Agreements() {
  return (
    <>
      <label>
        <input name="agreeTerms" type="checkbox" required />
        이용약관 동의
      </label>
      <label>
        <input name="agreePrivacy" type="checkbox" required />
        개인정보 처리 동의
      </label>
    </>
  );
}
export function LoginPage() {
  const login = useLogin();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (login.isPending) return;
    try {
      await login.mutateAsync(formValues(event.currentTarget));
      navigate(safeReturnTo(params.get("returnTo")), { replace: true });
    } catch {
      /* 오류는 아래에서 표시한다. */
    }
  };
  return (
    <main>
      <h1>로그인</h1>
      {params.get("error") && (
        <p role="alert">
          소셜 로그인을 완료하지 못했습니다. 다시 시도해 주세요.
        </p>
      )}
      <form onSubmit={submit}>
        <label>
          이메일
          <input name="email" type="email" autoComplete="username" required />
        </label>
        <label>
          비밀번호
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
          />
        </label>
        <button disabled={login.isPending}>로그인</button>
      </form>
      <ErrorMessage error={login.error} />
      <p>
        <a
          href="/api/oauth/google/start"
          onClick={() => rememberOAuthReturn(params.get("returnTo"))}
        >
          Google 로그인
        </a>{" "}
        <a
          href="/api/oauth/kakao/start"
          onClick={() => rememberOAuthReturn(params.get("returnTo"))}
        >
          카카오 로그인
        </a>
      </p>
      <Link to="/signup">가입</Link>{" "}
      <Link to="/password/forgot">비밀번호 재설정</Link>
    </main>
  );
}
export function SignupPage() {
  const { auth } = useRuntime();
  const signup = useMutation({ mutationFn: auth.signup });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (signup.isPending) return;
    const value = formValues(event.currentTarget);
    signup.mutate({
      ...value,
      agreeTerms: value.agreeTerms === "on",
      agreePrivacy: value.agreePrivacy === "on",
    });
  };
  return (
    <main>
      <h1>가입</h1>
      <form onSubmit={submit}>
        <label>
          이메일
          <input name="email" type="email" required autoComplete="username" />
        </label>
        <PasswordFields />
        <Agreements />
        <button disabled={signup.isPending}>인증 메일 요청</button>
      </form>
      <ErrorMessage error={signup.error} />
      {signup.data && (
        <MailNotice email={signup.data.email} ticket={signup.data.mailTicket} />
      )}
      <Link to="/login">로그인</Link>
    </main>
  );
}
function MailNotice({ email, ticket }: { email?: string; ticket: string }) {
  const { auth } = useRuntime();
  const resend = useMutation({ mutationFn: auth.resend });
  const currentTicket = resend.data?.mailTicket ?? ticket;
  const status = useQuery({
    queryKey: ["mail-status", currentTicket],
    queryFn: ({ signal }) => auth.mailStatus(currentTicket, signal),
    refetchInterval: (query) =>
      query.state.data?.status === "queued" ? 2000 : false,
    retry: false,
    gcTime: 0,
  });
  return (
    <section>
      <p role="status">
        인증 요청을 접수했습니다.{" "}
        {status.data?.status === "sent"
          ? "메일 서버에 전달했습니다."
          : status.data?.status === "failed"
            ? "메일 전송에 실패했습니다."
            : "전송 상태를 확인 중입니다."}
      </p>
      <ErrorMessage error={status.error ?? resend.error} />
      {email && (
        <button
          disabled={resend.isPending}
          onClick={() => resend.mutate(email)}
        >
          인증 메일 다시 요청
        </button>
      )}
    </section>
  );
}
export function VerifyPage() {
  const { token = "" } = useParams();
  const runtime = useRuntime();
  const navigate = useNavigate();
  const verify = useMutation({
    mutationFn: () => runtime.auth.verify(token),
    onSuccess: async ({ user }) => {
      await acceptSession(runtime, user);
      navigate("/stores", { replace: true });
    },
  });
  // 링크 방문만으로 토큰을 소비하지 않는다.
  return (
    <main>
      <h1>이메일 인증</h1>
      <button disabled={verify.isPending} onClick={() => verify.mutate()}>
        이메일 인증 완료
      </button>
      <ErrorMessage error={verify.error} />
    </main>
  );
}
export function PasswordPage({ reset = false }: { reset?: boolean }) {
  const { token = "" } = useParams();
  const { auth } = useRuntime();
  const runtime = useRuntime();
  const operation = useMutation({
    mutationFn: async (value: Record<string, FormDataEntryValue>) => {
      if (reset) {
        await auth.reset({ ...value, token });
        await runtime.queryClient.cancelQueries();
        runtime.queryClient.clear();
        runtime.queryClient.setQueryData(["session"], null);
      } else await auth.forgot(String(value.email));
    },
  });
  return (
    <main>
      <h1>{reset ? "새 비밀번호 설정" : "비밀번호 재설정 메일"}</h1>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!operation.isPending)
            operation.mutate(formValues(event.currentTarget));
        }}
      >
        {reset ? (
          <PasswordFields />
        ) : (
          <label>
            이메일
            <input name="email" type="email" required />
          </label>
        )}
        <button disabled={operation.isPending}>
          {reset ? "비밀번호 저장" : "메일 요청"}
        </button>
      </form>
      <ErrorMessage error={operation.error} />
      {operation.isSuccess && (
        <p role="status">
          {reset
            ? "새 비밀번호를 저장했습니다."
            : "요청을 접수했습니다. 이메일을 확인해 주세요."}
        </p>
      )}
      <Link to="/login">로그인</Link>
    </main>
  );
}
export function PendingSignupPage() {
  const runtime = useRuntime();
  const navigate = useNavigate();
  const pending = useQuery({
    queryKey: ["pending-signup"],
    queryFn: ({ signal }) => runtime.auth.pending(signal),
    retry: false,
    gcTime: 0,
  });
  const complete = useMutation({
    mutationFn: runtime.auth.complete,
    onSuccess: async (data) => {
      if (data.user) {
        await acceptSession(runtime, data.user);
        navigate(
          data.next === "/home"
            ? consumeOAuthReturn()
            : safeReturnTo(data.next),
          { replace: true },
        );
      }
    },
  });
  return (
    <main>
      <h1>소셜 가입 마무리</h1>
      <QueryState
        pending={pending.isPending}
        error={pending.error}
        retry={pending.refetch}
      />
      {pending.data && !complete.data?.mailTicket && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (complete.isPending) return;
            const values = formValues(event.currentTarget);
            complete.mutate({
              agreeTerms: values.agreeTerms === "on",
              agreePrivacy: values.agreePrivacy === "on",
              ...(pending.data.needsEmail
                ? { email: String(values.email) }
                : {}),
            });
          }}
        >
          {pending.data.needsEmail && (
            <label>
              이메일
              <input name="email" type="email" required />
            </label>
          )}
          <Agreements />
          <button disabled={complete.isPending}>가입 완료</button>
        </form>
      )}
      <ErrorMessage error={complete.error} />
      {complete.data?.mailTicket && (
        <MailNotice ticket={complete.data.mailTicket} />
      )}
    </main>
  );
}
