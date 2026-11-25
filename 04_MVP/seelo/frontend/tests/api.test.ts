import { describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { ApiClient, ApiError } from "../src/api/client";
import {
  createAuthApi,
  loginSchema,
  safeReturnTo,
  signupSchema,
} from "../src/api/auth";
import { createHttpGateway } from "../src/commerce/http-gateway";
import { createDemoGateway } from "../src/commerce/demo-gateway";

const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
describe("공통 통신", () => {
  it("CSRF가 없으면 초기화 후 변경 요청을 보낸다", async () => {
    let cookie = "";
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (path, init) => {
        if (path === "/api/auth/csrf") {
          cookie = "seelo_csrf=one";
          return new Response(null, { status: 204 });
        }
        expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("one");
        expect(init?.credentials).toBe("same-origin");
        return json({ ok: true });
      });
    const client = new ApiClient({ fetch: fetcher, cookie: () => cookie });
    await client.request("/api/test", z.object({ ok: z.boolean() }), {
      method: "POST",
      body: {},
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("CSRF 초기화 중복을 합치고 회전한 쿠키를 읽는다", async () => {
    let cookie = "";
    const tokens: string[] = [];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (path, init) => {
        if (path === "/api/auth/csrf") {
          await Promise.resolve();
          cookie = "seelo_csrf=first";
          return new Response(null, { status: 204 });
        }
        tokens.push(new Headers(init?.headers).get("X-CSRF-Token")!);
        return new Response(null, { status: 204 });
      });
    const client = new ApiClient({ fetch: fetcher, cookie: () => cookie });
    await Promise.all([
      client.request("/api/a", z.undefined(), { method: "POST" }),
      client.request("/api/b", z.undefined(), { method: "POST" }),
    ]);
    cookie = "seelo_csrf=rotated";
    await client.request("/api/c", z.undefined(), { method: "POST" });
    expect(
      fetcher.mock.calls.filter(([path]) => path === "/api/auth/csrf"),
    ).toHaveLength(1);
    expect(tokens).toEqual(["first", "first", "rotated"]);
  });
  it("변경 요청 실패를 자동 재시도하지 않는다", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      json(
        {
          error: {
            code: "COMMERCE_PROVIDER_ERROR",
            message: "조회 실패",
            details: {},
          },
        },
        503,
      ),
    );
    const client = new ApiClient({
      fetch: fetcher,
      cookie: () => "seelo_csrf=token",
    });
    await expect(
      client.request("/api/test", z.unknown(), { method: "POST" }),
    ).rejects.toMatchObject({ status: 503 });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("AUTH_REQUIRED에서만 세션 종료 처리를 호출한다", async () => {
    const onUnauthorized = vi.fn();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        json({ error: { code: "INVALID_CREDENTIALS", message: "오류" } }, 401),
      )
      .mockResolvedValueOnce(
        json({ error: { code: "AUTH_REQUIRED", message: "로그인 필요" } }, 401),
      );
    const client = new ApiClient({ fetch: fetcher, onUnauthorized });
    await expect(
      client.request("/api/login", z.unknown()),
    ).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).not.toHaveBeenCalled();
    await expect(
      client.request("/api/private", z.unknown()),
    ).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });
  it("서버 오류와 잘못된 응답을 구분한다", async () => {
    const client = new ApiClient({
      fetch: vi.fn<typeof fetch>().mockResolvedValue(json({ wrong: 1 })),
    });
    await expect(
      client.request("/api/test", z.object({ value: z.string() })),
    ).rejects.toMatchObject({ code: "CONTRACT_MISMATCH" });
  });
  it("외부 API 주소로 세션을 보내지 않는다", async () => {
    const fetcher = vi.fn<typeof fetch>();
    const client = new ApiClient({ fetch: fetcher });
    await expect(
      client.request("https://other.example/api/test", z.unknown()),
    ).rejects.toThrow();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("조회 취소 신호를 fetch에 전달한다", async () => {
    const controller = new AbortController();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (_path, init) => {
        expect(init?.signal).toBeDefined();
        controller.abort();
        expect(init?.signal?.aborted).toBe(true);
        throw new DOMException("취소", "AbortError");
      });
    const client = new ApiClient({ fetch: fetcher });
    await expect(
      client.request("/api/test", z.unknown(), { signal: controller.signal }),
    ).rejects.toMatchObject({ name: "AbortError" });
  });
});
describe("기존 인증 계약", () => {
  it("이메일 공백·대소문자를 정규화한다", () => {
    expect(
      loginSchema.parse({ email: " User@Example.com ", password: "a" }).email,
    ).toBe("user@example.com");
  });
  it("비밀번호 확인과 필수 동의를 검사한다", () => {
    expect(
      signupSchema.safeParse({
        email: "a@example.com",
        password: "abc12345",
        passwordConfirm: "different",
        agreeTerms: true,
        agreePrivacy: true,
      }).success,
    ).toBe(false);
    expect(
      signupSchema.safeParse({
        email: "a@example.com",
        password: "abc12345",
        passwordConfirm: "abc12345",
        agreeTerms: false,
        agreePrivacy: true,
      }).success,
    ).toBe(false);
  });
  it.each([
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "/login",
    "/signup",
  ])("외부·순환 복귀 경로 %s를 차단한다", (value) => {
    expect(safeReturnTo(value)).toBe("/stores");
  });
  it("내부 상품 복귀 경로를 보존한다", () => {
    expect(safeReturnTo("/stores/1/products/2?tab=plan")).toBe(
      "/stores/1/products/2?tab=plan",
    );
  });
  it("me는 user 래퍼 없이 읽고 login은 래퍼를 읽는다", async () => {
    const user = {
      id: 1,
      email: "test@example.com",
      role: "owner",
      provider: "email",
      hasStore: false,
    };
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(user))
      .mockResolvedValueOnce(json({ user }));
    const auth = createAuthApi(
      new ApiClient({ fetch: fetcher, cookie: () => "seelo_csrf=token" }),
    );
    expect(await auth.me()).toEqual(user);
    expect(
      (await auth.login({ email: user.email, password: "test" })).user,
    ).toEqual(user);
  });
});
describe("현재 쇼핑몰 서버 계약", () => {
  it("실제 shops 경로·응답 래퍼를 사용한다", async () => {
    const shops = await createDemoGateway().stores();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json({ shops }));
    const gateway = createHttpGateway(new ApiClient({ fetch: fetcher }));
    expect(await gateway.stores()).toEqual(shops);
    expect(fetcher.mock.calls[0][0]).toBe("/api/commerce/shops");
  });
  it("원본·정비안·쓰기 이력 응답을 조합한다", async () => {
    const demo = createDemoGateway();
    const store = (await demo.stores())[0];
    const product = (await demo.products(store.id, { page: 1, query: "" }))
      .items[0];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (path) =>
        String(path).endsWith("/plans")
          ? json({ plans: [] })
          : String(path).includes("/products/")
            ? json(product)
            : json(store),
      );
    const gateway = createHttpGateway(new ApiClient({ fetch: fetcher }));
    const workspace = await gateway.workspace(store.id, product.id);
    expect(workspace.product.id).toBe(product.id);
    expect(workspace.plans).toEqual([]);
  });
  it("다른 스토어의 상품 응답을 표시하지 않는다", async () => {
    const demo = createDemoGateway();
    const stores = await demo.stores();
    const product = (await demo.products(stores[1].id, { page: 1, query: "" }))
      .items[0];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (path) =>
        String(path).endsWith("/plans")
          ? json({ plans: [] })
          : String(path).includes("/products/")
            ? json(product)
            : json(stores[0]),
      );
    await expect(
      createHttpGateway(new ApiClient({ fetch: fetcher })).workspace(
        stores[0].id,
        product.id,
      ),
    ).rejects.toMatchObject({ code: "CONTRACT_MISMATCH" });
  });
  it("등록 요청에 실제 서버 필드만 보낸다", async () => {
    const store = (await createDemoGateway().stores())[0];
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json(store));
    const gateway = createHttpGateway(
      new ApiClient({ fetch: fetcher, cookie: () => "seelo_csrf=token" }),
    );
    await gateway.addStore({
      platform: "cafe24",
      externalId: "test-mall",
      name: "테스트",
      shopNo: 1,
    });
    expect(JSON.parse(fetcher.mock.calls[0][1]!.body as string)).toEqual({
      platform: "cafe24",
      externalId: "test-mall",
      name: "테스트",
      shopNo: 1,
    });
  });
  it("쇼핑몰 API 미연결을 시연 데이터로 대체하지 않는다", async () => {
    const gateway = createHttpGateway(
      new ApiClient({
        fetch: vi
          .fn<typeof fetch>()
          .mockResolvedValue(new Response("미연결", { status: 404 })),
      }),
    );
    await expect(gateway.stores()).rejects.toMatchObject({ status: 404 });
  });
  it("연결 해제와 정비안별 쓰기 이력 경로를 사용한다", async () => {
    const store = (await createDemoGateway().stores())[0];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ ...store, managerStatus: "revoked" }))
      .mockResolvedValueOnce(json({ writes: [] }));
    const gateway = createHttpGateway(
      new ApiClient({ fetch: fetcher, cookie: () => "seelo_csrf=token" }),
    );
    expect((await gateway.disconnect(store.id)).managerStatus).toBe("revoked");
    expect(fetcher.mock.calls[0][0]).toBe(
      `/api/commerce/shops/${store.id}/disconnect`,
    );
    expect(fetcher.mock.calls[0][1]!.method).toBe("POST");
    expect(await gateway.writes(7)).toEqual([]);
    expect(fetcher.mock.calls[1][0]).toBe("/api/commerce/plans/7/writes");
  });
  it("가져온 상품 검색·페이지를 서버에 요청한다", async () => {
    const demo = createDemoGateway();
    const product = (await demo.products(1, { page: 1, query: "" })).items[0];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        json({ products: [product], page: 2, pageSize: 20, total: 21 }),
      )
      .mockResolvedValueOnce(
        json({
          products: [{ ...product, shopId: 2 }],
          page: 1,
          pageSize: 20,
          total: 1,
        }),
      );
    const gateway = createHttpGateway(new ApiClient({ fetch: fetcher }));
    const page = await gateway.products(1, { page: 2, query: " 텀블러 " });
    expect(page).toMatchObject({ page: 2, total: 21 });
    const url = new URL(String(fetcher.mock.calls[0][0]), "https://seelo.test");
    expect(url.pathname).toBe("/api/commerce/shops/1/products");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      page: "2",
      pageSize: "20",
      query: "텀블러",
    });
    await expect(
      gateway.products(1, { page: 1, query: "" }),
    ).rejects.toMatchObject({ code: "CONTRACT_MISMATCH" });
  });
  it("스토어 주소만 보내고 판별은 서버에 맡긴다", async () => {
    const demo = createDemoGateway();
    const store = (await demo.stores())[0];
    const product = (await demo.products(1, { page: 1, query: "" })).items[0];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(store))
      .mockResolvedValueOnce(json(product));
    const gateway = createHttpGateway(
      new ApiClient({ fetch: fetcher, cookie: () => "seelo_csrf=token" }),
    );
    await gateway.addStore({ storeUrl: "https://smartstore.naver.com/seelo" });
    expect(JSON.parse(fetcher.mock.calls[0][1]!.body as string)).toEqual({
      storeUrl: "https://smartstore.naver.com/seelo",
    });
    await gateway.importProduct(1, {
      productUrl:
        "https://seelo-demo.cafe24.com/product/detail.html?product_no=9",
    });
    expect(JSON.parse(fetcher.mock.calls[1][1]!.body as string)).toEqual({
      productUrl:
        "https://seelo-demo.cafe24.com/product/detail.html?product_no=9",
    });
  });
  it("브라우저 수집 202 응답을 작업으로 받고 상태를 조회한다", async () => {
    const job = {
      id: 5,
      shopId: 1,
      productId: null,
      planId: null,
      kind: "collect",
      status: "queued",
      errorCode: null,
      result: {},
      stale: false,
      createdAt: "2026-11-25T00:00:00+00:00",
      startedAt: null,
      finishedAt: null,
    };
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ job }, 202))
      .mockResolvedValueOnce(json({ ...job, status: "succeeded" }))
      .mockResolvedValueOnce(json({ job: { ...job, shopId: 2 } }, 202));
    const gateway = createHttpGateway(
      new ApiClient({ fetch: fetcher, cookie: () => "seelo_csrf=token" }),
    );
    const result = await gateway.importProduct(1, { externalId: "9" });
    expect(result).toMatchObject({ kind: "job", job: { id: 5 } });
    expect((await gateway.job(5)).status).toBe("succeeded");
    expect(fetcher.mock.calls[1][0]).toBe("/api/commerce/jobs/5");
    await expect(
      gateway.importProduct(1, { externalId: "9" }),
    ).rejects.toMatchObject({ code: "CONTRACT_MISMATCH" });
  });
  it("가게 고유값 기록과 플랫폼 상품 목록 작업 경로를 사용한다", async () => {
    const store = (await createDemoGateway().stores())[0];
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(store))
      .mockResolvedValueOnce(
        json(
          {
            job: {
              id: 3,
              shopId: 1,
              productId: null,
              planId: null,
              kind: "catalog",
              status: "queued",
              errorCode: null,
              result: {},
              stale: false,
              createdAt: "2026-11-25T00:00:00+00:00",
              startedAt: null,
              finishedAt: null,
            },
          },
          202,
        ),
      );
    const gateway = createHttpGateway(
      new ApiClient({ fetch: fetcher, cookie: () => "seelo_csrf=token" }),
    );
    await gateway.manager(1, "verified", {
      storeName: " 시험몰 ",
      storeId: "",
    });
    expect(JSON.parse(fetcher.mock.calls[0][1]!.body as string)).toEqual({
      status: "verified",
      storeName: "시험몰",
    });
    const result = await gateway.requestCatalog(1);
    expect(result.kind).toBe("job");
    expect(fetcher.mock.calls[1][0]).toBe("/api/commerce/shops/1/catalog");
  });
  it("AI 준비 요청을 상품 준비 경로로 보낸다", async () => {
    const demo = createDemoGateway();
    const store = (await demo.stores())[0];
    const product = (await demo.products(1, { page: 1, query: "" })).items[0];
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (path) => {
      const url = String(path);
      if (url.endsWith("/prepare"))
        return json({ result: { planId: 1, planStatus: "draft" } }, 201);
      if (url.endsWith("/plans")) return json({ plans: [] });
      if (url.includes("/products/")) return json(product);
      return json(store);
    });
    const gateway = createHttpGateway(
      new ApiClient({ fetch: fetcher, cookie: () => "seelo_csrf=token" }),
    );
    await gateway.command(1, product.id, {
      action: "prepare",
      sourceUrls: ["https://maker.example.com/a"],
    });
    const call = fetcher.mock.calls.find(([path]) =>
      String(path).endsWith("/prepare"),
    )!;
    expect(call[0]).toBe(`/api/commerce/products/${product.id}/prepare`);
    expect(JSON.parse(call[1]!.body as string)).toEqual({
      sourceUrls: ["https://maker.example.com/a"],
    });
  });
  it("진단 질문 세트·측정·비교 경로를 사용한다", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        json({ error: { code: "NOT_FOUND", message: "없음" } }, 404),
      );
    const gateway = createHttpGateway(
      new ApiClient({ fetch: fetcher, cookie: () => "seelo_csrf=token" }),
    );
    await gateway
      .createMeasureSet(4, {
        name: "기본",
        queries: [{ id: "G01", question: "보온 텀블러를 찾아줘" }],
      })
      .catch(() => undefined);
    await gateway
      .runMeasure(5, { label: "B0", provider: "gemini", repeats: 3 })
      .catch(() => undefined);
    await gateway.compareRuns(6, 7).catch(() => undefined);
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual([
      "/api/commerce/products/4/measure-sets",
      "/api/commerce/measure-sets/5/runs",
      "/api/commerce/measure-compare?before=6&after=7",
    ]);
    expect(JSON.parse(fetcher.mock.calls[1][1]!.body as string)).toEqual({
      label: "B0",
      provider: "gemini",
      repeats: 3,
    });
  });
  it("OAuth 이동 주소를 카페24 공식 호스트로 제한한다", async () => {
    const gateway = createHttpGateway(
      new ApiClient({
        fetch: vi
          .fn<typeof fetch>()
          .mockResolvedValue(
            json({ authorizationUrl: "https://other.example/authorize" }),
          ),
        cookie: () => "seelo_csrf=token",
      }),
    );
    await expect(gateway.authorize(1)).rejects.toMatchObject({
      code: "CONTRACT_MISMATCH",
    });
  });
});
