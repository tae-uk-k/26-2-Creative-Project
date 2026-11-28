import { z } from "zod";

const errorSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.string(), z.unknown()).optional(),
  }),
});

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function messageOf(error: unknown): string {
  if (error instanceof z.ZodError)
    return error.issues.map((issue) => issue.message).join(" · ");
  return error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";
}

type ClientOptions = {
  fetch?: typeof fetch;
  cookie?: () => string;
  onUnauthorized?: () => void;
  timeoutMs?: number;
};
type RequestOptions = {
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
};

export class ApiClient {
  private csrfFlight?: Promise<void>;
  private readonly fetcher: typeof fetch;
  constructor(private readonly options: ClientOptions = {}) {
    this.fetcher = options.fetch ?? globalThis.fetch.bind(globalThis);
  }

  private csrfToken(): string | undefined {
    const raw = (this.options.cookie?.() ?? document.cookie)
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("seelo_csrf="));
    return raw
      ? decodeURIComponent(raw.slice("seelo_csrf=".length))
      : undefined;
  }

  private async timedFetch(
    path: string,
    init: RequestInit,
    timeoutMs?: number,
  ): Promise<Response> {
    const timeout = AbortSignal.timeout(
      timeoutMs ?? this.options.timeoutMs ?? 20_000,
    );
    const signal = init.signal
      ? AbortSignal.any([init.signal, timeout])
      : timeout;
    try {
      return await this.fetcher(path, {
        ...init,
        signal,
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
      });
    } catch (error) {
      if (init.signal?.aborted) throw error;
      throw new ApiError(
        0,
        timeout.aborted ? "TIMEOUT" : "NETWORK_ERROR",
        timeout.aborted
          ? "응답 시간이 지났습니다. 최신 상태를 조회해 주세요."
          : "서버에 연결하지 못했습니다.",
      );
    }
  }

  private async ensureCsrf(): Promise<void> {
    if (this.csrfToken()) return;
    this.csrfFlight ??= (async () => {
      const response = await this.timedFetch("/api/auth/csrf", {
        method: "GET",
      });
      if (!response.ok) await this.readError(response);
      if (!this.csrfToken())
        throw new ApiError(
          403,
          "CSRF_MISSING",
          "인증 쿠키를 확인하지 못했습니다.",
        );
    })().finally(() => {
      this.csrfFlight = undefined;
    });
    await this.csrfFlight;
  }

  private async readError(response: Response): Promise<never> {
    const parsed = errorSchema.safeParse(
      await response.json().catch(() => null),
    );
    const code = parsed.success
      ? parsed.data.error.code
      : `HTTP_${response.status}`;
    if (response.status === 401 && code === "AUTH_REQUIRED")
      this.options.onUnauthorized?.();
    throw new ApiError(
      response.status,
      code,
      parsed.success
        ? parsed.data.error.message
        : response.status === 404
          ? "요청한 API가 아직 연결되지 않았거나 대상을 찾을 수 없습니다."
          : "요청을 처리하지 못했습니다.",
      parsed.success ? parsed.data.error.details : {},
    );
  }

  async request<T>(
    path: string,
    schema: z.ZodType<T>,
    options: RequestOptions = {},
  ): Promise<T> {
    if (
      !path.startsWith("/api/") ||
      path.startsWith("//") ||
      path.includes("://")
    )
      throw new Error("같은 출처의 API 경로가 필요합니다.");
    const method = options.method ?? "GET";
    if (method !== "GET") await this.ensureCsrf();
    const headers: Record<string, string> = { Accept: "application/json" };
    if (options.body !== undefined)
      headers["Content-Type"] = "application/json";
    // 로그인·로그아웃 때 회전할 수 있으므로 요청마다 최신 쿠키를 읽는다.
    if (method !== "GET") headers["X-CSRF-Token"] = this.csrfToken()!;
    const response = await this.timedFetch(
      path,
      {
        method,
        headers,
        body:
          options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: options.signal,
      },
      options.timeoutMs,
    );
    if (!response.ok) return this.readError(response);
    const body: unknown =
      response.status === 204
        ? undefined
        : await response.json().catch(() => {
            throw new ApiError(
              response.status,
              "INVALID_RESPONSE",
              "서버 응답 형식이 올바르지 않습니다.",
            );
          });
    const parsed = schema.safeParse(body);
    if (!parsed.success)
      throw new ApiError(
        response.status,
        "CONTRACT_MISMATCH",
        "서버 응답이 프론트엔드 계약과 다릅니다.",
      );
    return parsed.data;
  }
}
