import { ApiError } from "../api/client";
import { conditionKey } from "./report";
import { approvedChanges, latestPlan, validateCommand } from "./rules";
import {
  allowedFields,
  factNames,
  manualSnapshotSchema,
  storeInputSchema,
  type CommerceGateway,
  type Fact,
  type FieldSupport,
  type FactKey,
  type ManualSnapshot,
  type Plan,
  type Product,
  type Store,
  type Workspace,
  type MeasureRun,
  type MeasureSet,
  type Platform,
  type ProductTarget,
} from "./schemas";
// 시연 모드는 API 경로를 흉내 낸다. 실제 서버의 필드 범위 계산과 같은 형식을 쓴다.
const demoSupport = (
  platform: Platform,
  mode: "api" | "browser" = "api",
): FieldSupport => ({
  mode,
  automatic: allowedFields[platform].filter((field) => field !== "attributes"),
  manual: platform === "smartstore" ? ["attributes"] : [],
  unavailable: [],
  conditions:
    platform === "smartstore"
      ? { description: "editor_conversion_approval" }
      : {},
});
const copy = <T>(value: T): T => structuredClone(value);
const date = () => new Date().toISOString();
const fingerprint = (value: string) => {
  let result = 0;
  for (const char of value) result = (result * 31 + char.charCodeAt(0)) >>> 0;
  return result.toString(16).padStart(64, "0");
};
// 명시적 시연 모드에서만 생성한다. 외부 요청·상품 수정·AI 호출은 없다.
export function createDemoGateway(): CommerceGateway {
  let sequence = 10;
  const shops: Store[] = [
    {
      id: 1,
      ownerId: 0,
      platform: "cafe24",
      externalId: "seelo-demo",
      shopNo: 1,
      name: "카페24 시연 스토어",
      managerStatus: "verified",
      apiStatus: "read_verified",
      readVerifiedAt: date(),
      writeVerifiedAt: null,
      automaticWritesEnabled: true,
      editingMode: "api",
      fieldSupport: demoSupport("cafe24"),
    },
    {
      id: 2,
      ownerId: 0,
      platform: "smartstore",
      externalId: "seelo-demo",
      shopNo: 1,
      name: "스마트스토어 시연 스토어",
      managerStatus: "verified",
      apiStatus: "not_connected",
      readVerifiedAt: null,
      writeVerifiedAt: null,
      automaticWritesEnabled: true,
      editingMode: "api",
      fieldSupport: demoSupport("smartstore"),
    },
    // 연결 단계를 보여 주는 시연 스토어. 관리자 화면 자동화 방식이다.
    {
      id: 3,
      ownerId: 0,
      platform: "smartstore",
      externalId: "seelo-guide",
      shopNo: 1,
      name: "권한 위임 전 시연 스토어",
      managerStatus: "not_requested",
      apiStatus: "not_connected",
      readVerifiedAt: null,
      writeVerifiedAt: null,
      automaticWritesEnabled: true,
      editingMode: "browser",
      fieldSupport: demoSupport("smartstore", "browser"),
    },
    {
      id: 4,
      ownerId: 0,
      platform: "cafe24",
      externalId: "seelo-wait",
      shopNo: 1,
      name: "권한 확인 중 시연 스토어",
      managerStatus: "invited",
      apiStatus: "not_connected",
      readVerifiedAt: null,
      writeVerifiedAt: null,
      automaticWritesEnabled: true,
      editingMode: "browser",
      fieldSupport: demoSupport("cafe24", "browser"),
    },
  ];
  const data = new Map<number, Workspace>();
  const measureSets: MeasureSet[] = [];
  const measureRuns: MeasureRun[] = [];
  const asked = new Map<number, FactKey[]>();
  const shop = (id: number) =>
    shops.find((shop) => shop.id === id) ?? missing();
  function missing(): never {
    throw new ApiError(404, "NOT_FOUND", "대상을 찾을 수 없습니다.");
  }
  function seed(
    store: Store,
    input: ManualSnapshot = {
      externalId: "1001",
      name: "시연용 텀블러 500mL",
      identity: "DEMO-T500::500mL-silver",
      fields: { description: "<p>기존 상품 소개</p>" },
    },
    source: Product["snapshotSource"] = "api",
  ) {
    const product: Product = {
      id: ++sequence,
      shopId: store.id,
      ...input,
      snapshotHash: fingerprint(JSON.stringify(input)),
      snapshotSource: source,
      facts: [],
      collectedAt: date(),
      fieldSupport: demoSupport(store.platform),
    };
    data.set(product.id, { store, product, plans: [], writes: [] });
    return product;
  }
  const daysAgo = (days: number) =>
    new Date(Date.now() - days * 86_400_000).toISOString();
  // 정비를 마친 시연 상품: 반영·공개 확인·정비 전후 측정까지 끝난 상태다. 보고서 화면을 보여 준다.
  function seedFinished(store: Store) {
    const product = seed(store, {
      externalId: "1003",
      name: "시연용 보온병 750mL",
      identity: "DEMO-B750::750mL-navy",
      fields: {
        description: "<p>매일 들고 다니기 좋은 보온병입니다.</p>",
        summary_description: "",
      },
    });
    const source = "https://example.com/demo-bottle";
    const fact = (key: FactKey, value: string): Fact => ({
      key,
      value,
      identity: product.identity,
      source_url: source,
      quote: `시연 고정 자료: ${value}`,
    });
    product.facts = [
      fact("material", "스테인리스 304 이중 진공"),
      fact("size", "750mL"),
      fact("care", "식기세척기 사용 불가, 손세척 권장"),
      {
        key: "origin",
        value: "대한민국",
        identity: product.identity,
        source_url: null,
        quote: "대한민국",
        source: "owner_answer",
      },
    ];
    const lines = product.facts
      .map((item) => `<li>${factNames[item.key]}: ${item.value}</li>`)
      .join("");
    const plan: Plan = {
      id: ++sequence,
      productId: product.id,
      status: "applied",
      snapshotHash: product.snapshotHash,
      changes: [
        {
          field: "description",
          before: product.fields.description,
          proposed: `${product.fields.description}\n<section data-seelo="product-facts"><h2>상품 정보</h2><ul>${lines}</ul></section>`,
          evidence: copy(product.facts),
          method: "api",
          reason: null,
        },
        {
          field: "summary_description",
          before: "",
          proposed: "스테인리스 304 이중 진공 · 750mL",
          evidence: copy(product.facts.slice(0, 2)),
          method: "api",
          reason: null,
        },
      ],
      questions: [],
      deferred: [],
      modelId: "demo-fixed-order",
      approvedAt: daysAgo(7),
      appliedAt: daysAgo(6),
      approval: {
        fields: ["description", "summary_description"],
        editorConversionConfirmed: false,
        approvedBy: store.ownerId,
        approvedRole: "owner",
      },
      publication: {
        pc_url:
          "https://seelo-demo.cafe24.com/product/detail.html?product_no=1003",
        mobile_url:
          "https://seelo-demo.cafe24.com/product/detail.html?product_no=1003",
        pc_matches: true,
        mobile_matches: true,
        note: "시연 기록",
        checked_by: 1,
        checked_at: daysAgo(6),
        method: "demo_observation",
      },
    };
    const value = data.get(product.id)!;
    value.plans.push(plan);
    value.writes.push({
      id: ++sequence,
      planId: plan.id,
      action: "apply",
      status: "applied",
      before: { description: plan.changes[0].before, summary_description: "" },
      after: {
        description: plan.changes[0].proposed,
        summary_description: plan.changes[1].proposed,
      },
      errorCode: null,
      createdAt: daysAgo(6),
    });
    const set: MeasureSet = {
      id: ++sequence,
      productId: product.id,
      name: "기본 질문",
      commonSuffix: "웹에서 제품을 찾아 3개까지 소개해줘.",
      queries: [
        {
          id: "G01",
          family: "general",
          question: "750mL 스테인리스 보온병 추천해줘",
        },
        {
          id: "G02",
          family: "general",
          question: "손세척하기 쉬운 이중 진공 텀블러 찾아줘",
        },
        {
          id: "G03",
          family: "general",
          question: "국산 보온병 중 출퇴근용으로 좋은 제품 알려줘",
        },
      ],
      targets: { names: [product.name], urls: [] },
      createdAt: daysAgo(11),
    };
    measureSets.push(set);
    // 질문마다 3번 묻는다. [발견, 추천, 링크 인용] 횟수.
    const demoRun = (
      provider: "openai" | "gemini",
      label: string,
      planId: number | null,
      days: number,
      counts: [number, number, number][],
    ): MeasureRun => {
      const rows = set.queries.map((query, index) => ({
        queryId: query.id,
        family: query.family,
        planned: 3,
        valid: 3,
        missing: 0,
        failedAttempts: 0,
        identified: counts[index][0],
        recommended: counts[index][1],
        cited: counts[index][2],
      }));
      const sum = (key: "identified" | "recommended" | "cited") =>
        rows.reduce((total, row) => total + row[key], 0);
      const valid = rows.length * 3;
      return {
        id: ++sequence,
        setId: set.id,
        productId: product.id,
        label,
        status: "completed",
        condition: {
          provider,
          model: provider === "openai" ? "demo-chatgpt" : "demo-gemini",
          toolOptions: "web_search",
          repeats: 3,
        },
        snapshotHash: product.snapshotHash,
        planId,
        createdAt: daysAgo(days),
        finishedAt: daysAgo(days),
        job: null,
        summary: {
          queries: rows,
          totals: {
            planned: valid,
            valid,
            missing: 0,
            identified: sum("identified"),
            recommended: sum("recommended"),
            cited: sum("cited"),
            rates: {
              identified: sum("identified") / valid,
              recommended: sum("recommended") / valid,
              cited: sum("cited") / valid,
            },
          },
        },
      };
    };
    measureRuns.push(
      demoRun("openai", "P1", plan.id, 2, [
        [2, 1, 1],
        [2, 1, 1],
        [1, 0, 0],
      ]),
      demoRun("gemini", "P1", plan.id, 2, [
        [1, 1, 0],
        [1, 0, 1],
        [0, 0, 0],
      ]),
      demoRun("openai", "B0", null, 10, [
        [0, 0, 0],
        [1, 0, 0],
        [0, 0, 0],
      ]),
      demoRun("gemini", "B0", null, 10, [
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
      ]),
    );
  }
  // 실제 서버의 상품 목록 요약(commerce_summary)과 같은 형식으로 만든다.
  function summarize(value: Workspace) {
    const plan = latestPlan(value);
    const runs = measureRuns.filter(
      (run) => run.productId === value.product.id,
    );
    const finished = runs.filter((run) =>
      ["completed", "partial"].includes(run.status),
    );
    const baselines = new Set(
      finished.filter((run) => run.planId === null).map(conditionKey),
    );
    return {
      planId: plan?.id ?? null,
      planStatus: plan?.status ?? null,
      questions: plan?.questions.length ?? 0,
      published: Boolean(
        plan?.publication.pc_matches &&
        plan.publication.mobile_matches &&
        plan.publication.checked_at,
      ),
      prepare: null,
      measure: {
        runs: runs.length,
        latestStatus: runs[0]?.status ?? null,
        baseline: baselines.size > 0,
        followUp: finished.some(
          (run) => run.planId !== null && baselines.has(conditionKey(run)),
        ),
      },
    };
  }
  shops
    .filter((store) => store.editingMode === "api")
    .forEach((store) =>
      seed(store, undefined, store.id === 1 ? "api" : "seller_supplied"),
    );
  seedFinished(shops[0]);
  // 실제 서버처럼 작업 화면에는 최신 정비안의 쓰기 이력만 담는다.
  const view = (value: Workspace): Workspace => {
    const latest = latestPlan(value);
    return copy({
      ...value,
      writes: value.writes.filter((write) => write.planId === latest?.id),
    });
  };
  const get = (storeId: number, productId: number) => {
    const value = data.get(productId) ?? missing();
    if (value.store.id !== storeId) missing();
    return value;
  };
  // 시연용 고정 목록. 실제 관리 화면을 읽지 않는다.
  function demoCatalog(id: number) {
    shop(id);
    const items = [
      { productNo: "1001", name: "시연용 텀블러 500mL" },
      { productNo: "1002", name: "시연용 머그 350mL" },
    ].map((item) => ({
      ...item,
      importedProductId:
        [...data.values()].find(
          (value) =>
            value.store.id === id &&
            value.product.externalId === item.productNo,
        )?.product.id ?? null,
    }));
    return {
      items,
      collectedAt: date(),
      truncated: false,
      scope: "platform" as const,
    };
  }
  async function importOne(id: number, target: ProductTarget) {
    const externalId =
      "externalId" in target
        ? target.externalId
        : (new URL(target.productUrl).searchParams.get("product_no") ??
          missing());
    const store = shop(id);
    if (store.editingMode === "browser" && store.managerStatus !== "verified")
      throw new ApiError(
        409,
        "COMMERCE_NOT_CONNECTED",
        "관리자 권한 확인이 필요합니다.",
      );
    if (
      store.editingMode === "api" &&
      (store.apiStatus === "not_connected" || store.apiStatus === "revoked")
    )
      throw new ApiError(
        409,
        "COMMERCE_NOT_CONNECTED",
        "API 인증이 필요합니다.",
      );
    const existing = [...data.values()].find(
      (value) =>
        value.store.id === id && value.product.externalId === externalId,
    );
    if (store.editingMode === "api") {
      store.apiStatus = "read_verified";
      store.readVerifiedAt = date();
    }
    return copy(
      existing?.product ??
        seed(store, {
          externalId,
          name: `시연 상품 ${externalId}`,
          identity: `DEMO-${externalId}`,
          fields: { description: "시연 상품 원본" },
        }),
    );
  }
  const gateway: CommerceGateway = {
    stores: async () => copy(shops),
    store: async (id) => copy(shop(id)),
    addStore: async (input) => {
      const parsed = storeInputSchema.parse(input);
      // 시연 모드는 기본 도메인만 판별한다. 실제 판별 규칙은 서버가 적용한다.
      const host = parsed.storeUrl
        ? new URL(
            parsed.storeUrl.includes("://")
              ? parsed.storeUrl
              : `https://${parsed.storeUrl}`,
          )
        : undefined;
      const value = {
        platform:
          parsed.platform ??
          (host?.hostname.endsWith("smartstore.naver.com")
            ? ("smartstore" as const)
            : host?.hostname.endsWith(".cafe24.com")
              ? ("cafe24" as const)
              : undefined),
        externalId:
          parsed.externalId ??
          (host?.hostname.endsWith("smartstore.naver.com")
            ? host.pathname.split("/").filter(Boolean)[0]?.toLowerCase()
            : host?.hostname.split(".").at(-3)),
        shopNo: parsed.shopNo ?? 1,
        name: parsed.name,
      };
      if (!value.platform || !value.externalId)
        throw new ApiError(
          422,
          "COMMERCE_INVALID",
          "주소로 스토어를 판별하지 못했습니다. 플랫폼과 스토어 ID를 입력해 주세요.",
        );
      if (
        shops.some(
          (shop) =>
            shop.platform === value.platform &&
            shop.externalId === value.externalId &&
            shop.shopNo === value.shopNo,
        )
      )
        throw new ApiError(
          409,
          "COMMERCE_DUPLICATE",
          "이미 등록한 스토어입니다.",
        );
      const store: Store = {
        platform: value.platform,
        externalId: value.externalId,
        shopNo: value.shopNo,
        name: value.name ?? value.externalId,
        id: ++sequence,
        ownerId: 0,
        managerStatus: "not_requested",
        apiStatus: "not_connected",
        readVerifiedAt: null,
        writeVerifiedAt: null,
        automaticWritesEnabled: true,
        editingMode: "api",
        fieldSupport: demoSupport(value.platform),
      };
      shops.push(store);
      return copy(store);
    },
    manager: async (id, status, identity) => {
      shop(id).managerStatus = status;
      shop(id).delegatedIdentity =
        status === "revoked"
          ? null
          : identity?.storeName
            ? { storeName: identity.storeName, storeId: identity.storeId }
            : shop(id).delegatedIdentity;
      return copy(shop(id));
    },
    requestCatalog: async (id) => ({
      kind: "catalog" as const,
      catalog: demoCatalog(id),
    }),
    catalog: async (id) => demoCatalog(id),
    disconnect: async (id) => {
      Object.assign(shop(id), {
        managerStatus: "revoked",
        apiStatus: "revoked",
      });
      return copy(shop(id));
    },
    writes: async (planId) =>
      copy(
        [...data.values()].flatMap((value) =>
          value.writes.filter((write) => write.planId === planId),
        ),
      ),
    operatorShops: async ({ page, query, managerStatus }) => {
      const items = shops
        .filter(
          (value) =>
            (!managerStatus || value.managerStatus === managerStatus) &&
            value.name.includes(query),
        )
        .map((value) => {
          const plans = [...data.values()]
            .filter((item) => item.store.id === value.id)
            .flatMap((item) => item.plans);
          const count = (...statuses: Plan["status"][]) =>
            plans.filter((plan) => statuses.includes(plan.status)).length;
          return {
            ...value,
            ownerEmail: "demo@example.com",
            work: {
              products: [...data.values()].filter(
                (item) => item.store.id === value.id,
              ).length,
              customerApproval: count("draft"),
              operatorExecute: count("approved"),
              manualEdit: count("manual_required"),
              checkResult: count("applying", "uncertain", "pending_reflection"),
            },
          };
        });
      return copy({
        shops: items.slice((page - 1) * 20, page * 20),
        page,
        pageSize: 20,
        total: items.length,
        invited: shops.filter((value) => value.managerStatus === "invited")
          .length,
      });
    },
    operatorTasks: async () =>
      copy(
        [...data.values()].flatMap((item) =>
          item.plans
            .filter((plan) =>
              [
                "draft",
                "approved",
                "manual_required",
                "applying",
                "uncertain",
                "pending_reflection",
              ].includes(plan.status),
            )
            .map((plan) => ({
              planId: plan.id,
              status: plan.status,
              next:
                plan.status === "draft"
                  ? ("customer_approval" as const)
                  : plan.status === "approved"
                    ? ("execute" as const)
                    : plan.status === "manual_required"
                      ? ("manual_edit" as const)
                      : ("check_result" as const),
              customerApproved:
                plan.approval?.approvedBy === item.store.ownerId,
              approvedFields: plan.approval?.fields ?? [],
              productId: item.product.id,
              productName: item.product.name,
              productNo: item.product.externalId,
              shopId: item.store.id,
              shopName: item.store.name,
              platform: item.store.platform,
              managerStatus: item.store.managerStatus,
              ownerEmail: "demo@example.com",
              approvedAt: plan.approvedAt,
            })),
        ),
      ),
    // 시연 모드는 AI를 호출하지 않는다. 측정은 모두 무효(호출 없음)로 남겨 노출 0과 구분한다.
    measureSets: async (productId) =>
      copy(measureSets.filter((value) => value.productId === productId)),
    createMeasureSet: async (productId, input) => {
      const product = [...data.values()].find(
        (value) => value.product.id === productId,
      )?.product;
      if (!product) missing();
      const value: MeasureSet = {
        id: ++sequence,
        productId,
        name: input.name,
        commonSuffix: "웹에서 제품을 찾아 3개까지 소개해줘.",
        queries: input.queries.map((query) => ({
          family: "general",
          ...query,
        })),
        targets: {
          names: input.targetNames?.length
            ? input.targetNames
            : [product!.name],
          urls: input.targetUrls ?? [],
        },
        createdAt: date(),
      };
      measureSets.unshift(value);
      return copy(value);
    },
    measureRuns: async (productId) =>
      copy(measureRuns.filter((value) => value.productId === productId)),
    runMeasure: async (setId, input) => {
      const set = measureSets.find((value) => value.id === setId) ?? missing();
      const product = [...data.values()].find(
        (value) => value.product.id === set.productId,
      )!.product;
      const rows = set.queries.map((query) => ({
        queryId: query.id,
        family: query.family,
        planned: input.repeats,
        valid: 0,
        missing: input.repeats,
        failedAttempts: input.repeats * 2,
        identified: 0,
        recommended: 0,
        cited: 0,
      }));
      const run: MeasureRun = {
        id: ++sequence,
        setId,
        productId: set.productId,
        label: input.label,
        status: "failed",
        condition: {
          provider: input.provider,
          model: "demo-no-ai",
          toolOptions: "demo",
          repeats: input.repeats,
        },
        snapshotHash: product.snapshotHash,
        planId: null,
        createdAt: date(),
        finishedAt: date(),
        job: null,
        summary: {
          queries: rows,
          totals: {
            planned: rows.length * input.repeats,
            valid: 0,
            missing: rows.length * input.repeats,
            identified: 0,
            recommended: 0,
            cited: 0,
            rates: { identified: null, recommended: null, cited: null },
          },
        },
      };
      measureRuns.unshift(run);
      return copy(run);
    },
    compareRuns: async (before, after) => {
      const left =
        measureRuns.find((value) => value.id === before) ?? missing();
      const right =
        measureRuns.find((value) => value.id === after) ?? missing();
      if (
        left.setId !== right.setId ||
        left.condition.provider !== right.condition.provider ||
        left.condition.repeats !== right.condition.repeats
      )
        throw new ApiError(
          422,
          "COMMERCE_INVALID",
          "같은 질문 세트·측정 조건끼리만 비교합니다.",
        );
      return copy({
        before: left,
        after: right,
        sameSnapshot: left.snapshotHash === right.snapshotHash,
        queries: left.summary.queries.map((row, index) => ({
          queryId: row.queryId,
          family: row.family,
          before: row,
          after: right.summary.queries[index],
          comparable: row.valid > 0 && right.summary.queries[index].valid > 0,
        })),
        totals: { before: left.summary.totals, after: right.summary.totals },
      });
    },
    authorize: async (id) => {
      shop(id).apiStatus = "authorized";
      return { authorizationUrl: "/stores" };
    },
    products: async (storeId, { page, query }) => {
      shop(storeId);
      const items = [...data.values()]
        .filter(
          (value) =>
            value.store.id === storeId &&
            value.product.name.toLowerCase().includes(query.toLowerCase()),
        )
        .map((value) => ({ ...value.product, summary: summarize(value) }));
      return copy({
        items: items.slice((page - 1) * 20, page * 20),
        page,
        pageSize: 20,
        total: items.length,
      });
    },
    importProduct: async (id, target) => ({
      kind: "product" as const,
      product: await importOne(id, target),
    }),
    job: async () => missing(),
    manualSnapshot: async (id, input) => {
      const value = manualSnapshotSchema.parse(input);
      if (
        Object.keys(value.fields).some(
          (field) => !allowedFields[shop(id).platform].includes(field as never),
        )
      )
        throw new ApiError(
          422,
          "COMMERCE_INVALID",
          "지원하는 필드만 입력해 주세요.",
        );
      return copy(seed(shop(id), value, "seller_supplied"));
    },
    workspace: async (storeId, productId) => view(get(storeId, productId)),
    command: async (storeId, productId, command) => {
      const workspace = get(storeId, productId);
      validateCommand(workspace, command, true);
      if (command.action === "prepare") {
        // 시연: 고정 자료 조사 → 크기 정보를 필요한 정보로 판단 → 권장 범위로 정비안 생성.
        await gateway.command(storeId, productId, {
          action: "research",
          sourceUrls: command.sourceUrls,
        });
        return gateway.command(storeId, productId, {
          action: "generate",
          fields: ["description"],
          requiredFacts: ["size"],
          useAi: true,
          allowEditorConversion: false,
        });
      }
      const plan =
        "planId" in command
          ? workspace.plans.find((value) => value.id === command.planId)
          : latestPlan(workspace);
      if (command.action === "research") {
        // 실제 서버처럼 조사 결과를 기존 근거·답변에 합친다.
        workspace.product.facts = [
          ...workspace.product.facts.filter((fact) => fact.key !== "model"),
          {
            key: "model",
            value: "DEMO-T500",
            identity: workspace.product.identity,
            source_url: "https://example.com/demo-product",
            quote: "시연 고정 자료: DEMO-T500 모델",
          },
        ];
      } else if (command.action === "facts") {
        const incoming = command.facts.map((fact) => ({
          key: fact.key,
          value: fact.value,
          identity: fact.identity,
          source_url: fact.sourceUrl,
          quote: fact.quote,
        }));
        workspace.product.facts = [
          ...workspace.product.facts.filter(
            (fact) => !incoming.some((value) => value.key === fact.key),
          ),
          ...incoming,
        ];
      } else if (command.action === "answers") {
        for (const [key, value] of Object.entries(command.answers)) {
          const fact: Fact = {
            key: key as Fact["key"],
            value: value!,
            identity: workspace.product.identity,
            quote: value!,
            source_url: null,
            source: "owner_answer",
          };
          workspace.product.facts = [
            ...workspace.product.facts.filter(
              (previous) => previous.key !== key,
            ),
            fact,
          ];
        }
      } else if (command.action === "generate") {
        const facts = workspace.product.facts;
        const previous = asked.get(productId) ?? [];
        const missing = command.requiredFacts.filter(
          (key) => !facts.some((fact) => fact.key === key),
        );
        const questions = [
          ...previous,
          ...missing
            .filter((key) => !previous.includes(key))
            .slice(0, Math.max(0, 3 - previous.length)),
        ];
        asked.set(productId, questions);
        const text = facts
          .map((fact) => `${factNames[fact.key]}: ${fact.value}`)
          .join(" · ");
        const next: Plan = {
          id: ++sequence,
          productId,
          status: text ? "draft" : "no_changes",
          snapshotHash: workspace.product.snapshotHash,
          changes: text
            ? command.fields.map((field) => ({
                field,
                before: workspace.product.fields[field] ?? "",
                proposed: (workspace.product.fields[field] ?? "") + "\n" + text,
                evidence: copy(facts),
                method:
                  field === "attributes" ||
                  (workspace.store.platform === "smartstore" &&
                    !command.allowEditorConversion)
                    ? "manual"
                    : "api",
                reason:
                  workspace.store.platform === "smartstore" &&
                  !command.allowEditorConversion
                    ? "editor_conversion_requires_approval"
                    : null,
              }))
            : [],
          questions: questions
            .filter((key) => missing.includes(key))
            .map((field) => ({
              field,
              text: `이 상품의 ${factNames[field]} 정보를 알려 주세요.`,
            })),
          deferred: command.requiredFacts
            .filter((key) => !facts.some((fact) => fact.key === key))
            .map((key) => `fact:${key}`),
          modelId: command.useAi ? "demo-fixed-order" : null,
          approvedAt: null,
          appliedAt: null,
          publication: {},
        };
        workspace.plans.unshift(next);
      } else if (command.action === "approve") {
        plan!.status = "approved";
        plan!.approvedAt = date();
        plan!.approval = {
          fields: command.fields ?? plan!.changes.map((change) => change.field),
          editorConversionConfirmed: command.editorConversionConfirmed ?? false,
          approvedBy: workspace.store.ownerId,
          approvedRole: "owner",
        };
      } else if (command.action === "apply" || command.action === "rollback") {
        const changes = approvedChanges(plan!);
        if (
          command.action === "apply" &&
          changes.some((change) => change.method === "manual")
        )
          plan!.status = "manual_required";
        else {
          plan!.status = command.action === "apply" ? "applied" : "rolled_back";
          plan!.appliedAt = date();
          plan!.publication = {};
          workspace.writes.push({
            id: ++sequence,
            planId: plan!.id,
            action: command.action === "apply" ? "apply" : "rollback",
            status: plan!.status,
            before: Object.fromEntries(
              changes.map((change) => [
                change.field,
                command.action === "apply" ? change.before : change.proposed,
              ]),
            ),
            after: Object.fromEntries(
              changes.map((change) => [
                change.field,
                command.action === "apply" ? change.proposed : change.before,
              ]),
            ),
            errorCode: null,
            createdAt: date(),
          });
          workspace.store.apiStatus = "write_verified";
          workspace.store.writeVerifiedAt = date();
        }
      } else if (command.action === "publication") {
        plan!.publication = {
          pc_url: command.pcUrl,
          mobile_url: command.mobileUrl,
          pc_matches: command.pcMatches,
          mobile_matches: command.mobileMatches,
          note: command.note,
          checked_by: 1,
          checked_at: date(),
          method: "demo_observation",
        };
      } else if (command.action === "manual-result") {
        plan!.status = "manual_recorded";
        plan!.appliedAt = date();
      }
      return view(workspace);
    },
  };
  return gateway;
}
