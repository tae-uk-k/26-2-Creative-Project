import { z } from "zod";
import type { ApiClient } from "../api/client";
import { ApiError } from "../api/client";
import {
  catalogSchema,
  measureCompareSchema,
  measureRunSchema,
  measureSetSchema,
  jobSchema,
  manualSnapshotSchema,
  operatorShopPageSchema,
  operatorTaskSchema,
  planSchema,
  productNoSchema,
  productSchema,
  productTargetSchema,
  publicUrl,
  storeInputSchema,
  storeSchema,
  writeSchema,
  type CommerceGateway,
  type Workspace,
} from "./schemas";
const root = "/api/commerce";
const numeric = (id: number) => String(z.number().int().positive().parse(id));
export function createHttpGateway(client: ApiClient): CommerceGateway {
  const storePath = (id: number) => `${root}/shops/${numeric(id)}`;
  const productPath = (id: number) => `${root}/products/${numeric(id)}`;
  const workspace = async (
    storeId: number,
    productId: number,
    signal?: AbortSignal,
  ): Promise<Workspace> => {
    const [store, product, { plans }] = await Promise.all([
      client.request(storePath(storeId), storeSchema, { signal }),
      client.request(productPath(productId), productSchema, { signal }),
      client.request(
        `${productPath(productId)}/plans`,
        z.object({ plans: z.array(planSchema) }),
        { signal },
      ),
    ]);
    if (
      product.shopId !== store.id ||
      plans.some((plan) => plan.productId !== product.id)
    )
      throw new ApiError(
        409,
        "CONTRACT_MISMATCH",
        "스토어·상품·정비안의 연결이 일치하지 않습니다.",
      );
    const latest = [...plans].sort((left, right) => right.id - left.id)[0];
    const { writes } = latest
      ? await client.request(
          `${root}/plans/${latest.id}/writes`,
          z.object({ writes: z.array(writeSchema) }),
          { signal },
        )
      : { writes: [] };
    return { store, product, plans, writes };
  };
  return {
    stores: async (signal) =>
      (
        await client.request(
          `${root}/shops`,
          z.object({ shops: z.array(storeSchema) }),
          { signal },
        )
      ).shops,
    store: (id, signal) =>
      client.request(storePath(id), storeSchema, { signal }),
    addStore: (input) =>
      client.request(`${root}/shops`, storeSchema, {
        method: "POST",
        body: storeInputSchema.parse(input),
      }),
    manager: (id, status, identity) =>
      client.request(`${storePath(id)}/manager`, storeSchema, {
        method: "POST",
        body: {
          status,
          ...(identity?.storeName?.trim()
            ? { storeName: identity.storeName.trim() }
            : {}),
          ...(identity?.storeId?.trim()
            ? { storeId: identity.storeId.trim() }
            : {}),
        },
      }),
    requestCatalog: async (id) => {
      const result = await client.request(
        `${storePath(id)}/catalog`,
        z.union([z.object({ job: jobSchema }), catalogSchema]),
        { method: "POST", timeoutMs: 100_000 },
      );
      return "job" in result
        ? { kind: "job" as const, job: result.job }
        : { kind: "catalog" as const, catalog: result };
    },
    catalog: (id, signal) =>
      client.request(`${storePath(id)}/catalog`, catalogSchema, { signal }),
    disconnect: (id) =>
      client.request(`${storePath(id)}/disconnect`, storeSchema, {
        method: "POST",
      }),
    writes: async (planId, signal) =>
      (
        await client.request(
          `${root}/plans/${numeric(planId)}/writes`,
          z.object({ writes: z.array(writeSchema) }),
          { signal },
        )
      ).writes,
    operatorShops: (search, signal) => {
      const params = new URLSearchParams({
        page: String(z.number().int().positive().parse(search.page)),
        pageSize: "20",
      });
      if (search.query.trim()) params.set("query", search.query.trim());
      if (search.managerStatus)
        params.set("managerStatus", search.managerStatus);
      return client.request(
        `${root}/operator/shops?${params}`,
        operatorShopPageSchema,
        { signal },
      );
    },
    operatorTasks: async (signal) =>
      (
        await client.request(
          `${root}/operator/tasks`,
          z.object({ tasks: z.array(operatorTaskSchema) }),
          { signal },
        )
      ).tasks,
    measureSets: async (productId, signal) =>
      (
        await client.request(
          `${productPath(productId)}/measure-sets`,
          z.object({ sets: z.array(measureSetSchema) }),
          { signal },
        )
      ).sets,
    createMeasureSet: (productId, input) =>
      client.request(
        `${productPath(productId)}/measure-sets`,
        measureSetSchema,
        {
          method: "POST",
          body: input,
        },
      ),
    measureRuns: async (productId, signal) =>
      (
        await client.request(
          `${productPath(productId)}/measure-runs`,
          z.object({ runs: z.array(measureRunSchema) }),
          { signal },
        )
      ).runs,
    runMeasure: (setId, input) =>
      client.request(
        `${root}/measure-sets/${numeric(setId)}/runs`,
        measureRunSchema,
        { method: "POST", body: input, timeoutMs: 100_000 },
      ),
    compareRuns: (before, after, signal) =>
      client.request(
        `${root}/measure-compare?before=${numeric(before)}&after=${numeric(after)}`,
        measureCompareSchema,
        { signal },
      ),
    authorize: async (id) => {
      const result = await client.request(
        `${storePath(id)}/cafe24/authorize`,
        z.object({ authorizationUrl: publicUrl }),
        { method: "POST" },
      );
      const url = new URL(result.authorizationUrl);
      if (
        !/^[a-z0-9][a-z0-9_-]{1,49}\.cafe24api\.com$/.test(url.hostname) ||
        url.pathname !== "/api/v2/oauth/authorize"
      )
        throw new ApiError(
          409,
          "CONTRACT_MISMATCH",
          "카페24 인증 주소를 확인하지 못했습니다.",
        );
      return result;
    },
    products: async (id, { page, query }, signal) => {
      const params = new URLSearchParams({
        page: String(z.number().int().positive().parse(page)),
        pageSize: "20",
      });
      if (query.trim()) params.set("query", query.trim().slice(0, 200));
      // 서버가 가져온 상품 안에서 검색·페이지를 나눈다.
      const result = await client.request(
        `${storePath(id)}/products?${params}`,
        z.object({
          products: z.array(productSchema),
          page: z.number().int().positive(),
          pageSize: z.number().int().positive(),
          total: z.number().int().nonnegative(),
        }),
        { signal },
      );
      if (result.products.some((product) => product.shopId !== id))
        throw new ApiError(
          409,
          "CONTRACT_MISMATCH",
          "다른 스토어의 상품 응답을 표시하지 않습니다.",
        );
      return {
        items: result.products,
        page: result.page,
        pageSize: result.pageSize,
        total: result.total,
      };
    },
    importProduct: async (id, target) => {
      const result = await client.request(
        `${storePath(id)}/products/import`,
        z.union([z.object({ job: jobSchema }), productSchema]),
        {
          method: "POST",
          body:
            "externalId" in target
              ? { externalId: productNoSchema.parse(target.externalId) }
              : productTargetSchema.parse(target),
        },
      );
      if ("job" in result) {
        if (result.job.shopId !== id || result.job.kind !== "collect")
          throw new ApiError(
            409,
            "CONTRACT_MISMATCH",
            "수집 작업 응답이 이 스토어와 일치하지 않습니다.",
          );
        return { kind: "job", job: result.job };
      }
      return { kind: "product", product: result };
    },
    job: (jobId, signal) =>
      client.request(`${root}/jobs/${numeric(jobId)}`, jobSchema, { signal }),
    manualSnapshot: (id, input) =>
      client.request(
        `${storePath(id)}/products/manual-snapshot`,
        productSchema,
        { method: "POST", body: manualSnapshotSchema.parse(input) },
      ),
    workspace,
    command: async (storeId, productId, command) => {
      const { action, ...rest } = command;
      if (action === "prepare") {
        await client.request(
          `${productPath(productId)}/prepare`,
          z.union([
            z.object({ job: jobSchema }),
            z.object({ result: z.unknown() }),
          ]),
          { method: "POST", body: rest, timeoutMs: 100_000 },
        );
      } else if (
        action === "research" ||
        action === "facts" ||
        action === "answers" ||
        action === "generate"
      ) {
        if (action === "generate")
          await client.request(`${productPath(productId)}/plans`, planSchema, {
            method: "POST",
            body: rest,
            timeoutMs: 70_000,
          });
        else
          await client.request(
            `${productPath(productId)}/${action}`,
            productSchema,
            {
              method: "POST",
              body: rest,
              timeoutMs: action === "research" ? 70_000 : undefined,
            },
          );
      } else {
        const { planId, ...payload } = rest as {
          planId: number;
          [key: string]: unknown;
        };
        // 서버는 상태 잠금으로 중복 쓰기를 차단한다. 변경 요청은 자동 재전송하지 않는다.
        const body =
          action === "approve" ||
          action === "publication" ||
          action === "manual-result"
            ? payload
            : undefined;
        await client.request(
          `${root}/plans/${numeric(planId)}/${action}`,
          planSchema,
          { method: "POST", body, timeoutMs: 100_000 },
        );
      }
      return workspace(storeId, productId);
    },
  };
}
