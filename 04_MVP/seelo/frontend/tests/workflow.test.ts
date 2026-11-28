import { describe, expect, it } from "vitest";
import { createDemoGateway } from "../src/commerce/demo-gateway";
import {
  isRunning,
  latestPlan,
  publicationComplete,
  stageOf,
  validChanges,
  validateCommand,
} from "../src/commerce/rules";
import {
  allowedFields,
  platformSchema,
  storeInputSchema,
} from "../src/commerce/schemas";
import type { CommerceGateway, Workspace } from "../src/commerce/schemas";

async function draft(
  storeId = 1,
): Promise<{ gateway: CommerceGateway; workspace: Workspace }> {
  const gateway = createDemoGateway();
  const product = (await gateway.products(storeId, { page: 1, query: "" }))
    .items[0];
  await gateway.command(storeId, product.id, {
    action: "facts",
    facts: [
      {
        key: "model",
        value: "DEMO-T500",
        identity: product.identity,
        sourceUrl: "https://example.com/model",
        quote: "모델 DEMO-T500 자료",
      },
    ],
  });
  const workspace = await gateway.command(storeId, product.id, {
    action: "generate",
    fields: ["description"],
    requiredFacts: ["size"],
    useAi: false,
    allowEditorConversion: false,
  });
  return { gateway, workspace };
}
describe("플랫폼과 승인 경계", () => {
  it("API 미연결이어도 위임 확인과 브라우저 원본으로 자동 수정한다", async () => {
    const { workspace } = await draft();
    const plan = latestPlan(workspace)!;
    plan.status = "approved";
    plan.approval = { fields: ["description"] };
    plan.changes[0].method = "browser";
    workspace.product.snapshotSource = "browser";
    workspace.store.apiStatus = "not_connected";
    workspace.store.managerStatus = "verified";
    workspace.store.automaticWritesEnabled = true;
    const command = { action: "apply", planId: plan.id } as const;
    expect(() => validateCommand(workspace, command)).not.toThrow();
    workspace.store.managerStatus = "revoked";
    expect(() => validateCommand(workspace, command)).toThrow("위임 권한");
  });
  it("두 플랫폼만 등록한다", () => {
    expect(platformSchema.safeParse("shopify").success).toBe(false);
    expect(allowedFields.smartstore).not.toContain("seo.meta_title");
  });
  it("등록은 권한·API 인증을 완료 처리하지 않는다", async () => {
    const gateway = createDemoGateway();
    const input = storeInputSchema.parse({
      platform: "cafe24",
      externalId: "new-mall",
      shopNo: 1,
      name: "신규",
    });
    const store = await gateway.addStore(input);
    expect(store.managerStatus).toBe("not_requested");
    expect(store.apiStatus).toBe("not_connected");
  });
  it("관리자 초대와 API 인증을 분리한다", async () => {
    const gateway = createDemoGateway();
    const store = await gateway.manager(2, "invited");
    expect(store.managerStatus).toBe("invited");
    expect(store.apiStatus).toBe("not_connected");
  });
  it("다른 모델의 근거를 거절한다", async () => {
    const { workspace } = await draft();
    expect(() =>
      validateCommand(workspace, {
        action: "facts",
        facts: [
          {
            key: "model",
            identity: "OTHER",
            value: "value",
            sourceUrl: "https://example.com/item",
            quote: "value",
          },
        ],
      }),
    ).toThrow("같은 근거");
  });
  it("인용문에 없는 값을 거절한다", async () => {
    const { workspace } = await draft();
    expect(() =>
      validateCommand(workspace, {
        action: "facts",
        facts: [
          {
            key: "model",
            identity: workspace.product.identity,
            value: "미확인",
            sourceUrl: "https://example.com/item",
            quote: "다른 값",
          },
        ],
      }),
    ).toThrow();
  });
  it.each(["identity", "quote", "source"] as const)(
    "승인 때 %s 근거도 다시 확인한다",
    async (kind) => {
      const { workspace } = await draft();
      const evidence = latestPlan(workspace)!.changes[0].evidence[0];
      if (kind === "identity") evidence.identity = "OTHER";
      if (kind === "quote") evidence.quote = "근거 없는 값";
      if (kind === "source") evidence.source_url = null;
      expect(validChanges(workspace, latestPlan(workspace)!)).toBe(false);
    },
  );
  it("원본 해시 충돌 때 승인하지 않는다", async () => {
    const { workspace } = await draft();
    expect(() =>
      validateCommand(workspace, {
        action: "approve",
        planId: latestPlan(workspace)!.id,
        snapshotHash: "f".repeat(64),
      }),
    ).toThrow("원본");
  });
  it("원본 값이 바뀌어도 승인하지 않는다", async () => {
    const { workspace } = await draft();
    workspace.product.fields.description = "외부 변경";
    expect(validChanges(workspace, latestPlan(workspace)!)).toBe(false);
  });
  it("지원하지 않는 필드를 거절한다", async () => {
    const { workspace } = await draft(2);
    expect(() =>
      validateCommand(workspace, {
        action: "generate",
        fields: ["seo.meta_title"],
        requiredFacts: [],
        useAi: false,
        allowEditorConversion: false,
      }),
    ).toThrow("지원하는 항목");
  });
  it("서버가 알려 준 현재 실행기 지원 필드만 생성·승인한다", async () => {
    const { workspace } = await draft();
    workspace.product.fieldSupport = {
      mode: "browser",
      automatic: ["description", "summary_description"],
      manual: [],
      unavailable: [
        { field: "mobile_description", reason: "browser_field_not_configured" },
      ],
      conditions: {},
    };
    expect(() =>
      validateCommand(workspace, {
        action: "generate",
        fields: ["description", "mobile_description"],
        requiredFacts: [],
        useAi: false,
        allowEditorConversion: false,
      }),
    ).toThrow("지원하는 항목");
    const plan = latestPlan(workspace)!;
    plan.changes[0].field = "mobile_description";
    plan.changes[0].before = "";
    expect(validChanges(workspace, plan)).toBe(false);
  });
  it("근거가 없으면 변경 없음으로 남긴다", async () => {
    const gateway = createDemoGateway();
    const product = (await gateway.products(1, { page: 1, query: "" }))
      .items[0];
    const workspace = await gateway.command(1, product.id, {
      action: "generate",
      fields: ["description"],
      requiredFacts: ["model"],
      useAi: false,
      allowEditorConversion: false,
    });
    expect(latestPlan(workspace)!.status).toBe("no_changes");
    expect(latestPlan(workspace)!.deferred).toContain("fact:model");
  });
  it("요청하지 않은 누락 답변은 거절한다", async () => {
    const { workspace } = await draft();
    expect(() =>
      validateCommand(workspace, {
        action: "answers",
        answers: { power: "220V" },
      }),
    ).toThrow("답변");
  });
});
describe("저장·공개 확인·복구", () => {
  it("선택해 승인한 필드만 적용한다", async () => {
    const { gateway, workspace } = await draft();
    const next = await gateway.command(1, workspace.product.id, {
      action: "generate",
      fields: ["description", "summary_description"],
      requiredFacts: [],
      useAi: false,
      allowEditorConversion: false,
    });
    const planId = latestPlan(next)!.id;
    await gateway.command(1, workspace.product.id, {
      action: "approve",
      planId,
      snapshotHash: workspace.product.snapshotHash,
      fields: ["summary_description"],
      editorConversionConfirmed: false,
    });
    const applied = await gateway.command(1, workspace.product.id, {
      action: "apply",
      planId,
    });
    expect(Object.keys(applied.writes.at(-1)!.after)).toEqual([
      "summary_description",
    ]);
  });
  it("스마트스토어 API 본문 변경은 승인 시 전환 동의를 다시 받는다", async () => {
    const { gateway, workspace } = await draft(2);
    const next = await gateway.command(2, workspace.product.id, {
      action: "generate",
      fields: ["description"],
      requiredFacts: [],
      useAi: false,
      allowEditorConversion: true,
    });
    expect(() =>
      validateCommand(next, {
        action: "approve",
        planId: latestPlan(next)!.id,
        snapshotHash: next.product.snapshotHash,
        fields: ["description"],
        editorConversionConfirmed: false,
      }),
    ).toThrow("HTML 전환");
  });
  it("재생성해도 누락 질문은 누적 세 개를 넘지 않는다", async () => {
    const { gateway, workspace } = await draft();
    await gateway.command(1, workspace.product.id, {
      action: "generate",
      fields: ["description"],
      requiredFacts: ["material", "weight"],
      useAi: false,
      allowEditorConversion: false,
    });
    const next = await gateway.command(1, workspace.product.id, {
      action: "generate",
      fields: ["description"],
      requiredFacts: ["power", "care"],
      useAi: false,
      allowEditorConversion: false,
    });
    expect(latestPlan(next)!.questions).toHaveLength(0);
    expect(latestPlan(next)!.deferred).toEqual(["fact:power", "fact:care"]);
  });
  it("승인 → 저장·재조회 → 공개 확인 → 복구를 분리한다", async () => {
    const { gateway, workspace } = await draft();
    const productId = workspace.product.id;
    const planId = latestPlan(workspace)!.id;
    await gateway.command(1, productId, {
      action: "approve",
      planId,
      snapshotHash: workspace.product.snapshotHash,
    });
    const applied = await gateway.command(1, productId, {
      action: "apply",
      planId,
    });
    expect(latestPlan(applied)!.status).toBe("applied");
    expect(publicationComplete(latestPlan(applied)!)).toBe(false);
    expect(stageOf(applied)).toContain("공개 반영 미확인");
    const checked = await gateway.command(1, productId, {
      action: "publication",
      planId,
      pcUrl: "https://example.com/pc",
      mobileUrl: "https://example.com/mobile",
      pcMatches: true,
      mobileMatches: true,
      note: "시연 확인",
    });
    expect(publicationComplete(latestPlan(checked)!)).toBe(true);
    const restored = await gateway.command(1, productId, {
      action: "rollback",
      planId,
      confirmed: true,
    });
    expect(latestPlan(restored)!.status).toBe("rolled_back");
    expect(publicationComplete(latestPlan(restored)!)).toBe(false);
    expect(restored.writes.at(-1)!.after.description).toBe(
      workspace.product.fields.description,
    );
  });
  it("이전 정비안은 복구할 수 있지만 승인하지 않는다", async () => {
    const { gateway, workspace } = await draft();
    const productId = workspace.product.id;
    const first = latestPlan(workspace)!.id;
    await gateway.command(1, productId, {
      action: "approve",
      planId: first,
      snapshotHash: workspace.product.snapshotHash,
    });
    await gateway.command(1, productId, { action: "apply", planId: first });
    const next = await gateway.command(1, productId, {
      action: "generate",
      fields: ["description"],
      requiredFacts: [],
      useAi: false,
      allowEditorConversion: false,
    });
    expect(latestPlan(next)!.id).not.toBe(first);
    expect(() =>
      validateCommand(next, {
        action: "rollback",
        planId: first,
        confirmed: true,
      }),
    ).not.toThrow();
    const old = next.plans.find((plan) => plan.id === first)!;
    old.status = "draft";
    expect(() =>
      validateCommand(next, {
        action: "approve",
        planId: first,
        snapshotHash: next.product.snapshotHash,
      }),
    ).toThrow("현재 정비안");
  });
  it("운영자는 승인하지 못하고 고객이 승인한 정비안만 실행한다", async () => {
    const { gateway, workspace } = await draft();
    const planId = latestPlan(workspace)!.id;
    const operator = { isAdmin: true, userId: 99 };
    expect(() =>
      validateCommand(
        workspace,
        {
          action: "approve",
          planId,
          snapshotHash: workspace.product.snapshotHash,
        },
        operator,
      ),
    ).toThrow("소유자");
    expect(() =>
      validateCommand(
        workspace,
        {
          action: "generate",
          fields: ["description"],
          requiredFacts: [],
          useAi: false,
          allowEditorConversion: false,
        },
        operator,
      ),
    ).toThrow("고객 계정");
    const approved = await gateway.command(1, workspace.product.id, {
      action: "approve",
      planId,
      snapshotHash: workspace.product.snapshotHash,
    });
    expect(() =>
      validateCommand(approved, { action: "apply", planId }, operator),
    ).not.toThrow();
    latestPlan(approved)!.approval = { fields: ["description"] };
    expect(() =>
      validateCommand(approved, { action: "apply", planId }, operator),
    ).toThrow("고객이 승인한");
    expect(() =>
      validateCommand(
        approved,
        { action: "apply", planId },
        { isAdmin: false, userId: 99 },
      ),
    ).toThrow("고객이 승인한");
  });
  it("대기·실행 중 작업은 새 명령을 막고 중단 의심 작업은 재조회만 허용한다", async () => {
    const { workspace } = await draft();
    const plan = latestPlan(workspace)!;
    plan.status = "approved";
    plan.approval = { fields: ["description"], approvedBy: 0 };
    plan.job = {
      id: 1,
      shopId: 1,
      productId: workspace.product.id,
      planId: plan.id,
      kind: "apply",
      status: "queued",
      errorCode: null,
      result: {},
      stale: false,
      createdAt: "2026-11-25T00:00:00+00:00",
      startedAt: null,
      finishedAt: null,
    };
    expect(isRunning(workspace)).toBe(true);
    expect(() =>
      validateCommand(workspace, { action: "apply", planId: plan.id }),
    ).toThrow("저장 중");
    plan.job.stale = true;
    expect(isRunning(workspace)).toBe(false);
  });
  it("승인 전 쓰기를 차단한다", async () => {
    const { workspace } = await draft();
    expect(() =>
      validateCommand(workspace, {
        action: "apply",
        planId: latestPlan(workspace)!.id,
      }),
    ).toThrow("승인");
  });
  it("스마트스토어 HTML 전환 미동의는 수동 편집으로 남긴다", async () => {
    const { gateway, workspace } = await draft(2);
    expect(latestPlan(workspace)!.changes[0].method).toBe("manual");
    await gateway.command(2, workspace.product.id, {
      action: "approve",
      planId: latestPlan(workspace)!.id,
      snapshotHash: workspace.product.snapshotHash,
    });
    const result = await gateway.command(2, workspace.product.id, {
      action: "apply",
      planId: latestPlan(workspace)!.id,
    });
    expect(latestPlan(result)!.status).toBe("manual_required");
    expect(result.writes).toHaveLength(0);
  });
  it("서버 쓰기 차단 설정을 확인한다", async () => {
    const { workspace } = await draft();
    latestPlan(workspace)!.status = "approved";
    latestPlan(workspace)!.approval = { fields: ["description"] };
    workspace.store.automaticWritesEnabled = false;
    expect(() =>
      validateCommand(workspace, {
        action: "apply",
        planId: latestPlan(workspace)!.id,
      }),
    ).toThrow("꺼져");
  });
  it("판매자 제공 원본만으로 API 쓰기를 하지 않는다", async () => {
    const { workspace } = await draft();
    latestPlan(workspace)!.status = "approved";
    latestPlan(workspace)!.approval = { fields: ["description"] };
    workspace.product.snapshotSource = "seller_supplied";
    expect(() =>
      validateCommand(workspace, {
        action: "apply",
        planId: latestPlan(workspace)!.id,
      }),
    ).toThrow("직접 수집한 원본");
  });
  it("공개 확인은 관리자만 기록한다", async () => {
    const { workspace } = await draft();
    latestPlan(workspace)!.status = "applied";
    expect(() =>
      validateCommand(
        workspace,
        {
          action: "publication",
          planId: latestPlan(workspace)!.id,
          pcUrl: "https://example.com/pc",
          mobileUrl: "https://example.com/mobile",
          pcMatches: true,
          mobileMatches: true,
          note: "확인",
        },
        false,
      ),
    ).toThrow("관리자");
  });
  it("재조회가 필요한 uncertain 상태에서 재적용을 차단한다", async () => {
    const { workspace } = await draft();
    latestPlan(workspace)!.status = "uncertain";
    expect(() =>
      validateCommand(workspace, {
        action: "apply",
        planId: latestPlan(workspace)!.id,
      }),
    ).toThrow("승인");
    expect(() =>
      validateCommand(workspace, {
        action: "verify",
        planId: latestPlan(workspace)!.id,
      }),
    ).not.toThrow();
  });
});

describe("정비안 글 보기", () => {
  it("사양 목록과 접힘 영역을 한 줄씩 읽는다", async () => {
    const { readableText } = await import("../src/ui/DiffView");
    const html =
      '<section data-seelo="product-facts"><h2>상품 정보</h2><dl><dt>원재료</dt><dd>수박씨 100% (출처: <cite>maker.example.com</cite>)</dd><dt>무게</dt><dd>300g</dd></dl><details><summary>자료 원문 보기</summary><p>“원재료: 수박씨 100%”</p></details><script type="application/ld+json">{"name":"x"}</script></section>';
    const text = readableText(html);
    expect(text).toContain(
      "원재료: 수박씨 100% (출처: maker.example.com)\n무게: 300g",
    );
    expect(text).toContain("자료 원문 보기\n“원재료: 수박씨 100%”");
    expect(text).not.toContain('"name"');
  });
});
