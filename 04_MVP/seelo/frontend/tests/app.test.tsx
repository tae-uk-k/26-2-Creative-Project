import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { StrictMode } from "react";
import { AppRoutes } from "../src/app/router";
import {
  createRuntime,
  RuntimeProvider,
  sessionKey,
  type Runtime,
} from "../src/app/runtime";
import { keys } from "../src/app/commerce";

afterEach(cleanup);
function mount(path: string, runtime: Runtime = createRuntime("demo")) {
  render(
    <RuntimeProvider runtime={runtime}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </RuntimeProvider>,
  );
  return runtime;
}
const change = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
describe("기본 폼 통합", () => {
  it("카페24 근거 저장 → 생성 → 승인 → 적용 → 복구를 실행한다", async () => {
    const runtime = mount("/stores/1/products");
    fireEvent.click(
      await screen.findByRole("link", { name: "시연용 텀블러 500mL" }),
    );
    await screen.findByRole("button", { name: "근거 저장" });
    change("확인한 값", "일상용");
    change("근거 주소", "https://example.com/source");
    change("값이 포함된 인용문", "일상용 텀블러입니다.");
    fireEvent.click(screen.getByRole("button", { name: "근거 저장" }));
    await screen.findByText(/^용도: 일상용/, { selector: "li" });
    fireEvent.click(
      screen.getByRole("button", { name: "선택한 항목으로 정비안 생성" }),
    );
    await screen.findByText("정비안 승인 대기");
    fireEvent.click(screen.getByLabelText("선택한 변경 값을 확인했습니다."));
    fireEvent.click(screen.getByRole("button", { name: "정비안 승인" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "승인한 변경 적용" }),
    );
    await screen.findByText("저장·API 재조회 완료 · 공개 반영 미확인");
    expect(screen.getByText("PC: 미확인 · 모바일: 미확인")).toBeDefined();
    fireEvent.click(
      screen.getByLabelText("승인한 필드의 수정 전 값으로 복구합니다."),
    );
    fireEvent.click(screen.getByRole("button", { name: "원본 값 복구" }));
    await screen.findByText("원본 값 복구됨 · 공개 반영 미확인");
    expect(runtime.queryClient.getQueryData(keys.store(1))).toMatchObject({
      apiStatus: "write_verified",
    });
  });
  it("연결 해제 후 수집 버튼과 권한 상태를 바로 갱신한다", async () => {
    mount("/stores/1/products");
    const importButton = await screen.findByRole("button", {
      name: "API로 원본 수집",
    });
    expect((importButton as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByText("연결 해제", { selector: "summary" }));
    const submit = screen.getByRole("button", { name: "연결 해제" });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(
      screen.getByLabelText("이 스토어의 seelo 연결을 해제합니다."),
    );
    fireEvent.click(submit);
    await screen.findByText("관리자 권한: 권한 해제됨");
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "API로 원본 수집",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(true),
    );
  });
  it("이전 정비안을 골라 쓰기 이력을 보고 복구한다", async () => {
    mount("/stores/1/products");
    fireEvent.click(
      await screen.findByRole("link", { name: "시연용 텀블러 500mL" }),
    );
    await screen.findByRole("button", { name: "근거 저장" });
    change("확인한 값", "일상용");
    change("근거 주소", "https://example.com/source");
    change("값이 포함된 인용문", "일상용 텀블러입니다.");
    fireEvent.click(screen.getByRole("button", { name: "근거 저장" }));
    await screen.findByText(/^용도: 일상용/, { selector: "li" });
    fireEvent.click(
      screen.getByRole("button", { name: "선택한 항목으로 정비안 생성" }),
    );
    await screen.findByText("정비안 승인 대기");
    fireEvent.click(screen.getByLabelText("선택한 변경 값을 확인했습니다."));
    fireEvent.click(screen.getByRole("button", { name: "정비안 승인" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "승인한 변경 적용" }),
    );
    await screen.findByText("저장·API 재조회 완료 · 공개 반영 미확인");
    const firstPlan = screen
      .getByRole("heading", { level: 3, name: /정비안 #/ })
      .textContent!.match(/#(\d+)/)![1];
    fireEvent.click(
      screen.getByRole("button", { name: "선택한 항목으로 정비안 생성" }),
    );
    await screen.findByText("정비안 승인 대기");
    fireEvent.click(screen.getByRole("link", { name: `#${firstPlan}` }));
    await screen.findByText(`정비안 #${firstPlan} (이전 정비안)`);
    await screen.findByText(`정비안 #${firstPlan}의 쓰기 이력`);
    expect(screen.queryByRole("button", { name: "정비안 승인" })).toBeNull();
    fireEvent.click(
      screen.getByLabelText("승인한 필드의 수정 전 값으로 복구합니다."),
    );
    fireEvent.click(screen.getByRole("button", { name: "원본 값 복구" }));
    await screen.findByText("상태: rolled_back");
  });
  it("스토어 주소만 입력해 플랫폼과 스토어 ID를 등록한다", async () => {
    mount("/stores");
    await screen.findByText("카페24 시연 스토어");
    change("스토어 주소", "https://smartstore.naver.com/newstore/products/1");
    fireEvent.click(screen.getByRole("button", { name: "스토어 등록" }));
    await screen.findByText("스마트스토어 스토어 newstore으로 등록했습니다.");
  });
  it("운영자 화면은 고객 스토어와 고객 승인 대기를 보여 준다", async () => {
    const runtime = mount("/stores/1/products");
    fireEvent.click(
      await screen.findByRole("link", { name: "시연용 텀블러 500mL" }),
    );
    await screen.findByRole("button", { name: "근거 저장" });
    change("확인한 값", "일상용");
    change("근거 주소", "https://example.com/source");
    change("값이 포함된 인용문", "일상용 텀블러입니다.");
    fireEvent.click(screen.getByRole("button", { name: "근거 저장" }));
    await screen.findByText(/^용도: 일상용/, { selector: "li" });
    fireEvent.click(
      screen.getByRole("button", { name: "선택한 항목으로 정비안 생성" }),
    );
    await screen.findByText("정비안 승인 대기");
    fireEvent.click(screen.getByRole("link", { name: "운영자 고객 업무" }));
    await screen.findByRole("heading", { name: "운영자 고객 업무" });
    const list = await screen.findByRole("list", { name: "작업 대기 목록" });
    await waitFor(() => expect(list.textContent).toContain("고객 승인 대기"));
    expect(screen.getAllByText("demo@example.com").length).toBeGreaterThan(0);
    // 다른 사용자(운영자)로 보면 승인 버튼 대신 고객 승인 대기를 표시한다.
    runtime.queryClient.setQueryData(sessionKey, {
      id: 99,
      email: "operator@example.com",
      role: "admin",
      provider: "email",
      hasStore: false,
    });
    fireEvent.click(screen.getByRole("link", { name: /시연용 텀블러 500mL/ }));
    await screen.findByText("고객 승인 대기 · 운영자는 승인할 수 없습니다.");
    expect(screen.queryByRole("button", { name: "정비안 승인" })).toBeNull();
  });
  it("브라우저 수집 작업이 끝나면 가져온 상품으로 이동한다", async () => {
    const runtime = createRuntime("demo");
    const product = (await runtime.gateway.products(1, { page: 1, query: "" }))
      .items[0];
    const job = {
      id: 77,
      shopId: 1,
      productId: null,
      planId: null,
      kind: "collect" as const,
      status: "queued" as const,
      errorCode: null,
      result: {},
      stale: false,
      createdAt: "2026-11-25T00:00:00+00:00",
      startedAt: null,
      finishedAt: null,
    };
    runtime.gateway.importProduct = vi
      .fn()
      .mockResolvedValue({ kind: "job", job });
    runtime.gateway.job = vi.fn().mockResolvedValue({
      ...job,
      status: "succeeded",
      result: { productId: product.id },
    });
    mount("/stores/1/products", runtime);
    const submit = await screen.findByRole("button", {
      name: "API로 원본 수집",
    });
    change("상품번호 또는 카페24 상품 주소", "1001");
    fireEvent.click(submit);
    await screen.findByRole("heading", { name: "상품 정비" });
    expect(runtime.gateway.job).toHaveBeenCalledWith(77, expect.anything());
  });
  it("플랫폼 상품 목록을 가져온 상품과 구분하고 골라 가져온다", async () => {
    const runtime = createRuntime("demo");
    const store = await runtime.gateway.store(1);
    runtime.gateway.store = vi
      .fn()
      .mockResolvedValue({ ...store, editingMode: "browser" });
    mount("/stores/1/products", runtime);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "관리 화면에서 상품 목록 조회",
      }),
    );
    const list = await screen.findByRole("list", { name: "플랫폼 상품" });
    await waitFor(() => expect(list.textContent).toContain("1002"));
    expect(
      screen.getByRole("link", { name: "가져온 상품 열기" }),
    ).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "가져오기" }));
    await screen.findByRole("heading", { name: "상품 정비" });
    await screen.findByText("모델·옵션: DEMO-1002");
  });
  it("AI가 먼저 조사하고 필요한 정보만 물은 뒤 답변하면 다시 만든다", async () => {
    mount("/stores/1/products");
    fireEvent.click(
      await screen.findByRole("link", { name: "시연용 텀블러 500mL" }),
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "AI가 조사하고 정비안 만들기",
      }),
    );
    const question = await screen.findByLabelText(
      "이 상품의 크기 정보를 알려 주세요.",
    );
    // 사장님은 정비 필드나 필수 사실을 고르지 않았다.
    fireEvent.change(question, { target: { value: "500mL" } });
    fireEvent.click(screen.getByRole("button", { name: "답변 저장" }));
    await waitFor(() =>
      expect(
        screen.queryByLabelText("이 상품의 크기 정보를 알려 주세요."),
      ).toBeNull(),
    );
    await screen.findByText("정비안 승인 대기");
    expect(
      screen.getAllByText(/^크기: 500mL/, { selector: "li" }).length,
    ).toBeGreaterThan(0);
  });
  it("AI 노출 진단 실패는 무효로 표시하고 같은 세트 회차를 비교한다", async () => {
    mount("/stores/1/products");
    fireEvent.click(
      await screen.findByRole("link", { name: "시연용 텀블러 500mL" }),
    );
    await screen.findByLabelText("세트 이름");
    change("세트 이름", "기본");
    change(
      '고정 질문 (한 줄에 "ID | 질문" 또는 "ID | 질문군 | 질문")',
      "G01 | 500mL 텀블러를 찾아줘\nG02 | general | 보온 텀블러를 찾아줘",
    );
    fireEvent.click(screen.getByRole("button", { name: "질문 세트 만들기" }));
    await screen.findByText("질문 세트: 기본 (2문항)");
    fireEvent.click(screen.getByRole("button", { name: "측정 시작" }));
    const table = await screen.findByRole("table", { name: "측정 회차" });
    await waitFor(() => expect(table.textContent).toContain("모두 무효"));
    // 정상 응답이 없으면 노출 0%가 아니라 판정 불가로 남긴다.
    expect(table.textContent).toContain("판정 불가");
    expect(table.textContent).not.toContain("0%");
    fireEvent.click(screen.getByRole("button", { name: "측정 시작" }));
    fireEvent.click(await screen.findByRole("button", { name: "전후 비교" }));
    const compare = await screen.findByRole("table", { name: "전후 비교" });
    expect(compare.textContent).toContain("정상 응답 부족·비교 보류");
  });
  it("미로그인 접근은 원래 상품 경로를 보존한다", async () => {
    const runtime = createRuntime("api");
    runtime.queryClient.setQueryData(sessionKey, null);
    mount("/stores/1/products/11?tab=plan", runtime);
    await screen.findByRole("heading", { name: "로그인" });
    expect(screen.queryByRole("heading", { name: "상품 정비" })).toBeNull();
    expect(screen.getByRole("link", { name: "가입" })).toBeDefined();
  });
  it("시연 모드는 인증 페이지에서도 실제 API를 호출하지 않는다", async () => {
    const fetcher = vi.spyOn(globalThis, "fetch");
    mount("/verify-email/demo-token");
    await screen.findByRole("heading", { name: "스토어" });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("StrictMode에서도 소셜 로그인 전 상품 목록으로 복귀한다", async () => {
    sessionStorage.setItem("seelo-oauth-return", "/stores/2/products");
    const runtime = createRuntime("demo");
    render(
      <StrictMode>
        <RuntimeProvider runtime={runtime}>
          <MemoryRouter initialEntries={["/home"]}>
            <AppRoutes />
          </MemoryRouter>
        </RuntimeProvider>
      </StrictMode>,
    );
    await screen.findByText(
      "스마트스토어 API는 공식 판매자 연결 후 관리자가 별도로 인증합니다.",
    );
    expect(sessionStorage.getItem("seelo-oauth-return")).toBeNull();
  });
  it("로그아웃 성공 때 사용자별 조회 캐시를 비운다", async () => {
    const runtime = createRuntime("demo");
    runtime.queryClient.setQueryData(["mail-status", "private-ticket"], {
      status: "sent",
    });
    mount("/stores", runtime);
    await screen.findByText("카페24 시연 스토어");
    fireEvent.click(screen.getByRole("button", { name: "조회 캐시 초기화" }));
    await waitFor(() =>
      expect(
        runtime.queryClient.getQueryData(["mail-status", "private-ticket"]),
      ).toBeUndefined(),
    );
  });
});
