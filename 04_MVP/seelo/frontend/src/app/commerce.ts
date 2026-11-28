import { useRef } from "react";
import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import { isRunning, validateCommand } from "../commerce/rules";
import {
  type Command,
  type DelegatedIdentity,
  type ImportResult,
  type Job,
  type ManualSnapshot,
  type MeasureRun,
  type OperatorShopSearch,
  type ProductSearch,
  type ProductTarget,
  type StoreInput,
  type Workspace,
} from "../commerce/schemas";
import { sessionKey, useRuntime } from "./runtime";
import type { User } from "../api/auth";
export const keys = {
  stores: ["commerce", "stores"] as const,
  store: (id: number) => ["commerce", "store", id] as const,
  products: (id: number, search?: ProductSearch) =>
    search
      ? (["commerce", "products", id, search] as const)
      : (["commerce", "products", id] as const),
  workspace: (storeId: number, productId: number) =>
    ["commerce", "workspace", storeId, productId] as const,
  writes: (planId?: number) =>
    planId === undefined
      ? (["commerce", "writes"] as const)
      : (["commerce", "writes", planId] as const),
};
export function useStores() {
  const { gateway } = useRuntime();
  return useQuery({
    queryKey: keys.stores,
    queryFn: ({ signal }) => gateway.stores(signal),
  });
}
export function useAddStore() {
  const runtime = useRuntime();
  return useMutation({
    mutationFn: (input: StoreInput) => runtime.gateway.addStore(input),
    onSuccess: () =>
      runtime.queryClient.invalidateQueries({ queryKey: keys.stores }),
  });
}
export function useStore(id: number) {
  const { gateway } = useRuntime();
  return useQuery({
    queryKey: keys.store(id),
    queryFn: ({ signal }) => gateway.store(id, signal),
    enabled: Number.isSafeInteger(id) && id > 0,
  });
}
export function useProducts(id: number, search: ProductSearch) {
  const { gateway } = useRuntime();
  return useQuery({
    queryKey: keys.products(id, search),
    queryFn: ({ signal }) => gateway.products(id, search, signal),
    enabled: Number.isSafeInteger(id) && id > 0,
  });
}
export function useShopAction(id: number) {
  const runtime = useRuntime();
  const lock = useRef(false);
  const mutation = useMutation({
    mutationFn: async (
      input:
        | {
            action: "manager";
            status: "invited" | "verified" | "revoked";
            identity?: DelegatedIdentity;
          }
        | { action: "authorize" }
        | { action: "disconnect"; confirmed: true },
    ) => {
      if (input.action === "manager") {
        const store = await runtime.gateway.manager(
          id,
          input.status,
          input.identity,
        );
        runtime.queryClient.setQueryData(keys.store(id), store);
      } else if (input.action === "disconnect") {
        if (!input.confirmed)
          throw new ApiError(
            409,
            "INVALID_STATE",
            "연결 해제를 확인해 주세요.",
          );
        const store = await runtime.gateway.disconnect(id);
        runtime.queryClient.setQueryData(keys.store(id), store);
      } else {
        const result = await runtime.gateway.authorize(id);
        if (runtime.mode === "api") return result.authorizationUrl;
      }
    },
    // 권한·연결 상태가 바뀌면 수집·저장 가능 여부를 다시 계산하도록 관련 조회를 모두 새로 받는다.
    onSuccess: () =>
      Promise.all([
        runtime.queryClient.invalidateQueries({ queryKey: keys.stores }),
        runtime.queryClient.invalidateQueries({ queryKey: keys.store(id) }),
        runtime.queryClient.invalidateQueries({ queryKey: keys.products(id) }),
        runtime.queryClient.invalidateQueries({
          queryKey: ["commerce", "workspace", id],
        }),
        runtime.queryClient.invalidateQueries({ queryKey: keys.writes() }),
      ]),
  });
  return {
    ...mutation,
    // 카페24 인증 주소처럼 결과가 있으면 돌려준다.
    run: async (input: Parameters<typeof mutation.mutateAsync>[0]) => {
      if (lock.current) return;
      lock.current = true;
      try {
        return await mutation.mutateAsync(input);
      } finally {
        lock.current = false;
      }
    },
  };
}
export function useImportProduct(id: number) {
  const runtime = useRuntime();
  return useMutation({
    mutationFn: async (
      input: ProductTarget | ManualSnapshot,
    ): Promise<ImportResult> =>
      "fields" in input
        ? {
            kind: "product",
            product: await runtime.gateway.manualSnapshot(id, input),
          }
        : runtime.gateway.importProduct(id, input),
    onSuccess: () =>
      Promise.all([
        runtime.queryClient.invalidateQueries({ queryKey: keys.products(id) }),
        runtime.queryClient.invalidateQueries({ queryKey: keys.store(id) }),
      ]),
  });
}
export function useWorkspace(storeId: number, productId: number) {
  const { gateway } = useRuntime();
  return useQuery({
    queryKey: keys.workspace(storeId, productId),
    queryFn: ({ signal }) => gateway.workspace(storeId, productId, signal),
    enabled:
      Number.isSafeInteger(storeId) &&
      storeId > 0 &&
      Number.isSafeInteger(productId) &&
      productId > 0,
    refetchInterval: (query) =>
      query.state.data && isRunning(query.state.data) ? 3000 : false,
    refetchIntervalInBackground: false,
  });
}
export function useOperatorShops(search: OperatorShopSearch, enabled: boolean) {
  const { gateway } = useRuntime();
  return useQuery({
    queryKey: ["commerce", "operator", "shops", search] as const,
    queryFn: ({ signal }) => gateway.operatorShops(search, signal),
    enabled,
  });
}
export function useOperatorTasks(enabled: boolean) {
  const { gateway } = useRuntime();
  return useQuery({
    queryKey: ["commerce", "operator", "tasks"] as const,
    queryFn: ({ signal }) => gateway.operatorTasks(signal),
    enabled,
  });
}
export const activeJob = (job: Job | null | undefined) =>
  Boolean(job && ["queued", "running"].includes(job.status) && !job.stale);
// 브라우저 작업은 끝날 때까지 3초마다 조회한다. 끝난 작업·중단 의심 작업은 더 조회하지 않는다.
export function useJob(jobId: number | undefined) {
  const { gateway } = useRuntime();
  return useQuery({
    queryKey: ["commerce", "job", jobId] as const,
    queryFn: ({ signal }) => gateway.job(jobId!, signal),
    enabled: jobId !== undefined && Number.isSafeInteger(jobId) && jobId > 0,
    refetchInterval: (query) => (activeJob(query.state.data) ? 3000 : false),
    refetchIntervalInBackground: false,
  });
}
export function useCatalog(storeId: number, enabled: boolean) {
  const { gateway } = useRuntime();
  return useQuery({
    queryKey: ["commerce", "catalog", storeId] as const,
    queryFn: ({ signal }) => gateway.catalog(storeId, signal),
    enabled: enabled && Number.isSafeInteger(storeId) && storeId > 0,
  });
}
export function useWrites(planId: number | undefined) {
  const { gateway } = useRuntime();
  return useQuery({
    queryKey: keys.writes(planId),
    queryFn: ({ signal }) => gateway.writes(planId!, signal),
    enabled: planId !== undefined && Number.isSafeInteger(planId) && planId > 0,
  });
}
// AI 노출 측정. 측정 중인 회차가 있으면 5초마다 다시 조회한다.
export const measureKeys = {
  sets: (productId: number) => ["commerce", "measure-sets", productId] as const,
  runs: (productId: number) => ["commerce", "measure-runs", productId] as const,
  compare: (before: number, after: number) =>
    ["commerce", "measure-compare", before, after] as const,
};
export function useMeasureSets(productId: number) {
  const { gateway } = useRuntime();
  return useQuery({
    queryKey: measureKeys.sets(productId),
    queryFn: ({ signal }) => gateway.measureSets(productId, signal),
    enabled: Number.isSafeInteger(productId) && productId > 0,
  });
}
export function useMeasureRuns(productId: number) {
  const { gateway } = useRuntime();
  return useQuery({
    queryKey: measureKeys.runs(productId),
    queryFn: ({ signal }) => gateway.measureRuns(productId, signal),
    enabled: Number.isSafeInteger(productId) && productId > 0,
    refetchInterval: (query) =>
      query.state.data?.some((run) =>
        ["queued", "running"].includes(run.status),
      )
        ? 5000
        : false,
  });
}
// 여러 상품의 측정 회차를 한 번에 조회한다. AI 노출 현황 목록에서 쓴다.
export function useMeasureRunsMany(productIds: number[]) {
  const { gateway } = useRuntime();
  return useQueries({
    queries: productIds.map((productId) => ({
      queryKey: measureKeys.runs(productId),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        gateway.measureRuns(productId, signal),
      refetchInterval: (query: { state: { data?: MeasureRun[] } }) =>
        query.state.data?.some((run) =>
          ["queued", "running"].includes(run.status),
        )
          ? 5000
          : false,
    })),
  });
}
export function useCompare(pair: { before: number; after: number } | null) {
  const { gateway } = useRuntime();
  return useQuery({
    queryKey: measureKeys.compare(pair?.before ?? 0, pair?.after ?? 0),
    queryFn: ({ signal }) =>
      gateway.compareRuns(pair!.before, pair!.after, signal),
    enabled: pair !== null,
    retry: false,
  });
}
export function useCommand(storeId: number, productId: number) {
  const runtime = useRuntime();
  const flight = useRef(false);
  const mutation = useMutation({
    mutationFn: async (command: Command) => {
      await runtime.queryClient.cancelQueries({
        queryKey: keys.workspace(storeId, productId),
      });
      const workspace = runtime.queryClient.getQueryData<Workspace>(
        keys.workspace(storeId, productId),
      );
      if (!workspace)
        throw new ApiError(409, "NOT_READY", "상품을 먼저 조회해 주세요.");
      const user = runtime.queryClient.getQueryData<User | null>(sessionKey);
      validateCommand(workspace, command, {
        isAdmin: user?.role === "admin",
        userId: user?.id,
      });
      return runtime.gateway.command(storeId, productId, command);
    },
    onSuccess: (workspace) => {
      runtime.queryClient.setQueryData(
        keys.workspace(storeId, productId),
        workspace,
      );
      runtime.queryClient.setQueryData(keys.store(storeId), workspace.store);
      void runtime.queryClient.invalidateQueries({
        queryKey: keys.products(storeId),
      });
      void runtime.queryClient.invalidateQueries({ queryKey: keys.writes() });
    },
    onError: () => {
      void runtime.queryClient.invalidateQueries({
        queryKey: keys.workspace(storeId, productId),
      });
    },
  });
  return {
    ...mutation,
    run: async (command: Command) => {
      if (flight.current)
        throw new ApiError(409, "IN_FLIGHT", "요청을 처리 중입니다.");
      flight.current = true;
      try {
        return await mutation.mutateAsync(command);
      } finally {
        flight.current = false;
      }
    },
  };
}
