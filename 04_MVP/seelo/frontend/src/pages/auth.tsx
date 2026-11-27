import { useState, type FormEvent, type ReactNode } from "react";
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
import { Button, ButtonLink, TextLink } from "../ui/Button";
import { Badge, Notice } from "../ui/Display";
import { Checkbox, TextField } from "../ui/Field";
import { ErrorMessage, QueryState, formValues } from "./common";
import styles from "./auth.module.css";

// 로그인·가입 화면 공통 틀. 넓은 화면에서는 왼쪽에 랜딩과 같은 어두운 무대를 둔다.
function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={styles.wrap}>
      <aside className={styles.stage} aria-hidden="true">
        <img
          className={styles.stageLogo}
          src="/images/logo.png"
          width="78"
          height="38"
          alt=""
        />
        <div className={styles.stageCopy}>
          <strong>AI 검색에서 우리 상품이 답이 되도록</strong>
          <span>
            스마트스토어·카페24 상품 정보를 AI가 읽기 쉽게 정리합니다.
          </span>
        </div>
        <img
          className={styles.art}
          src="/images/stores-layered.webp"
          width="1672"
          height="941"
          alt=""
        />
      </aside>
      <main id="main" className={styles.formSide}>
        <div className={styles.card}>
          <Link to="/" aria-label="seelo 처음으로">
            <img
              className={styles.mobileLogo}
              src="/images/logo.png"
              width="78"
              height="38"
              alt="seelo"
            />
          </Link>
          <div>
            <h1 className={styles.title}>{title}</h1>
            {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}
function SocialButtons({
  intent,
  returnTo,
}: {
  intent: "login" | "signup";
  returnTo: string | null;
}) {
  const remember = () => rememberOAuthReturn(returnTo);
  return (
    <div className={styles.social}>
      <a
        className={[styles.socialButton, styles.kakao].join(" ")}
        href={`/api/oauth/kakao/start?intent=${intent}`}
        onClick={remember}
      >
        <span className={styles.socialMark} aria-hidden="true">
          💬
        </span>
        카카오로 계속하기
      </a>
      <a
        className={[styles.socialButton, styles.google].join(" ")}
        href={`/api/oauth/google/start?intent=${intent}`}
        onClick={remember}
      >
        <span className={styles.socialMark} aria-hidden="true">
          G
        </span>
        Google로 계속하기
      </a>
    </div>
  );
}
function PasswordFields() {
  return (
    <>
      <TextField
        label="새 비밀번호"
        name="password"
        type="password"
        autoComplete="new-password"
        required
        minLength={8}
        maxLength={128}
        hint="영문과 숫자를 섞어 8자 이상"
      />
      <TextField
        label="비밀번호 확인"
        name="passwordConfirm"
        type="password"
        autoComplete="new-password"
        required
      />
    </>
  );
}
// 전체 동의를 누르면 두 항목을 함께 고른다. 각 항목 옆에서 본문을 연다.
function Agreements() {
  const [terms, setTerms] = useState(false);
  const [privacy, setPrivacy] = useState(false);
  return (
    <div className={styles.agree}>
      <Checkbox
        className={styles.agreeAll}
        label="전체 동의"
        checked={terms && privacy}
        onChange={(event) => {
          setTerms(event.target.checked);
          setPrivacy(event.target.checked);
        }}
      />
      <div className={styles.agreeRow}>
        <Checkbox
          label="이용약관 동의"
          name="agreeTerms"
          required
          checked={terms}
          onChange={(event) => setTerms(event.target.checked)}
        />
        <Link to="/terms" target="_blank">
          보기
        </Link>
      </div>
      <div className={styles.agreeRow}>
        <Checkbox
          label="개인정보 처리 동의"
          name="agreePrivacy"
          required
          checked={privacy}
          onChange={(event) => setPrivacy(event.target.checked)}
        />
        <Link to="/privacy" target="_blank">
          보기
        </Link>
      </div>
    </div>
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
    <AuthLayout title="로그인">
      {params.get("error") && (
        <Notice tone="error">
          소셜 로그인을 완료하지 못했습니다. 다시 시도해 주세요.
        </Notice>
      )}
      <SocialButtons intent="login" returnTo={params.get("returnTo")} />
      <div className={styles.divider}>또는 이메일로</div>
      <form className={styles.form} onSubmit={submit}>
        <TextField
          label="이메일"
          name="email"
          type="email"
          autoComplete="username"
          required
        />
        <TextField
          label="비밀번호"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
        <ErrorMessage error={login.error} />
        <Button type="submit" size="lg" block loading={login.isPending}>
          로그인
        </Button>
      </form>
      <div className={styles.links}>
        <TextLink to="/signup">가입</TextLink>
        <TextLink to="/password/forgot">비밀번호 재설정</TextLink>
      </div>
    </AuthLayout>
  );
}
export function SignupPage() {
  const { auth } = useRuntime();
  const [params] = useSearchParams();
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
  if (signup.data)
    return (
      <AuthLayout title="메일함을 확인해 주세요">
        <MailNotice email={signup.data.email} ticket={signup.data.mailTicket} />
      </AuthLayout>
    );
  return (
    <AuthLayout
      title="가입"
      subtitle="스토어를 연결하고 상품 정비를 시작하세요."
    >
      <SocialButtons intent="signup" returnTo={params.get("returnTo")} />
      <div className={styles.divider}>또는 이메일로</div>
      <form className={styles.form} onSubmit={submit}>
        <TextField
          label="이메일"
          name="email"
          type="email"
          required
          autoComplete="username"
        />
        <PasswordFields />
        <Agreements />
        <ErrorMessage error={signup.error} />
        <Button type="submit" size="lg" block loading={signup.isPending}>
          인증 메일 요청
        </Button>
      </form>
      <div className={styles.links}>
        <TextLink to="/login">로그인</TextLink>
      </div>
    </AuthLayout>
  );
}
function MailNotice({ email, ticket }: { email?: string; ticket?: string }) {
  const { auth } = useRuntime();
  const resend = useMutation({ mutationFn: auth.resend });
  const currentTicket = resend.data?.mailTicket ?? ticket;
  const status = useQuery({
    queryKey: ["mail-status", currentTicket],
    queryFn: ({ signal }) => auth.mailStatus(currentTicket!, signal),
    enabled: Boolean(currentTicket),
    refetchInterval: (query) =>
      query.state.data?.status === "queued" ? 2000 : false,
    retry: false,
    gcTime: 0,
  });
  return (
    <div className={styles.mail}>
      <span className={styles.mailIcon} aria-hidden="true">
        📬
      </span>
      {email && <p className={styles.mailTo}>{email}</p>}
      <p role="status">
        {status.data?.status === "sent" ? (
          <Badge tone="green" dot>
            메일을 보냈어요
          </Badge>
        ) : status.data?.status === "failed" ? (
          <Badge tone="red" dot>
            메일을 보내지 못했어요
          </Badge>
        ) : currentTicket ? (
          <Badge tone="blue" dot>
            메일을 보내는 중
          </Badge>
        ) : (
          <Badge dot>링크를 열면 가입이 끝나요</Badge>
        )}
      </p>
      <ErrorMessage error={status.error ?? resend.error} />
      {email && (
        <Button
          variant="secondary"
          loading={resend.isPending}
          onClick={() => resend.mutate(email)}
        >
          인증 메일 다시 요청
        </Button>
      )}
      <TextLink to="/login">로그인으로</TextLink>
    </div>
  );
}
export function SignupSentPage() {
  return (
    <AuthLayout title="메일함을 확인해 주세요">
      <MailNotice />
    </AuthLayout>
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
      navigate("/home", { replace: true });
    },
  });
  // 링크 방문만으로 토큰을 소비하지 않는다.
  return (
    <AuthLayout title="이메일 인증" subtitle="버튼을 누르면 가입이 끝납니다.">
      <ErrorMessage error={verify.error} />
      <Button
        size="lg"
        block
        loading={verify.isPending}
        onClick={() => verify.mutate()}
      >
        이메일 인증 완료
      </Button>
    </AuthLayout>
  );
}
export function PasswordPage({ reset = false }: { reset?: boolean }) {
  const { token = "" } = useParams();
  const runtime = useRuntime();
  const operation = useMutation({
    mutationFn: async (value: Record<string, FormDataEntryValue>) => {
      if (reset) {
        await runtime.auth.reset({ ...value, token });
        await runtime.queryClient.cancelQueries();
        runtime.queryClient.clear();
        runtime.queryClient.setQueryData(["session"], null);
      } else await runtime.auth.forgot(String(value.email));
    },
  });
  if (operation.isSuccess)
    return (
      <AuthLayout
        title={reset ? "비밀번호를 바꿨어요" : "메일함을 확인해 주세요"}
      >
        <div className={styles.mail}>
          <span className={styles.mailIcon} aria-hidden="true">
            {reset ? "🔐" : "📬"}
          </span>
          <p role="status">
            {reset
              ? "새 비밀번호를 저장했습니다."
              : "요청을 접수했습니다. 이메일을 확인해 주세요."}
          </p>
          <ButtonLink to="/login" size="lg" block>
            로그인
          </ButtonLink>
        </div>
      </AuthLayout>
    );
  return (
    <AuthLayout
      title={reset ? "새 비밀번호 설정" : "비밀번호 재설정"}
      subtitle={
        reset ? undefined : "가입한 이메일로 재설정 링크를 보내 드려요."
      }
    >
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          if (!operation.isPending)
            operation.mutate(formValues(event.currentTarget));
        }}
      >
        {reset ? (
          <PasswordFields />
        ) : (
          <TextField
            label="이메일"
            name="email"
            type="email"
            autoComplete="username"
            required
          />
        )}
        <ErrorMessage error={operation.error} />
        <Button type="submit" size="lg" block loading={operation.isPending}>
          {reset ? "비밀번호 저장" : "메일 요청"}
        </Button>
      </form>
      <div className={styles.links}>
        <TextLink to="/login">로그인</TextLink>
      </div>
    </AuthLayout>
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
  if (complete.data?.mailTicket)
    return (
      <AuthLayout title="메일함을 확인해 주세요">
        <MailNotice ticket={complete.data.mailTicket} />
      </AuthLayout>
    );
  return (
    <AuthLayout
      title="가입 마무리"
      subtitle={
        pending.data
          ? `${pending.data.provider === "kakao" ? "카카오" : "Google"} 계정으로 가입합니다.`
          : undefined
      }
    >
      <QueryState
        pending={pending.isPending}
        error={pending.error}
        retry={pending.refetch}
        lines={2}
      />
      {pending.data && (
        <form
          className={styles.form}
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
            <TextField
              label="이메일"
              name="email"
              type="email"
              required
              hint="카카오에서 이메일을 받지 못해 따로 확인합니다."
            />
          )}
          <Agreements />
          <ErrorMessage error={complete.error} />
          <Button type="submit" size="lg" block loading={complete.isPending}>
            가입 완료
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
