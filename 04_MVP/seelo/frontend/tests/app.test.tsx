import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { MemoryRouter } from "react-router-dom";
import { StrictMode } from "react";
import { AppRoutes } from "../src/app/router";
import {
  createRuntime,
  demoUsers,
  RuntimeProvider,
  sessionKey,
  switchDemoPersona,
  type Runtime,
} from "../src/app/runtime";
import { keys } from "../src/app/commerce";

afterEach(() => {
  cleanup();
  // 시연 화면 선택은 세션 저장소에 남는다. 테스트마다 사장님 화면에서 시작한다.
  sessionStorage.clear();
});
// 운영자 화면으로 시작하는 시연 실행 환경.
function operatorRuntime() {
  const runtime = createRuntime("demo");
  runtime.queryClient.setQueryData(sessionKey, demoUsers.operator);
  return runtime;
}
const asOperator = (runtime: Runtime) =>
  act(() => switchDemoPersona(runtime, "operator"));
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
const mainNav = () =>
  within(screen.getByRole("navigation", { name: "주요 메뉴" }));
// 근거를 직접 넣고 정비안을 만든 뒤 정비안 검토 화면에서 승인한다.
async function draftAndApprove() {
  fireEvent.click(await screen.findByText("정보를 직접 넣을게요"));
  change("확인한 값", "일상용");
  change("근거 주소", "https://example.com/source");
  change("값이 포함된 인용문", "일상용 텀블러입니다.");
  fireEvent.click(screen.getByRole("button", { name: "근거 저장" }));
  await screen.findByText("일상용");
  fireEvent.click(
    screen.getByRole("button", { name: "선택한 항목으로 정비안 생성" }),
  );
  fireEvent.click(await screen.findByRole("link", { name: /정비안 확인하기/ }));
  fireEvent.click(await screen.findByRole("button", { name: /승인하기/ }));
  fireEvent.click(
    within(await screen.findByRole("dialog")).getByRole("button", {
      name: "정비안 승인",
    }),
  );
}
describe("화면 통합", () => {
  it("랜딩은 시안 문구와 바꾼 FAQ 답을 보여 주고 로그인으로 이어진다", async () => {
    const runtime = createRuntime("api");
    runtime.queryClient.setQueryData(sessionKey, null);
    mount("/", runtime);
    await screen.findByRole("heading", {
      name: "AI 검색에서 우리 상품이 답이 되도록",
    });
    expect(
      screen.getByText(
        "쇼핑몰 주소만 등록하면 seelo가 현재 상세페이지와 공개 자료를 먼저 조사하고, 확인되지 않은 정보만 여쭤봅니다.",
      ),
    ).toBeDefined();
    expect(screen.getByRole("link", { name: "로그인" })).toBeDefined();
    // 시안의 히어로처럼 무료 진단 버튼이 준비 중 안내를 연다.
    const diagnosis = screen.getByRole("button", { name: "무료 진단받기" });
    expect(diagnosis.getAttribute("popovertarget")).toBe("diagnosis-notice");
    expect(document.getElementById("diagnosis-notice")?.textContent).toBe(
      "무료 진단은 준비 중이에요.",
    );
  });
  it("홈은 스토어 위임·보고서 같은 할 일을 카드로 모은다", async () => {
    mount("/home");
    const todos = await screen.findByRole("list", { name: "지금 할 일" });
    await waitFor(() =>
      expect(todos.textContent).toContain("보고서가 준비됐어요"),
    );
    expect(todos.textContent).toContain("권한 위임을 마쳐 주세요");
    expect(
      screen.getByRole("list", { name: "진행 중 목록" }).textContent,
    ).toContain("권한 확인 중 시연 스토어");
  });
  it.each([
    [3, "seelo 담당자를 대행사 매니저로 초대", "판매자센터 열기"],
    [1, "seelo 전용 부운영자 만들기", "카페24 관리자 열기"],
  ])(
    "연결 전 스토어 %i에 플랫폼별 위임 순서를 보여 준다",
    async (id, step, admin) => {
      const runtime = createRuntime("demo");
      const store = await runtime.gateway.store(id);
      runtime.gateway.store = vi.fn().mockResolvedValue({
        ...store,
        editingMode: "browser",
        managerStatus: "not_requested",
      });
      mount(`/stores/${id}`, runtime);
      const steps = await screen.findByRole("list", { name: "권한 위임 순서" });
      expect(steps.textContent).toContain(step);
      expect(screen.getByRole("link", { name: admin })).toBeDefined();
    },
  );
  it("초대를 보내면 확인 대기 화면으로 바뀐다", async () => {
    mount("/stores/3");
    fireEvent.click(
      await screen.findByRole("button", { name: "초대를 보냈어요" }),
    );
    await screen.findByText("seelo가 권한을 확인하고 있어요");
  });
  it("근거 저장 → 생성 → 승인 → 운영자 반영 → 복구를 실행한다", async () => {
    const runtime = mount("/stores/1/products/11");
    await draftAndApprove();
    // 판매자 화면에는 반영 버튼이 없다. 운영자 화면에서 반영한다.
    await screen.findByText("seelo가 확인하고 반영할게요");
    expect(
      screen.queryByRole("button", { name: "승인한 변경 적용" }),
    ).toBeNull();
    await asOperator(runtime);
    fireEvent.click(
      await screen.findByRole("button", { name: "승인한 변경 적용" }),
    );
    await screen.findByText("쇼핑몰에 반영했어요");
    fireEvent.click(
      screen.getByRole("button", { name: "수정 전으로 되돌리기" }),
    );
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "원본 값 복구",
      }),
    );
    await screen.findByText("수정 전으로 되돌렸어요");
    expect(runtime.queryClient.getQueryData(keys.store(1))).toMatchObject({
      apiStatus: "write_verified",
    });
  });
  it("연결 해제는 확인한 뒤에만 실행하고 상품 추가를 막는다", async () => {
    mount("/stores/1/settings");
    fireEvent.click(await screen.findByRole("button", { name: "연결 해제" }));
    const dialog = within(screen.getByRole("dialog"));
    const confirm = dialog.getByRole("button", { name: "연결 해제" });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(
      dialog.getByLabelText("이 스토어의 seelo 연결을 해제합니다."),
    );
    fireEvent.click(confirm);
    await screen.findByRole("heading", { name: "API 연결" });
    expect(screen.queryByRole("button", { name: "상품 추가" })).toBeNull();
    expect(screen.queryByRole("button", { name: "불러오기" })).toBeNull();
  });
  it("반영한 정비안의 쓰기 이력을 본다", async () => {
    const runtime = mount("/stores/1/products/11");
    await draftAndApprove();
    await screen.findByText("seelo가 확인하고 반영할게요");
    await asOperator(runtime);
    fireEvent.click(
      await screen.findByRole("button", { name: "승인한 변경 적용" }),
    );
    await screen.findByText("쇼핑몰에 반영했어요");
    // 정비안이 하나뿐이면 지난 정비안 목록 없이 이번 정비안에서 연다.
    expect(screen.queryByRole("list", { name: "정비안 이력" })).toBeNull();
    fireEvent.click(screen.getByRole("link", { name: "자세히" }));
    await screen.findByRole("list", { name: /의 쓰기 이력$/ });
    expect(await screen.findByText("쇼핑몰 반영")).toBeDefined();
    expect(screen.queryByRole("button", { name: /승인하기/ })).toBeNull();
  });
  it("스토어 주소만 입력해 플랫폼을 알아보고 등록한다", async () => {
    mount("/stores/new");
    change("스토어 주소", "https://smartstore.naver.com/newstore/products/1");
    await screen.findByText("newstore", { exact: false });
    fireEvent.click(screen.getByRole("button", { name: "스토어 등록" }));
    await screen.findByRole("heading", { name: "newstore" });
  });
  it("운영자는 고객 승인 대기를 보고 승인하지 못한다", async () => {
    const runtime = mount("/stores/1/products/11");
    fireEvent.click(
      await screen.findByRole("button", {
        name: "AI가 조사하고 정비안 만들기",
      }),
    );
    fireEvent.change(
      await screen.findByLabelText("이 상품의 크기 정보를 알려 주세요."),
      { target: { value: "500mL" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "답변 저장" }));
    await screen.findByText("정비안이 준비됐어요");
    // 사장님 화면에는 운영 관리 메뉴가 없다. 시연 띠에서 운영자 화면으로 바꾼다.
    expect(mainNav().queryByRole("link", { name: "운영 관리" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "운영자 화면" }));
    await screen.findByRole("heading", { name: "운영 관리" });
    expect(mainNav().queryByRole("link", { name: "홈" })).toBeNull();
    fireEvent.click(await screen.findByRole("tab", { name: /고객 승인 대기/ }));
    const list = await screen.findByRole("list", { name: "작업 대기 목록" });
    expect(list.textContent).toContain("고객 승인 대기");
    expect(list.textContent).toContain("demo@example.com");
    expect(runtime.queryClient.getQueryData(sessionKey)).toMatchObject({
      role: "admin",
    });
    fireEvent.click(within(list).getAllByRole("link")[0]);
    await screen.findByText("판매자 승인을 기다려요.");
    fireEvent.click(screen.getByRole("link", { name: "정비안 보기" }));
    await screen.findByText("고객 승인 대기 · 운영자는 승인할 수 없습니다.");
    expect(screen.queryByRole("button", { name: /승인하기/ })).toBeNull();
  });
  it("관리자 화면 수집 작업이 끝나면 가져온 상품으로 이동한다", async () => {
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
    mount("/stores/1", runtime);
    fireEvent.click(await screen.findByRole("button", { name: "상품 추가" }));
    await screen.findByLabelText("상품번호 또는 카페24 상품 주소");
    change("상품번호 또는 카페24 상품 주소", "1001");
    fireEvent.click(screen.getByRole("button", { name: "불러오기" }));
    await screen.findByRole("heading", { name: product.name });
    expect(runtime.gateway.job).toHaveBeenCalledWith(77, expect.anything());
  });
  it("스토어 화면은 상품 목록을 먼저 보여 주고 상품 추가는 눌러서 연다", async () => {
    mount("/stores/1");
    const list = await screen.findByRole("list", { name: "불러온 상품 목록" });
    await waitFor(() =>
      expect(list.textContent).toContain("시연용 보온병 750mL"),
    );
    // 연결을 마친 스토어에는 연결 단계와 상품 추가 입력칸을 처음부터 펼치지 않는다.
    expect(
      screen.queryByRole("group", { name: "스토어 연결 단계" }),
    ).toBeNull();
    expect(
      screen.queryByLabelText("상품번호 또는 카페24 상품 주소"),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "상품 추가" }));
    await screen.findByLabelText("상품번호 또는 카페24 상품 주소");
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    await waitFor(() =>
      expect(
        screen.queryByLabelText("상품번호 또는 카페24 상품 주소"),
      ).toBeNull(),
    );
    // 스토어 화면에는 상품 목록 하나만 둔다. AI 노출은 메뉴에서 본다.
    expect(screen.queryByRole("tablist")).toBeNull();
  });
  it("AI 노출 메뉴는 상품마다 숫자만 보여 주고 상품을 누르면 자세히 연다", async () => {
    mount("/home");
    fireEvent.click(
      await within(
        await screen.findByRole("navigation", { name: "주요 메뉴" }),
      ).findByRole("link", { name: "AI 노출" }),
    );
    await screen.findByText("1개 상품이 AI 답변에 더 자주 나와요");
    const list = await screen.findByRole("list", {
      name: "카페24 시연 스토어 상품별 노출",
    });
    const rows = within(list).getAllByRole("link");
    const bottle = rows.find((row) =>
      row.textContent?.includes("시연용 보온병 750mL"),
    )!;
    expect(bottle.textContent).toContain("56%");
    expect(bottle.textContent).toContain("+44%p");
    const tumbler = rows.find((row) =>
      row.textContent?.includes("시연용 텀블러 500mL"),
    )!;
    // 측정 전 상품은 한 번만 말한다. 빈 값(-)을 칸마다 늘어놓지 않는다.
    expect(tumbler.textContent?.match(/측정 전/g)).toHaveLength(1);
    expect(tumbler.textContent).not.toContain("-");
    // 줄 안에는 상태 배지·보고서·측정 버튼을 두지 않는다.
    expect(within(list).queryByRole("button")).toBeNull();
    expect(within(list).queryByText("전후 비교 가능")).toBeNull();
    fireEvent.click(bottle);
    const chatgpt = await screen.findByRole("region", { name: "ChatGPT 노출" });
    expect(chatgpt.textContent).toContain("+44%p");
  });
  it("상품 화면은 정비와 AI 노출을 탭으로 나누고 측정 관리는 운영자에게만 보인다", async () => {
    mount("/stores/1/products/13?tab=exposure");
    const chatgpt = await screen.findByRole("region", { name: "ChatGPT 노출" });
    expect(chatgpt.textContent).toContain("상품 발견");
    expect(chatgpt.textContent).toContain("+44%p");
    expect(
      screen.getByRole("link", { name: "전후 보고서 보기" }),
    ).toBeDefined();
    expect(screen.queryByRole("link", { name: "측정 관리" })).toBeNull();
    // 정비 탭의 확인한 정보는 AI 노출 탭에서 보이지 않는다.
    expect(screen.queryByRole("region", { name: "확인한 정보" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "정비" }));
    await screen.findByRole("region", { name: "확인한 정보" });
    // 판매자 화면에는 되돌리기·측정 같은 운영자 행동이 없다.
    expect(
      screen.queryByRole("button", { name: "수정 전으로 되돌리기" }),
    ).toBeNull();
    cleanup();
    mount("/stores/1/products/13?tab=exposure", operatorRuntime());
    expect(
      await screen.findByRole("link", { name: "측정 관리" }),
    ).toBeDefined();
  });
  it("쇼핑몰 상품 목록을 불러온 상품과 구분하고 골라 가져온다", async () => {
    const runtime = createRuntime("demo");
    const store = await runtime.gateway.store(1);
    runtime.gateway.store = vi
      .fn()
      .mockResolvedValue({ ...store, editingMode: "browser" });
    mount("/stores/1?view=catalog", runtime);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "쇼핑몰 상품 목록 가져오기",
      }),
    );
    const list = await screen.findByRole("list", { name: "플랫폼 상품" });
    await waitFor(() => expect(list.textContent).toContain("1002"));
    expect(
      screen.getByRole("link", { name: "가져온 상품 열기" }),
    ).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "가져오기" }));
    await screen.findByRole("heading", { name: "시연 상품 1002" });
    expect(screen.getByText("모델·옵션: DEMO-1002")).toBeDefined();
  });
  it("AI가 먼저 조사하고 필요한 정보만 물은 뒤 답변하면 다시 만든다", async () => {
    mount("/stores/1/products/11");
    fireEvent.click(
      await screen.findByRole("button", {
        name: "AI가 조사하고 정비안 만들기",
      }),
    );
    const question = await screen.findByLabelText(
      "이 상품의 크기 정보를 알려 주세요.",
    );
    // 판매자는 정비 필드나 필수 사실을 고르지 않았다.
    fireEvent.change(question, { target: { value: "500mL" } });
    fireEvent.click(screen.getByRole("button", { name: "답변 저장" }));
    await screen.findByText("정비안이 준비됐어요");
    expect(
      screen.queryByLabelText("이 상품의 크기 정보를 알려 주세요."),
    ).toBeNull();
    expect(
      within(screen.getByRole("region", { name: "확인한 정보" })).getByText(
        "500mL",
      ),
    ).toBeDefined();
  });
  it("측정 실패는 무효로 표시하고 같은 세트 회차를 보고서로 비교한다", async () => {
    mount("/stores/1/products/11/measure", operatorRuntime());
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
    fireEvent.click(await screen.findByRole("link", { name: "보고서로 보기" }));
    const compare = await screen.findByRole("table", { name: "전후 비교" });
    expect(compare.textContent).toContain("정상 응답 부족·비교 보류");
  });
  it("보고서는 정비 전후 비율과 바뀐 내용을 함께 보여 준다", async () => {
    mount("/stores/1/products/13/report");
    const chatgpt = await screen.findByRole("region", {
      name: "ChatGPT 전후 비교",
    });
    await waitFor(() => expect(chatgpt.textContent).toContain("상품 발견"));
    expect(chatgpt.textContent).toContain("+44%p");
    expect(
      await screen.findByRole("region", { name: "요약 설명" }),
    ).toBeDefined();
  });
  it("계정 탈퇴는 확인 문구를 정확히 입력해야 누를 수 있다", async () => {
    mount("/account");
    await screen.findByText("로그인 정보");
    fireEvent.click(screen.getByRole("button", { name: "탈퇴" }));
    const dialog = within(screen.getByRole("dialog"));
    const confirm = dialog.getByRole("button", { name: "탈퇴" });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(dialog.getByRole("textbox"), {
      target: { value: "탈퇴합니다" },
    });
    expect((confirm as HTMLButtonElement).disabled).toBe(false);
  });
  it("미로그인 접근은 원래 상품 경로를 보존한다", async () => {
    const runtime = createRuntime("api");
    runtime.queryClient.setQueryData(sessionKey, null);
    mount("/stores/1/products/11?tab=plan", runtime);
    await screen.findByRole("heading", { name: "로그인" });
    expect(
      screen.queryByRole("heading", { name: "시연용 텀블러 500mL" }),
    ).toBeNull();
    expect(screen.getByRole("link", { name: "가입" })).toBeDefined();
  });
  it("시연 모드는 인증 페이지에서도 실제 API를 호출하지 않는다", async () => {
    const fetcher = vi.spyOn(globalThis, "fetch");
    mount("/verify-email/demo-token");
    await screen.findByRole("heading", { name: "오늘 할 일" });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("StrictMode에서도 소셜 로그인 전 화면으로 복귀한다", async () => {
    sessionStorage.setItem("seelo-oauth-return", "/stores/2");
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
      /스마트스토어 API는 seelo가 공식 절차로 따로 인증해요/,
    );
    expect(sessionStorage.getItem("seelo-oauth-return")).toBeNull();
  });
  it("로그아웃 성공 때 사용자별 조회 캐시를 비운다", async () => {
    const runtime = createRuntime("api");
    runtime.queryClient.setQueryData(sessionKey, demoUsers.seller);
    runtime.queryClient.setQueryData(["mail-status", "private-ticket"], {
      status: "sent",
    });
    runtime.gateway.stores = vi.fn().mockResolvedValue([]);
    runtime.account.get = vi.fn().mockResolvedValue({
      email: "demo@example.com",
      provider: "email",
      createdAt: "2026-11-01T00:00:00+00:00",
      canChangePassword: true,
    });
    runtime.auth.logout = vi.fn().mockResolvedValue(undefined);
    mount("/account", runtime);
    fireEvent.click(await screen.findByRole("button", { name: "로그아웃" }));
    await waitFor(() =>
      expect(
        runtime.queryClient.getQueryData(["mail-status", "private-ticket"]),
      ).toBeUndefined(),
    );
  });
  it("시연에서 사장님 화면과 운영자 화면은 메뉴부터 나뉜다", async () => {
    mount("/home");
    await screen.findByRole("heading", { name: "오늘 할 일" });
    expect(
      mainNav()
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["홈", "스토어", "AI 노출"]);
    // 시연 계정에는 로그아웃할 계정이 없어 계정 화면에 로그아웃 버튼을 두지 않는다.
    fireEvent.click(screen.getByRole("button", { name: "운영자 화면" }));
    await screen.findByRole("heading", { name: "운영 관리" });
    expect(
      mainNav()
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["운영 관리"]);
    fireEvent.click(screen.getByRole("button", { name: "사장님 화면" }));
    await screen.findByRole("heading", { name: "오늘 할 일" });
  });
  it("운영자가 고객 스토어를 열면 판매자 안내 대신 권한 확인 칸을 본다", async () => {
    mount("/stores/4", operatorRuntime());
    await screen.findByText("판매자가 권한을 줬다고 알려 왔어요");
    expect(screen.getByRole("link", { name: /고객 스토어/ })).toBeDefined();
    expect(
      screen.getByRole("button", { name: "권한 확인 완료" }),
    ).toBeDefined();
    expect(screen.queryByRole("button", { name: "안내 다시 보기" })).toBeNull();
    expect(
      screen.queryByRole("button", { name: "부운영자를 만들었어요" }),
    ).toBeNull();
  });
});
