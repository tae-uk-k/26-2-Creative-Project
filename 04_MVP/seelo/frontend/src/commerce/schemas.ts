import { z } from "zod";

export const platformSchema = z.enum(["smartstore", "cafe24"]);
export type Platform = z.infer<typeof platformSchema>;
export const platformNames: Record<Platform, string> = {
  smartstore: "스마트스토어",
  cafe24: "카페24",
};
export const factKeySchema = z.enum([
  "purpose",
  "model",
  "material",
  "size",
  "weight",
  "components",
  "power",
  "compatibility",
  "care",
  "ingredients",
  "nutrition",
  "serving",
  "allergens",
  "origin",
  "storage",
  "manufacturer",
]);
export type FactKey = z.infer<typeof factKeySchema>;
export const factNames: Record<FactKey, string> = {
  purpose: "용도",
  model: "모델",
  material: "소재",
  size: "크기",
  weight: "무게",
  components: "구성품",
  power: "전원 조건",
  compatibility: "호환 조건",
  care: "사용·관리",
  ingredients: "원재료",
  nutrition: "영양성분·함량",
  serving: "섭취 방법·1회 섭취량",
  allergens: "알레르기 유발 성분",
  origin: "원산지",
  storage: "보관 방법",
  manufacturer: "제조·판매원",
};
export const fieldSchema = z.enum([
  "description",
  "mobile_description",
  "summary_description",
  "simple_description",
  "seo.meta_title",
  "seo.meta_description",
  "seo.meta_keywords",
  "attributes",
]);
export type Field = z.infer<typeof fieldSchema>;
export const fieldNames: Record<Field, string> = {
  description: "상세설명",
  mobile_description: "모바일 설명",
  summary_description: "요약 설명",
  simple_description: "간략 설명",
  "seo.meta_title": "SEO 제목",
  "seo.meta_description": "SEO 설명",
  "seo.meta_keywords": "SEO 키워드",
  attributes: "상품 속성",
};
export const allowedFields: Record<Platform, readonly Field[]> = {
  smartstore: ["description", "attributes"],
  cafe24: [
    "description",
    "mobile_description",
    "summary_description",
    "simple_description",
    "seo.meta_title",
    "seo.meta_description",
    "seo.meta_keywords",
  ],
};
export const editingModeSchema = z.enum(["browser", "api"]);
export type EditingMode = z.infer<typeof editingModeSchema>;
// 서버가 현재 편집 모드와 실행기 설정으로 계산한 필드 범위. 화면은 이 값만 선택지로 쓴다.
export const fieldSupportSchema = z.object({
  mode: editingModeSchema,
  automatic: z.array(fieldSchema),
  manual: z.array(fieldSchema),
  unavailable: z.array(z.object({ field: fieldSchema, reason: z.string() })),
  conditions: z.record(z.string(), z.string()).default({}),
});
export type FieldSupport = z.infer<typeof fieldSupportSchema>;
export const unavailableReasons: Record<string, string> = {
  browser_field_not_configured:
    "관리자 화면 자동화에서 원본을 읽고 저장하는 입력 칸이 확인되지 않았습니다.",
  api_field_not_supported: "API 경로에서 지원하지 않습니다.",
};
export const publicUrl = z
  .url("올바른 HTTPS 주소를 입력해 주세요.")
  .refine((value) => {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      !url.username &&
      !url.password &&
      (!url.port || url.port === "443") &&
      url.hostname.includes(".") &&
      !/^[0-9.:]+$/.test(url.hostname) &&
      !/\.(local|internal|test)$/.test(url.hostname)
    );
  }, "공개 HTTPS 주소를 입력해 주세요.");
const id = z.number().int().positive();
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const date = z.iso.datetime({ offset: true });
const externalIdSchema = z
  .string()
  .trim()
  .regex(
    /^[a-z0-9][a-z0-9_-]{1,49}$/,
    "스토어 ID는 영문 소문자·숫자·밑줄·하이픈 2~50자로 입력해 주세요.",
  );
const storeBaseSchema = z.object({
  platform: platformSchema,
  externalId: externalIdSchema,
  shopNo: z.number().int().min(1).max(1000),
  name: z.string().trim().min(1).max(100),
});
// 스토어 주소만 받으면 서버가 플랫폼·스토어 ID·쇼핑몰 번호를 판별한다.
// 연결 도메인처럼 판별할 수 없는 주소일 때만 플랫폼과 스토어 ID를 직접 받는다.
export const storeInputSchema = z
  .object({
    storeUrl: z.string().trim().min(1).max(2048).optional(),
    platform: platformSchema.optional(),
    externalId: externalIdSchema.optional(),
    shopNo: z.number().int().min(1).max(1000).optional(),
    name: z.string().trim().min(1).max(100).optional(),
  })
  .refine(
    (value) =>
      Boolean(value.storeUrl) || Boolean(value.platform && value.externalId),
    "스토어 주소를 입력해 주세요.",
  );
export const productTargetSchema = z.union([
  z.object({ externalId: z.string().regex(/^[1-9][0-9]{0,18}$/) }),
  z.object({ productUrl: z.string().trim().min(1).max(2048) }),
]);
export type ProductTarget = z.infer<typeof productTargetSchema>;
export type ImportResult =
  { kind: "product"; product: Product } | { kind: "job"; job: Job };
// 브라우저 작업 상태. 서버가 worker-fix에서 실행한다. stale은 중단 의심 표시다.
export const jobSchema = z.object({
  id,
  shopId: id,
  productId: id.nullable(),
  planId: id.nullable(),
  kind: z.enum([
    "collect",
    "apply",
    "rollback",
    "verify",
    "catalog",
    "prepare",
    "forget_session",
  ]),
  status: z.enum(["queued", "running", "succeeded", "failed"]),
  errorCode: z.string().nullable(),
  result: z.record(z.string(), z.unknown()),
  stale: z.boolean(),
  createdAt: date,
  startedAt: date.nullable(),
  finishedAt: date.nullable(),
});
export type Job = z.infer<typeof jobSchema>;
export const browserSessionSchema = z
  .object({
    status: z.string(),
    jobId: id.optional(),
    checkedAt: z.string().optional(),
  })
  .nullable()
  .optional();
export const storeSchema = storeBaseSchema.extend({
  id,
  ownerId: z.number().int().nonnegative(),
  managerStatus: z.enum(["not_requested", "invited", "verified", "revoked"]),
  apiStatus: z.enum([
    "not_connected",
    "authorized",
    "read_verified",
    "write_verified",
    "revoked",
  ]),
  readVerifiedAt: date.nullable(),
  writeVerifiedAt: date.nullable(),
  automaticWritesEnabled: z.boolean(),
  editingMode: editingModeSchema,
  fieldSupport: fieldSupportSchema,
  browserRunner: z.enum(["worker", "inline"]).optional(),
  browserSession: browserSessionSchema,
  // 운영자가 위임 목록에서 확인한 스토어 고유값. 실행기가 이 값과 정확히 대조한다.
  delegatedIdentity: z
    .object({
      storeName: z.string().optional(),
      storeId: z.string().optional(),
      verifiedAt: z.string().optional(),
    })
    .nullable()
    .optional(),
});
export type DelegatedIdentity = { storeName?: string; storeId?: string };
// 위임받은 관리 화면에서 읽은 플랫폼 상품 목록. seelo에 가져온 상품 목록과 다르다.
export const catalogSchema = z.object({
  items: z.array(
    z.object({
      productNo: z.string().regex(/^[1-9][0-9]{0,18}$/),
      name: z.string(),
      importedProductId: id.nullable(),
    }),
  ),
  collectedAt: z.string().nullable(),
  truncated: z.boolean(),
  skipped: z.number().int().nonnegative().optional(),
  scope: z.literal("platform"),
});
export type Catalog = z.infer<typeof catalogSchema>;
export type StoreInput = z.infer<typeof storeInputSchema>;
export type Store = z.infer<typeof storeSchema>;
export const factSchema = z.object({
  key: factKeySchema,
  value: z.string().min(1).max(1000),
  identity: z.string().min(1).max(250),
  source_url: publicUrl.nullable(),
  quote: z.string().min(1).max(4000),
  source: z.literal("owner_answer").optional(),
  // 함량·섭취량의 숫자와 단위. 서버가 인용문과 대조해 저장한 값이다.
  quantities: z
    .array(z.object({ amount: z.string(), unit: z.string() }))
    .optional(),
});
export type Fact = z.infer<typeof factSchema>;
export const factInputSchema = z
  .object({
    key: factKeySchema,
    value: z.string().trim().min(1).max(1000),
    identity: z.string().min(1).max(250),
    sourceUrl: publicUrl,
    quote: z.string().min(1).max(4000),
  })
  .refine((fact) => fact.quote.includes(fact.value), {
    message: "인용문에 확인한 값이 포함돼야 합니다.",
    path: ["quote"],
  });
export type FactInput = z.infer<typeof factInputSchema>;
export const productNoSchema = z
  .string()
  .regex(/^[1-9][0-9]{0,18}$/, "플랫폼 상품번호를 숫자로 입력해 주세요.");
export const manualSnapshotSchema = z.object({
  externalId: productNoSchema,
  name: z.string().trim().min(1).max(250),
  identity: z.string().trim().min(1).max(250),
  fields: z
    .record(z.string(), z.string().max(200000))
    .refine(
      (value) => Object.keys(value).length > 0,
      "원본 필드가 필요합니다.",
    ),
});
export type ManualSnapshot = z.infer<typeof manualSnapshotSchema>;
export const productSchema = z.object({
  id,
  shopId: id,
  externalId: productNoSchema,
  name: z.string(),
  identity: z.string(),
  fields: z.record(z.string(), z.string()),
  snapshotHash: hash,
  snapshotSource: z.enum(["api", "browser", "seller_supplied"]),
  facts: z.array(factSchema),
  collectedAt: date,
  fieldSupport: fieldSupportSchema,
  prepareJob: z.lazy(() => jobSchema.nullable()).optional(),
  automaticWritesEnabled: z.boolean().optional(),
  // 상품 목록에서만 오는 진행 요약. 다음 할 일을 고르는 데 쓴다.
  summary: z
    .object({
      planId: id.nullable(),
      planStatus: z.string().nullable(),
      questions: z.number().int().nonnegative(),
      published: z.boolean(),
      prepare: z.object({ status: z.string(), stale: z.boolean() }).nullable(),
      measure: z.object({
        runs: z.number().int().nonnegative(),
        latestStatus: z.string().nullable(),
        baseline: z.boolean(),
        followUp: z.boolean(),
      }),
    })
    .nullable()
    .optional(),
});
export type Product = z.infer<typeof productSchema>;
export type ProductSummary = NonNullable<Product["summary"]>;
export const changeSchema = z.object({
  field: fieldSchema,
  before: z.string(),
  proposed: z.string(),
  evidence: z.array(factSchema),
  method: z.enum(["manual", "api", "browser"]),
  reason: z.string().nullable(),
});
export const planSchema = z.object({
  id,
  productId: id,
  status: z.enum([
    "draft",
    "approved",
    "no_changes",
    "applying",
    "applied",
    "pending_reflection",
    "uncertain",
    "conflict",
    "rejected",
    "manual_required",
    "manual_recorded",
    "rolled_back",
    "superseded",
  ]),
  snapshotHash: hash,
  changes: z.array(changeSchema),
  questions: z.array(z.object({ field: factKeySchema, text: z.string() })),
  deferred: z.array(z.string()),
  modelId: z.string().nullable(),
  approvedAt: date.nullable(),
  appliedAt: date.nullable(),
  approval: z
    .object({
      fields: z.array(fieldSchema).optional(),
      editorConversionConfirmed: z.boolean().optional(),
      // 승인자는 항상 스토어 소유자다. 운영자 실행 전에 이 값을 확인한다.
      approvedBy: id.optional(),
      approvedRole: z.string().optional(),
    })
    .optional(),
  job: jobSchema.nullable().optional(),
  publication: z.object({
    pc_url: publicUrl.optional(),
    mobile_url: publicUrl.optional(),
    pc_matches: z.boolean().optional(),
    mobile_matches: z.boolean().optional(),
    note: z.string().optional(),
    checked_by: id.optional(),
    checked_at: date.optional(),
    method: z.string().optional(),
  }),
});
export type Plan = z.infer<typeof planSchema>;
export const writeSchema = z.object({
  id,
  planId: id,
  action: z.enum(["apply", "rollback"]),
  status: z.string(),
  before: z.record(z.string(), z.string()),
  after: z.record(z.string(), z.string()),
  errorCode: z.string().nullable(),
  createdAt: date,
});
export type Write = z.infer<typeof writeSchema>;
export const operatorShopSchema = storeSchema.extend({
  ownerEmail: z.string(),
  work: z.object({
    products: z.number().int().nonnegative(),
    customerApproval: z.number().int().nonnegative(),
    operatorExecute: z.number().int().nonnegative(),
    manualEdit: z.number().int().nonnegative(),
    checkResult: z.number().int().nonnegative(),
  }),
});
export type OperatorShop = z.infer<typeof operatorShopSchema>;
export const operatorShopPageSchema = z.object({
  shops: z.array(operatorShopSchema),
  page: z.number().int().positive(),
  pageSize: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  invited: z.number().int().nonnegative(),
});
export type OperatorShopPage = z.infer<typeof operatorShopPageSchema>;
export const operatorTaskSchema = z.object({
  planId: id,
  status: z.string(),
  next: z.enum(["execute", "manual_edit", "check_result", "customer_approval"]),
  customerApproved: z.boolean(),
  approvedFields: z.array(fieldSchema),
  productId: id,
  productName: z.string(),
  productNo: z.string(),
  shopId: id,
  shopName: z.string(),
  platform: platformSchema,
  managerStatus: z.string(),
  ownerEmail: z.string(),
  approvedAt: date.nullable(),
});
export type OperatorTask = z.infer<typeof operatorTaskSchema>;
export type OperatorShopSearch = {
  page: number;
  query: string;
  managerStatus?: Store["managerStatus"];
};
// 쇼핑몰 AI 노출 진단. 호출 실패는 무효(missing)로 남기고 노출 0으로 세지 않는다.
export const measureQuerySchema = z.object({
  id: z.string().regex(/^[A-Za-z0-9_-]{1,20}$/),
  family: z.string().default("general"),
  question: z.string().min(5).max(500),
});
export const measureSetSchema = z.object({
  id,
  productId: id,
  name: z.string(),
  commonSuffix: z.string(),
  queries: z.array(measureQuerySchema),
  targets: z.object({ names: z.array(z.string()), urls: z.array(z.string()) }),
  createdAt: date,
});
export type MeasureSet = z.infer<typeof measureSetSchema>;
const measureRowSchema = z.object({
  queryId: z.string(),
  family: z.string(),
  planned: z.number().int(),
  valid: z.number().int(),
  missing: z.number().int(),
  failedAttempts: z.number().int(),
  identified: z.number().int(),
  recommended: z.number().int(),
  cited: z.number().int(),
});
const measureTotalsSchema = z.object({
  planned: z.number().int(),
  valid: z.number().int(),
  missing: z.number().int(),
  identified: z.number().int(),
  recommended: z.number().int(),
  cited: z.number().int(),
  rates: z.object({
    identified: z.number().nullable(),
    recommended: z.number().nullable(),
    cited: z.number().nullable(),
  }),
});
export const measureRunSchema = z.object({
  id,
  setId: id,
  productId: id,
  label: z.string(),
  status: z.enum(["queued", "running", "completed", "partial", "failed"]),
  condition: z.object({
    provider: z.enum(["openai", "gemini"]),
    model: z.string(),
    toolOptions: z.string(),
    repeats: z.number().int(),
  }),
  snapshotHash: hash,
  planId: id.nullable(),
  createdAt: date,
  finishedAt: date.nullable(),
  job: jobSchema.nullable(),
  summary: z.object({
    queries: z.array(measureRowSchema),
    totals: measureTotalsSchema,
  }),
});
export type MeasureRun = z.infer<typeof measureRunSchema>;
const runRefSchema = z.object({
  id,
  label: z.string(),
  snapshotHash: hash,
  planId: id.nullable(),
  condition: z
    .object({
      provider: z.enum(["openai", "gemini"]),
      model: z.string(),
      toolOptions: z.string(),
      repeats: z.number().int(),
    })
    .optional(),
  finishedAt: date.nullable().optional(),
});
export const measureCompareSchema = z.object({
  before: runRefSchema,
  after: runRefSchema,
  sameSnapshot: z.boolean(),
  queries: z.array(
    z.object({
      queryId: z.string(),
      family: z.string(),
      before: measureRowSchema,
      after: measureRowSchema,
      comparable: z.boolean(),
    }),
  ),
  totals: z.object({ before: measureTotalsSchema, after: measureTotalsSchema }),
});
export type MeasureCompare = z.infer<typeof measureCompareSchema>;
export type MeasureSetInput = {
  name: string;
  queries: { id: string; family?: string; question: string }[];
  targetNames?: string[];
  targetUrls?: string[];
};
export type MeasureRunInput = {
  label: string;
  provider: "openai" | "gemini";
  repeats: number;
};
export type Workspace = {
  store: Store;
  product: Product;
  plans: Plan[];
  // 최신 정비안의 쓰기 이력. 다른 정비안의 이력은 writes(planId)로 따로 조회한다.
  writes: Write[];
};
export type ProductSearch = { page: number; query: string };
// seelo에 가져온 상품의 서버 검색 결과. 플랫폼의 전체 상품 목록과 다르다.
export type ProductPage = {
  items: Product[];
  page: number;
  pageSize: number;
  total: number;
};
export const generateSchema = z.object({
  fields: z.array(fieldSchema).min(1).max(8),
  requiredFacts: z.array(factKeySchema).max(16),
  useAi: z.boolean(),
  allowEditorConversion: z.boolean(),
});
export type GenerateInput = z.infer<typeof generateSchema>;
export type Command =
  | { action: "research"; sourceUrls: string[] }
  // 기본 흐름: AI가 자료 조사 → 필요한 정보 판단 → 정비안 생성. 승인은 고객이 따로 한다.
  | { action: "prepare"; sourceUrls: string[] }
  | { action: "facts"; facts: FactInput[] }
  | { action: "answers"; answers: Partial<Record<FactKey, string>> }
  | ({ action: "generate" } & GenerateInput)
  | {
      action: "approve";
      planId: number;
      snapshotHash: string;
      fields?: Field[];
      editorConversionConfirmed?: boolean;
    }
  | { action: "apply" | "verify"; planId: number }
  | { action: "rollback"; planId: number; confirmed: true }
  | {
      action: "publication";
      planId: number;
      pcUrl: string;
      mobileUrl: string;
      pcMatches: boolean;
      mobileMatches: boolean;
      note: string;
    }
  | {
      action: "manual-result";
      planId: number;
      values: Record<string, string>;
      note: string;
    };
export interface CommerceGateway {
  stores(signal?: AbortSignal): Promise<Store[]>;
  store(id: number, signal?: AbortSignal): Promise<Store>;
  addStore(input: StoreInput): Promise<Store>;
  manager(
    id: number,
    status: "invited" | "verified" | "revoked",
    identity?: DelegatedIdentity,
  ): Promise<Store>;
  requestCatalog(
    storeId: number,
  ): Promise<{ kind: "job"; job: Job } | { kind: "catalog"; catalog: Catalog }>;
  catalog(storeId: number, signal?: AbortSignal): Promise<Catalog>;
  authorize(id: number): Promise<{ authorizationUrl: string }>;
  // seelo의 접근 기록·API 토큰을 폐기한다. 플랫폼 쪽 매니저·앱 삭제는 판매자가 따로 한다.
  disconnect(id: number): Promise<Store>;
  writes(planId: number, signal?: AbortSignal): Promise<Write[]>;
  // 운영자(관리자) 전용 조회. 서버가 관리자 역할을 다시 확인한다.
  operatorShops(
    search: OperatorShopSearch,
    signal?: AbortSignal,
  ): Promise<OperatorShopPage>;
  operatorTasks(signal?: AbortSignal): Promise<OperatorTask[]>;
  measureSets(productId: number, signal?: AbortSignal): Promise<MeasureSet[]>;
  createMeasureSet(
    productId: number,
    input: MeasureSetInput,
  ): Promise<MeasureSet>;
  measureRuns(productId: number, signal?: AbortSignal): Promise<MeasureRun[]>;
  runMeasure(setId: number, input: MeasureRunInput): Promise<MeasureRun>;
  compareRuns(
    before: number,
    after: number,
    signal?: AbortSignal,
  ): Promise<MeasureCompare>;
  products(
    storeId: number,
    search: ProductSearch,
    signal?: AbortSignal,
  ): Promise<ProductPage>;
  // 브라우저 수집은 서버가 작업으로 받는다(202). API 경로·로컬 실행은 바로 상품을 돌려준다.
  importProduct(storeId: number, target: ProductTarget): Promise<ImportResult>;
  job(jobId: number, signal?: AbortSignal): Promise<Job>;
  manualSnapshot(storeId: number, input: ManualSnapshot): Promise<Product>;
  workspace(
    storeId: number,
    productId: number,
    signal?: AbortSignal,
  ): Promise<Workspace>;
  command(
    storeId: number,
    productId: number,
    command: Command,
  ): Promise<Workspace>;
}
