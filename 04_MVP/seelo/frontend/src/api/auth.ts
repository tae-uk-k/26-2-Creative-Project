import { z } from "zod";
import type { ApiClient } from "./client";

export const userSchema = z.object({
  id: z.number().int(),
  email: z.email(),
  role: z.enum(["owner", "admin"]),
  provider: z.enum(["email", "google", "kakao"]),
  hasStore: z.boolean(),
});
export type User = z.infer<typeof userSchema>;
const email = z
  .string()
  .trim()
  .toLowerCase()
  .pipe(z.email("이메일 형식을 확인해 주세요."));
const password = z
  .string()
  .min(8, "비밀번호는 8자 이상이어야 합니다.")
  .max(128)
  .regex(/[a-zA-Z]/, "영문을 포함해 주세요.")
  .regex(/[0-9]/, "숫자를 포함해 주세요.");
export const loginSchema = z.object({
  email,
  password: z.string().min(1, "비밀번호를 입력해 주세요.").max(128),
});
export const signupSchema = z
  .object({
    email,
    password,
    passwordConfirm: z.string(),
    agreeTerms: z.literal(true, "이용약관에 동의해 주세요."),
    agreePrivacy: z.literal(true, "개인정보 처리에 동의해 주세요."),
  })
  .refine((value) => value.password === value.passwordConfirm, {
    message: "비밀번호가 서로 다릅니다.",
    path: ["passwordConfirm"],
  });
export const resetSchema = z
  .object({
    token: z.string().min(10).max(200),
    password,
    passwordConfirm: z.string(),
  })
  .refine((value) => value.password === value.passwordConfirm, {
    message: "비밀번호가 서로 다릅니다.",
    path: ["passwordConfirm"],
  });
const ticketSchema = z.object({ mailTicket: z.string() });

export function createAuthApi(client: ApiClient) {
  const post = <T>(path: string, schema: z.ZodType<T>, body?: unknown) =>
    client.request(`/api/auth/${path}`, schema, { method: "POST", body });
  return {
    me: (signal?: AbortSignal) =>
      client.request("/api/auth/me", userSchema, { signal }),
    login: (input: unknown) =>
      post("login", z.object({ user: userSchema }), loginSchema.parse(input)),
    logout: () => post("logout", z.undefined()),
    signup: (input: unknown) =>
      post(
        "signup",
        ticketSchema.extend({ email: z.string() }),
        signupSchema.parse(input),
      ),
    verify: (token: string) =>
      post("verify-email", z.object({ user: userSchema }), { token }),
    resend: (value: string) =>
      post("verify-email/resend", ticketSchema, { email: email.parse(value) }),
    mailStatus: (ticket: string, signal?: AbortSignal) =>
      client.request(
        `/api/auth/signup/mail-status?ticket=${encodeURIComponent(ticket)}`,
        z.object({ status: z.enum(["queued", "sent", "failed"]) }),
        { signal },
      ),
    forgot: (value: string) =>
      post("password/forgot", z.object({}), { email: email.parse(value) }),
    reset: (input: unknown) =>
      post("password/reset", z.undefined(), resetSchema.parse(input)),
    pending: (signal?: AbortSignal) =>
      client.request(
        "/api/auth/pending-signup",
        z.object({
          provider: z.enum(["google", "kakao"]),
          email: z.string().nullable(),
          needsEmail: z.boolean(),
        }),
        { signal },
      ),
    complete: (input: {
      agreeTerms: boolean;
      agreePrivacy: boolean;
      email?: string;
    }) =>
      post(
        "pending-signup/complete",
        z.object({
          next: z.string(),
          user: userSchema.optional(),
          mailTicket: z.string().optional(),
        }),
        input,
      ),
  };
}

// 외부 URL·프로토콜 상대 경로·역슬래시를 복귀 대상으로 사용하지 않는다.
export function safeReturnTo(value: string | null | undefined): string {
  if (!value || !/^\/(?!\/)/.test(value) || /[\\\u0000-\u0020]/.test(value))
    return "/home";
  try {
    const url = new URL(value, "https://seelo.local");
    return url.origin === "https://seelo.local" &&
      !/^\/(login|signup)(\/|$)/.test(url.pathname)
      ? `${url.pathname}${url.search}${url.hash}`
      : "/home";
  } catch {
    return "/home";
  }
}

export function rememberOAuthReturn(value: string | null) {
  try {
    sessionStorage.setItem("seelo-oauth-return", safeReturnTo(value));
  } catch {
    /* 저장소가 차단돼도 로그인은 진행한다. */
  }
}
export function peekOAuthReturn(): string {
  try {
    return safeReturnTo(sessionStorage.getItem("seelo-oauth-return"));
  } catch {
    return "/home";
  }
}
export function consumeOAuthReturn(): string {
  try {
    const value = sessionStorage.getItem("seelo-oauth-return");
    sessionStorage.removeItem("seelo-oauth-return");
    return safeReturnTo(value);
  } catch {
    return "/home";
  }
}
