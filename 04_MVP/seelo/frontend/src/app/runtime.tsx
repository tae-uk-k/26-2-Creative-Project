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
    gateway:
      mode === "demo"
        ? createDemoGateway(() =>
            queryClient.getQueryData<User | null>(sessionKey),
          )
        : createHttpGateway(client),
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
// 시연 계정은 둘이다. 사장님은 시연 스토어를 모두 가진 판매자, 운영자는 스토어가 없는 seelo 직원이다.
// 실제 서비스처럼 두 화면을 나눠 보여 주려고 한 계정에 두 역할을 겹치지 않는다.
export const demoUsers = {
  seller: {
    id: 0,
    email: "demo@example.com",
    role: "owner",
    provider: "email",
    hasStore: true,
  },
  operator: {
    id: 900,
    email: "operator@example.com",
    role: "admin",
    provider: "email",
    hasStore: false,
  },
} satisfies Record<string, User>;
export type DemoPersona = keyof typeof demoUsers;
// 시연 중 주소를 직접 열어도 고른 화면을 유지한다. 저장소를 못 쓰면 사장님 화면으로 시작한다.
const personaKey = "seelo-demo-persona";
function storedPersona(): DemoPersona {
  try {
    return sessionStorage.getItem(personaKey) === "operator"
      ? "operator"
      : "seller";
  } catch {
    return "seller";
  }
}
function storePersona(persona: DemoPersona | null) {
  try {
    if (persona) sessionStorage.setItem(personaKey, persona);
    else sessionStorage.removeItem(personaKey);
  } catch {
    // 저장하지 못해도 지금 화면은 바뀐다.
  }
}
// 시연 자료와 화면 선택을 모두 처음 상태로 돌린다.
export function restartDemo() {
  storePersona(null);
  window.location.assign("/home");
}
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
    initialData:
      runtime.mode === "demo" ? demoUsers[storedPersona()] : undefined,
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
        runtime.mode === "demo" ? demoUsers[storedPersona()] : null,
      );
    },
  });
}
// 시연에서 사장님·운영자 화면을 바꾼다. 시연 자료는 그대로 두고 조회 결과만 새로 받는다.
// 같은 화면에 머물러도 동작하도록 조회 결과를 지우지 않고 다시 받는다.
export async function switchDemoPersona(
  runtime: Runtime,
  persona: DemoPersona,
) {
  storePersona(persona);
  runtime.queryClient.setQueryData(sessionKey, demoUsers[persona]);
  await runtime.queryClient.invalidateQueries({ predicate: isCommerce });
}
export async function acceptSession(runtime: Runtime, user: User) {
  await runtime.queryClient.cancelQueries({ queryKey: sessionKey });
  await runtime.clearCommerce();
  runtime.queryClient.setQueryData(sessionKey, user);
}
