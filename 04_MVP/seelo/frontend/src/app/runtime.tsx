import { createContext, useContext, type ReactNode } from "react";
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
} from "@tanstack/react-query";
import { ApiClient, ApiError } from "../api/client";
import { createAuthApi, type User } from "../api/auth";
import {
  createAccountApi,
  passwordChangeSchema,
  type AccountApi,
} from "../api/account";
import { createDemoGateway } from "../commerce/demo-gateway";
import { createHttpGateway } from "../commerce/http-gateway";

export const sessionKey = ["session"] as const;
const isCommerce = (query: { queryKey: readonly unknown[] }) =>
  query.queryKey[0] !== "session";
export function createRuntime(mode: "api" | "demo") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        retry: (count, error) =>
          count < 1 &&
          error instanceof ApiError &&
          (error.status === 0 || error.status >= 500),
        refetchOnWindowFocus: true,
      },
      mutations: { retry: false },
    },
  });
  const clearCommerce = async () => {
    await queryClient.cancelQueries({ predicate: isCommerce });
    queryClient.removeQueries({ predicate: isCommerce });
  };
  const client = new ApiClient({
    onUnauthorized: () => {
      void clearCommerce();
      queryClient.setQueryData(sessionKey, null);
    },
  });
  return {
    mode,
    queryClient,
    auth: createAuthApi(client),
    account: mode === "demo" ? demoAccountApi() : createAccountApi(client),
    gateway: mode === "demo" ? createDemoGateway() : createHttpGateway(client),
    clearCommerce,
  };
}
// 시연 모드는 계정을 바꾸지 않는다. 화면 흐름만 확인한다.
function demoAccountApi(): AccountApi {
  return {
    get: async () => ({
      email: "demo@example.com",
      provider: "email",
      createdAt: new Date().toISOString(),
      canChangePassword: true,
    }),
    changePassword: async (input) => {
      passwordChangeSchema.parse(input);
    },
    remove: async () => {
      throw new ApiError(
        409,
        "DEMO_ONLY",
        "시연 모드에서는 탈퇴하지 않습니다.",
      );
    },
  };
}
export type Runtime = ReturnType<typeof createRuntime>;
const RuntimeContext = createContext<Runtime | null>(null);
export function RuntimeProvider({
  runtime,
  children,
}: {
  runtime: Runtime;
  children: ReactNode;
}) {
  return (
    <RuntimeContext.Provider value={runtime}>
      <QueryClientProvider client={runtime.queryClient}>
        {children}
      </QueryClientProvider>
    </RuntimeContext.Provider>
  );
}
export function useRuntime(): Runtime {
  const runtime = useContext(RuntimeContext);
  if (!runtime) throw new Error("실행 환경이 필요합니다.");
  return runtime;
}
const demoUser: User = {
  id: 0,
  email: "demo@example.com",
  role: "admin",
  provider: "email",
  hasStore: false,
};
export function useSession() {
  const runtime = useRuntime();
  return useQuery({
    queryKey: sessionKey,
    queryFn: async ({ signal }) => {
      try {
        return await runtime.auth.me(signal);
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    enabled: runtime.mode === "api",
    initialData: runtime.mode === "demo" ? demoUser : undefined,
    staleTime: 30_000,
  });
}
export function useLogin() {
  const runtime = useRuntime();
  return useMutation({
    mutationFn: runtime.auth.login,
    onSuccess: async ({ user }) => {
      await runtime.queryClient.cancelQueries({ queryKey: sessionKey });
      await runtime.clearCommerce();
      runtime.queryClient.setQueryData(sessionKey, user);
    },
  });
}
export function useLogout() {
  const runtime = useRuntime();
  return useMutation({
    mutationFn: async () => {
      if (runtime.mode === "api") await runtime.auth.logout();
    },
    onSuccess: async () => {
      await runtime.queryClient.cancelQueries();
      runtime.queryClient.clear();
      runtime.queryClient.setQueryData(
        sessionKey,
        runtime.mode === "demo" ? demoUser : null,
      );
    },
  });
}
export async function acceptSession(runtime: Runtime, user: User) {
  await runtime.queryClient.cancelQueries({ queryKey: sessionKey });
  await runtime.clearCommerce();
  runtime.queryClient.setQueryData(sessionKey, user);
}
