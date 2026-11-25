import { useEffect, useState, type FormEvent } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  useAddStore,
  useCommand,
  activeJob,
  useCatalog,
  useImportProduct,
  useJob,
  useProducts,
  useShopAction,
  useStore,
  useStores,
  useWorkspace,
  useWrites,
} from "../app/commerce";
import { useRuntime, useSession } from "../app/runtime";
import {
  factInputSchema,
  factNames,
  fieldNames,
  generateSchema,
  manualSnapshotSchema,
  platformNames,
  productNoSchema,
  storeInputSchema,
  unavailableReasons,
  type Command,
  type FactKey,
  type Field,
  type ProductTarget,
  type Store,
  type Workspace,
} from "../commerce/schemas";
import {
  approvedChanges,
  customerApproved,
  jobMessage,
  editingLabel,
  isRunning,
  latestPlan,
  planById,
  publicationComplete,
  stageOf,
  validChanges,
  verifiableStatuses,
} from "../commerce/rules";
import { ErrorMessage, QueryState, formValues } from "./common";
import { MeasureSection } from "./measure";

export function StoresPage() {
  const stores = useStores();
  const add = useAddStore();
  const [error, setError] = useState<unknown>(null);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (add.isPending) return;
    try {
      const raw = formValues(event.currentTarget);
      const text = (key: string) => String(raw[key] ?? "").trim() || undefined;
      // 빈 칸은 보내지 않는다. 주소만 있으면 서버가 플랫폼·스토어 ID·쇼핑몰 번호를 판별한다.
      const input = storeInputSchema.parse({
        storeUrl: text("storeUrl"),
        name: text("name"),
        platform: text("platform"),
        externalId: text("externalId"),
        shopNo: text("shopNo") ? Number(text("shopNo")) : undefined,
      });
      setError(null);
      add.mutate(input);
    } catch (error) {
      setError(error);
    }
  };
  return (
    <main>
      <h1>스토어</h1>
      <QueryState
        pending={stores.isPending}
        error={stores.error}
        retry={stores.refetch}
      />
      <ul>
        {stores.data?.map((store) => (
          <li key={store.id}>
            <Link to={`/stores/${store.id}/products`}>{store.name}</Link> (
            {platformNames[store.platform]} · {store.externalId}
            {store.platform === "cafe24" ? ` · 쇼핑몰 ${store.shopNo}번` : ""})
          </li>
        ))}
      </ul>
      {stores.data?.length === 0 && <p>등록한 스토어가 없습니다.</p>}
      {add.data && (
        <p role="status">
          {platformNames[add.data.platform]} 스토어 {add.data.externalId}
          {add.data.platform === "cafe24"
            ? ` · 쇼핑몰 ${add.data.shopNo}번`
            : ""}
          으로 등록했습니다.
        </p>
      )}
      <h2>작업 대상 등록</h2>
      <p>플랫폼 가입, 관리자 권한 부여, API 인증은 각각 진행합니다.</p>
      <form onSubmit={submit}>
        <label>
          스토어 주소
          <input
            name="storeUrl"
            maxLength={2048}
            placeholder="https://smartstore.naver.com/스토어주소"
          />
        </label>
        <label>
          스토어 이름 (선택)
          <input name="name" maxLength={100} />
        </label>
        <details>
          <summary>연결 도메인 등 주소로 판별할 수 없을 때</summary>
          <label>
            플랫폼
            <select name="platform" defaultValue="">
              <option value="">주소로 판별</option>
              <option value="cafe24">카페24</option>
              <option value="smartstore">스마트스토어</option>
            </select>
          </label>
          <label>
            스토어 ID (카페24 몰 아이디)
            <input name="externalId" maxLength={50} />
          </label>
          <label>
            쇼핑몰 번호 (카페24 다중 쇼핑몰일 때만)
            <input name="shopNo" type="number" min={1} max={1000} />
          </label>
        </details>
        <button disabled={add.isPending}>스토어 등록</button>
      </form>
      <ErrorMessage error={error ?? add.error} />
    </main>
  );
}
const jobKinds: Record<string, string> = {
  collect: "원본 수집",
  apply: "저장",
  rollback: "복구",
  verify: "재조회",
  catalog: "상품 목록",
  prepare: "AI 준비",
  forget_session: "세션 삭제",
};
const jobStatuses: Record<string, string> = {
  queued: "대기",
  running: "실행 중",
  succeeded: "완료",
  failed: "실패",
};
const managerNames = {
  not_requested: "초대 전",
  invited: "초대 확인 중",
  verified: "권한 확인됨",
  revoked: "권한 해제됨",
};
const apiNames = {
  not_connected: "미연결",
  authorized: "인증됨 · 조회 시험 전",
  read_verified: "API 조회 확인됨",
  write_verified: "API 저장·재조회 확인됨",
  revoked: "인증 해제됨",
};
function ConnectionStatus({ store }: { store: Store }) {
  const action = useShopAction(store.id);
  const session = useSession();
  const runtime = useRuntime();
  const [disconnectConfirmed, setDisconnectConfirmed] = useState(false);
  const owner = session.data?.id === store.ownerId;
  const connected =
    store.managerStatus !== "revoked" ||
    !["not_connected", "revoked"].includes(store.apiStatus);
  const invoke = (value: Parameters<typeof action.run>[0]) => {
    void action.run(value).catch(() => undefined);
  };
  return (
    <section aria-label="연결 상태">
      <h2>연결 상태</h2>
      <p>관리자 권한: {managerNames[store.managerStatus]}</p>
      <p>
        수정 방식:{" "}
        {store.editingMode === "browser" ? "관리자 화면 자동화" : "API"}
      </p>
      {store.editingMode !== "browser" && (
        <p>API 인증: {apiNames[store.apiStatus]}</p>
      )}
      <p>서버 자동 수정: {store.automaticWritesEnabled ? "켜짐" : "꺼짐"}</p>
      {store.editingMode === "browser" &&
        store.browserSession &&
        store.browserSession.status !== "ok" && (
          <p role="alert">
            담당자 브라우저: {jobMessage(store.browserSession.status)}
          </p>
        )}
      <button
        disabled={action.isPending || store.managerStatus === "verified"}
        onClick={() => invoke({ action: "manager", status: "invited" })}
      >
        관리자 초대 전달 기록
      </button>
      {store.delegatedIdentity?.storeName && (
        <p>
          확인한 가게: {store.delegatedIdentity.storeName}
          {store.delegatedIdentity.storeId
            ? ` · 고유 ID ${store.delegatedIdentity.storeId}`
            : ""}
        </p>
      )}
      {session.data?.role === "admin" && (
        <>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const values = formValues(event.currentTarget);
              invoke({
                action: "manager",
                status: "verified",
                identity: {
                  storeName: String(values.storeName ?? ""),
                  storeId: String(values.storeId ?? ""),
                },
              });
            }}
          >
            <label>
              위임 목록·관리 화면의 스토어 이름 (실행기가 그대로 대조)
              <input
                name="storeName"
                maxLength={100}
                defaultValue={store.delegatedIdentity?.storeName ?? ""}
              />
            </label>
            <label>
              위임 목록의 고유 ID (확인한 경우)
              <input
                name="storeId"
                maxLength={100}
                pattern="[A-Za-z0-9_.:-]+"
                defaultValue={store.delegatedIdentity?.storeId ?? ""}
              />
            </label>
            <button
              disabled={action.isPending || store.managerStatus === "verified"}
            >
              관리자가 편집 권한 확인
            </button>
          </form>
          <button
            disabled={action.isPending || store.managerStatus !== "verified"}
            onClick={() => invoke({ action: "manager", status: "revoked" })}
          >
            권한 회수 확인 기록
          </button>
        </>
      )}
      {store.editingMode === "browser" ? (
        <p>편집 권한이 확인되면 관리자 화면에서 상품 정보를 읽고 수정합니다.</p>
      ) : store.platform === "cafe24" ? (
        <button
          disabled={action.isPending}
          onClick={() => invoke({ action: "authorize" })}
        >
          {runtime.mode === "demo"
            ? "시연 API 인증 완료"
            : "카페24 API OAuth 연결"}
        </button>
      ) : (
        <p>
          스마트스토어 API는 공식 판매자 연결 후 관리자가 별도로 인증합니다.
        </p>
      )}
      {action.data && (
        <p>
          <a href={action.data} target="_blank" rel="noreferrer">
            카페24 인증창 열기
          </a>
          . 인증 후 이 화면으로 돌아와 최신 상태를 조회해 주세요.
        </p>
      )}
      {owner && connected && (
        <details>
          <summary>연결 해제</summary>
          <p>
            seelo의 상품 수집·저장을 멈추고 보관한 API 토큰을 폐기합니다.
            플랫폼의 매니저·부운영자·앱 권한 삭제는 판매자 관리 화면에서 직접
            진행해 주세요.
          </p>
          <label>
            <input
              type="checkbox"
              checked={disconnectConfirmed}
              onChange={(event) => setDisconnectConfirmed(event.target.checked)}
            />
            이 스토어의 seelo 연결을 해제합니다.
          </label>
          <button
            disabled={action.isPending || !disconnectConfirmed}
            onClick={() => invoke({ action: "disconnect", confirmed: true })}
          >
            연결 해제
          </button>
        </details>
      )}
      <ErrorMessage error={action.error} />
    </section>
  );
}
function sourceUrls(form: HTMLFormElement): string[] {
  return String(formValues(form).sourceUrls ?? "")
    .split(/\r?\n/)
    .map((url) => url.trim())
    .filter(Boolean);
}
// 숫자만 입력하면 상품번호, 주소면 서버가 같은 몰의 카페24 상품번호로 바꾼다.
function productTarget(value: string): ProductTarget {
  const text = value.trim();
  return /^[1-9][0-9]{0,18}$/.test(text)
    ? { externalId: productNoSchema.parse(text) }
    : { productUrl: text };
}
export function ProductsPage() {
  const { storeId: rawId = "" } = useParams();
  const id = Number(rawId);
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const candidate = Number(params.get("page"));
  const page = Number.isSafeInteger(candidate) && candidate > 0 ? candidate : 1;
  const query = (params.get("query") ?? "").slice(0, 200);
  const store = useStore(id);
  const products = useProducts(id, { page, query });
  const importer = useImportProduct(id);
  const runtime = useRuntime();
  const rawJob = Number(params.get("job"));
  const jobId = Number.isSafeInteger(rawJob) && rawJob > 0 ? rawJob : undefined;
  const job = useJob(jobId);
  const collected =
    job.data?.status === "succeeded" && job.data.shopId === id
      ? Number(job.data.result.productId)
      : undefined;
  useEffect(() => {
    if (!collected || !Number.isSafeInteger(collected)) return;
    void runtime.queryClient.invalidateQueries({
      queryKey: ["commerce", "products", id],
    });
    navigate(`/stores/${id}/products/${collected}`);
  }, [collected, id, navigate, runtime.queryClient]);
  const [error, setError] = useState<unknown>(null);
  const importProduct = async (
    event: FormEvent<HTMLFormElement>,
    manual: boolean,
  ) => {
    event.preventDefault();
    if (importer.isPending) return;
    const raw = formValues(event.currentTarget);
    setError(null);
    try {
      const result = await importer.mutateAsync(
        manual
          ? manualSnapshotSchema.parse({
              externalId: raw.externalId,
              name: raw.name,
              identity: raw.identity,
              fields: { description: String(raw.description) },
            })
          : productTarget(String(raw.externalId)),
      );
      if (result.kind === "job")
        // 브라우저 수집은 worker가 실행한다. 작업 번호를 주소에 남겨 새로고침해도 이어서 조회한다.
        setParams({
          ...Object.fromEntries(params),
          job: String(result.job.id),
        });
      else navigate(`/stores/${id}/products/${result.product.id}`);
    } catch (error) {
      setError(error);
    }
  };
  if (!Number.isSafeInteger(id) || id <= 0)
    return <p role="alert">스토어 번호가 올바르지 않습니다.</p>;
  return (
    <main>
      <h1>상품</h1>
      <Link to="/stores">스토어 목록</Link>
      <QueryState
        pending={store.isPending}
        error={store.error}
        retry={store.refetch}
      />
      {store.data && (
        <>
          <ConnectionStatus store={store.data} />
          <h2>플랫폼 원본 수집</h2>
          <form onSubmit={(event) => void importProduct(event, false)}>
            <label>
              {store.data.platform === "cafe24"
                ? "상품번호 또는 카페24 상품 주소"
                : "원상품번호"}
              <input name="externalId" required maxLength={2048} />
            </label>
            {store.data.platform === "smartstore" && (
              <p>
                공개 상품 주소의 번호는 원상품번호와 다를 수 있습니다.
                판매자센터 상품 목록의 원상품번호를 입력해 주세요.
              </p>
            )}
            <button
              disabled={
                importer.isPending ||
                (store.data.editingMode === "browser"
                  ? store.data.managerStatus !== "verified"
                  : ["not_connected", "revoked"].includes(store.data.apiStatus))
              }
            >
              {store.data.editingMode === "browser"
                ? "관리자 화면에서 원본 수집"
                : "API로 원본 수집"}
            </button>
          </form>
          <details>
            <summary>판매자가 제공한 원본으로 준비</summary>
            <p>
              직접 수집한 원본과 구분해 저장합니다. 판매자가 제공한 원본만으로
              자동 수정을 실행하지 않습니다.
            </p>
            <form onSubmit={(event) => void importProduct(event, true)}>
              <label>
                상품번호
                <input name="externalId" required />
              </label>
              <label>
                상품명
                <input name="name" required maxLength={250} />
              </label>
              <label>
                모델·옵션 식별값
                <input name="identity" required maxLength={250} />
              </label>
              <label>
                현재 상세설명
                <textarea name="description" required maxLength={200000} />
              </label>
              <button disabled={importer.isPending}>제공 원본 등록</button>
            </form>
          </details>
          {job.data && job.data.shopId === id && (
            <p role="status">
              {job.data.status === "failed"
                ? `원본 수집 실패: ${jobMessage(job.data.errorCode)}`
                : job.data.stale
                  ? "수집 작업이 오래 멈췄습니다. 다시 수집할 수 있습니다."
                  : job.data.status === "succeeded"
                    ? "원본 수집 완료"
                    : `관리 화면에서 원본을 수집하고 있습니다 (${job.data.status === "queued" ? "대기" : "실행 중"}).`}
            </p>
          )}
          <ErrorMessage error={error ?? importer.error ?? job.error} />
        </>
      )}
      {store.data?.editingMode === "browser" && (
        <CatalogSection
          storeId={id}
          verified={store.data.managerStatus === "verified"}
          busy={importer.isPending}
          onImport={(productNo) =>
            void importer
              .mutateAsync({ externalId: productNo })
              .then((result) =>
                result.kind === "job"
                  ? setParams({
                      ...Object.fromEntries(params),
                      job: String(result.job.id),
                    })
                  : navigate(`/stores/${id}/products/${result.product.id}`),
              )
              .catch(setError)
          }
        />
      )}
      <h2>seelo에 가져온 상품</h2>
      <p>
        원본을 수집한 상품만 서버에서 검색합니다. 플랫폼의 전체 상품 목록이
        아닙니다.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setParams({
            query: String(formValues(event.currentTarget).query).trim(),
            page: "1",
          });
        }}
      >
        <label>
          상품 검색
          <input
            key={query}
            name="query"
            defaultValue={query}
            maxLength={200}
          />
        </label>
        <button>검색</button>
      </form>
      <QueryState
        pending={products.isPending}
        error={products.error}
        retry={products.refetch}
      />
      <ul>
        {products.data?.items.map((product) => (
          <li key={product.id}>
            <Link to={`/stores/${id}/products/${product.id}`}>
              {product.name}
            </Link>{" "}
            ·{" "}
            {product.snapshotSource === "browser"
              ? "관리자 화면 수집"
              : product.snapshotSource === "api"
                ? "API 수집"
                : "판매자 제공 원본"}
          </li>
        ))}
      </ul>
      {products.data?.items.length === 0 && <p>조회한 상품이 없습니다.</p>}
      <button
        disabled={page === 1}
        onClick={() => setParams({ query, page: String(page - 1) })}
      >
        이전
      </button>
      <span> {page}페이지 </span>
      <button
        disabled={
          !products.data || page * products.data.pageSize >= products.data.total
        }
        onClick={() => setParams({ query, page: String(page + 1) })}
      >
        다음
      </button>
      {products.data && <span> · 전체 {products.data.total}개</span>}
    </main>
  );
}
// 위임받은 관리 화면의 플랫폼 상품 목록. 가져온 상품 목록과 구분해 보여 준다.
function CatalogSection({
  storeId,
  verified,
  busy,
  onImport,
}: {
  storeId: number;
  verified: boolean;
  busy: boolean;
  onImport: (productNo: string) => void;
}) {
  const runtime = useRuntime();
  const catalog = useCatalog(storeId, verified);
  const [jobId, setJobId] = useState<number>();
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const job = useJob(jobId);
  const finished = job.data?.status === "succeeded" ? job.data.id : undefined;
  useEffect(() => {
    if (finished)
      void runtime.queryClient.invalidateQueries({
        queryKey: ["commerce", "catalog", storeId],
      });
  }, [finished, runtime.queryClient, storeId]);
  const request = async () => {
    setError(null);
    setPending(true);
    try {
      const result = await runtime.gateway.requestCatalog(storeId);
      if (result.kind === "job") setJobId(result.job.id);
      else
        runtime.queryClient.setQueryData(
          ["commerce", "catalog", storeId],
          result.catalog,
        );
    } catch (error) {
      setError(error);
    } finally {
      setPending(false);
    }
  };
  return (
    <section aria-label="플랫폼 상품 목록">
      <h2>플랫폼 상품 목록 (관리 화면 조회)</h2>
      <p>
        위임받은 관리 화면에서 가게를 대조한 뒤 상품번호와 이름만 읽습니다. 고를
        상품을 가져오면 원본을 수집합니다.
      </p>
      <button
        disabled={
          !verified || pending || Boolean(job.data && activeJob(job.data))
        }
        onClick={() => void request()}
      >
        관리 화면에서 상품 목록 조회
      </button>
      {job.data && (
        <p role="status">
          {job.data.status === "failed"
            ? `목록 조회 실패: ${jobMessage(job.data.errorCode)}`
            : job.data.status === "succeeded"
              ? "목록 조회 완료"
              : "목록을 조회하고 있습니다."}
        </p>
      )}
      <ErrorMessage error={error ?? catalog.error} />
      {catalog.data?.collectedAt && (
        <p>
          조회 시각: {catalog.data.collectedAt} · {catalog.data.items.length}개
          {catalog.data.truncated ? " (일부만 조회)" : ""}
        </p>
      )}
      <ul aria-label="플랫폼 상품">
        {catalog.data?.items.map((item) => (
          <li key={item.productNo}>
            {item.name} · {item.productNo}{" "}
            {item.importedProductId ? (
              <Link
                to={`/stores/${storeId}/products/${item.importedProductId}`}
              >
                가져온 상품 열기
              </Link>
            ) : (
              <button disabled={busy} onClick={() => onImport(item.productNo)}>
                가져오기
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
export function WorkspacePage() {
  const params = useParams();
  const [search] = useSearchParams();
  const storeId = Number(params.storeId);
  const productId = Number(params.productId);
  const workspace = useWorkspace(storeId, productId);
  const rawPlan = Number(search.get("plan"));
  const selectedPlanId =
    Number.isSafeInteger(rawPlan) && rawPlan > 0 ? rawPlan : undefined;
  if (
    !Number.isSafeInteger(storeId) ||
    storeId <= 0 ||
    !Number.isSafeInteger(productId) ||
    productId <= 0
  )
    return <p role="alert">상품 경로가 올바르지 않습니다.</p>;
  return (
    <main>
      <h1>상품 정비</h1>
      <Link to={`/stores/${storeId}/products`}>상품 목록</Link>
      <button
        onClick={() => void workspace.refetch()}
        disabled={workspace.isFetching}
      >
        최신 상태 조회
      </button>
      <QueryState
        pending={workspace.isPending}
        error={workspace.error}
        retry={workspace.refetch}
      />
      {workspace.data && (
        <>
          <ConnectionStatus store={workspace.data.store} />
          <WorkspaceForm
            key={`${productId}/${latestPlan(workspace.data)?.id ?? "none"}/${selectedPlanId ?? "latest"}/${workspace.data.product.snapshotHash}`}
            workspace={workspace.data}
            selectedPlanId={selectedPlanId}
          />
          <MeasureSection productId={workspace.data.product.id} />
        </>
      )}
    </main>
  );
}
function WorkspaceForm({
  workspace,
  selectedPlanId,
}: {
  workspace: Workspace;
  selectedPlanId?: number;
}) {
  const command = useCommand(workspace.store.id, workspace.product.id);
  const session = useSession();
  const [error, setError] = useState<unknown>(null);
  const [approved, setApproved] = useState(false);
  const [restore, setRestore] = useState(false);
  const latest = latestPlan(workspace);
  // 이력에서 고른 정비안의 상세·쓰기 이력·복구를 다룬다. 승인·답변은 최신 정비안에서만 받는다.
  const plan = planById(workspace, selectedPlanId) ?? latest;
  const isLatest = plan !== undefined && plan.id === latest?.id;
  const planWrites = useWrites(plan?.id);
  const writes = planWrites.data ?? (isLatest ? workspace.writes : []);
  const [selected, setSelected] = useState<Field[]>(
    plan?.approval?.fields ?? plan?.changes.map((change) => change.field) ?? [],
  );
  const [editorConfirmed, setEditorConfirmed] = useState(false);
  const editorConsent =
    workspace.store.platform === "smartstore" &&
    plan?.changes.some(
      (change) =>
        selected.includes(change.field) &&
        change.field === "description" &&
        change.method === "api",
    );
  const busy = command.isPending || isRunning(workspace);
  const admin = session.data?.role === "admin";
  // 고객(소유자)이 자료 보완·생성·승인을 한다. 운영자는 고객이 승인한 정비안만 실행한다.
  const owner = !session.data || session.data.id === workspace.store.ownerId;
  const canExecute = (target: typeof plan) =>
    Boolean(
      target && (owner || (admin && customerApproved(workspace, target))),
    );
  const active = workspace.plans.some((plan) =>
    ["approved", "applying", "pending_reflection", "uncertain"].includes(
      plan.status,
    ),
  );
  const prepareJob = workspace.product.prepareJob;
  const run = async (value: Command): Promise<boolean> => {
    setError(null);
    try {
      await command.run(value);
      return true;
    } catch (error) {
      setError(error);
      return false;
    }
  };
  const facts = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    try {
      const fact = factInputSchema.parse({
        ...formValues(event.currentTarget),
        identity: workspace.product.identity,
      });
      void run({ action: "facts", facts: [fact] });
    } catch (error) {
      setError(error);
    }
  };
  const generate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    try {
      const input = generateSchema.parse({
        fields: data.getAll("fields"),
        requiredFacts: data.getAll("requiredFacts"),
        useAi: data.get("useAi") === "on",
        allowEditorConversion: data.get("allowEditorConversion") === "on",
      });
      void run({ action: "generate", ...input });
    } catch (error) {
      setError(error);
    }
  };
  return (
    <section>
      <h2>{workspace.product.name}</h2>
      <p role="status">{stageOf(workspace)}</p>
      <p>모델·옵션: {workspace.product.identity}</p>
      <p>
        원본:{" "}
        {workspace.product.snapshotSource === "browser"
          ? "관리자 화면 수집"
          : workspace.product.snapshotSource === "api"
            ? "API 수집"
            : "판매자 제공"}{" "}
        · 해시: {workspace.product.snapshotHash}
      </p>
      <details>
        <summary>수집한 원본 값</summary>
        <pre>{JSON.stringify(workspace.product.fields, null, 2)}</pre>
      </details>
      <ErrorMessage error={error ?? command.error} />
      <h3>AI 정비 준비</h3>
      <p>
        원본을 수집하면 AI가 기존 본문·본문 속 공식 자료를 먼저 읽고, 이 상품에
        필요한 정보를 판단해 정비안을 만듭니다. 확인하지 못한 필수 정보만
        묻습니다.
      </p>
      {prepareJob && (
        <p role="status">
          AI 준비:{" "}
          {prepareJob.status === "failed"
            ? `실패 · ${jobMessage(prepareJob.errorCode)}`
            : prepareJob.stale
              ? "오래 멈춤 · 다시 실행할 수 있습니다."
              : prepareJob.status === "succeeded"
                ? "완료"
                : prepareJob.status === "running"
                  ? "자료를 조사하고 정비안을 만드는 중"
                  : "대기"}
        </p>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void run({
            action: "prepare",
            sourceUrls: sourceUrls(event.currentTarget),
          });
        }}
      >
        <label>
          추가 공식 자료 주소 (선택, 한 줄에 하나·최대 3개)
          <textarea name="sourceUrls" />
        </label>
        <button disabled={busy || active || !owner}>
          AI가 조사하고 정비안 만들기
        </button>
      </form>
      <h3>같은 모델·옵션의 근거</h3>
      <ul>
        {workspace.product.facts.map((fact) => (
          <li key={fact.key}>
            {factNames[fact.key]}: {fact.value}
            {fact.quantities?.length
              ? ` (수치: ${fact.quantities.map((q) => `${q.amount} ${q.unit}`).join(", ")})`
              : ""}{" "}
            ·{" "}
            {fact.source_url ? (
              <a href={fact.source_url} target="_blank" rel="noreferrer">
                근거 출처
              </a>
            ) : (
              "판매자 답변"
            )}
          </li>
        ))}
      </ul>
      <details>
        <summary>직접 보완·범위 지정 (선택)</summary>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void run({
              action: "research",
              sourceUrls: sourceUrls(event.currentTarget),
            });
          }}
        >
          <label>
            조사할 공식 자료 주소 (한 줄에 하나·최대 3개)
            <textarea name="sourceUrls" />
          </label>
          <button disabled={busy || !owner}>자료 조사만 다시 실행</button>
        </form>
        <form onSubmit={facts}>
          <label>
            정보 종류
            <select name="key">
              {Object.entries(factNames).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            확인한 값<input name="value" required maxLength={1000} />
          </label>
          <label>
            근거 주소
            <input name="sourceUrl" type="url" required />
          </label>
          <label>
            값이 포함된 인용문
            <textarea name="quote" required maxLength={4000} />
          </label>
          <button disabled={busy || !owner}>근거 저장</button>
        </form>
        <h3>정비할 항목 선택</h3>
        <form onSubmit={generate}>
          <fieldset disabled={busy || active}>
            <legend>변경할 필드</legend>
            {workspace.product.fieldSupport.automatic.map((field) => (
              <label key={field}>
                <input
                  name="fields"
                  type="checkbox"
                  value={field}
                  defaultChecked={field === "description"}
                />
                {fieldNames[field]}
              </label>
            ))}
            {workspace.product.fieldSupport.manual.map((field) => (
              <label key={field}>
                <input name="fields" type="checkbox" value={field} />
                {fieldNames[field]} (관리자 수동 편집)
              </label>
            ))}
            {workspace.product.fieldSupport.unavailable.length > 0 && (
              <ul aria-label="현재 수정 방식에서 지원하지 않는 항목">
                {workspace.product.fieldSupport.unavailable.map((item) => (
                  <li key={item.field}>
                    {fieldNames[item.field]}:{" "}
                    {unavailableReasons[item.reason] ?? item.reason}
                  </li>
                ))}
              </ul>
            )}
          </fieldset>
          <fieldset disabled={busy || active}>
            <legend>자료에서 확인할 필수 사실</legend>
            {Object.entries(factNames).map(([key, label]) => (
              <label key={key}>
                <input name="requiredFacts" type="checkbox" value={key} />
                {label}
              </label>
            ))}
          </fieldset>
          <label>
            <input
              name="useAi"
              type="checkbox"
              defaultChecked
              disabled={busy || active}
            />
            AI로 확인한 사실의 순서 정렬
          </label>
          {workspace.product.fieldSupport.conditions.description ===
            "editor_conversion_approval" && (
            <label>
              <input
                name="allowEditorConversion"
                type="checkbox"
                disabled={busy || active}
              />
              상세설명 API 적용 시 HTML 형식 전환을 허용합니다.
            </label>
          )}
          <button disabled={busy || active || !owner}>
            선택한 항목으로 정비안 생성
          </button>
        </form>
      </details>
      {!owner && <p>자료 보완·정비안 생성·승인은 고객 계정에서 진행합니다.</p>}
      {selectedPlanId !== undefined && !planById(workspace, selectedPlanId) && (
        <p role="alert">선택한 정비안을 찾지 못해 최신 정비안을 표시합니다.</p>
      )}
      {plan && (
        <section aria-label="선택한 정비안">
          <h3>
            정비안 #{plan.id}
            {isLatest ? " (최신)" : " (이전 정비안)"}
          </h3>
          <p>상태: {plan.status}</p>
          {plan.job && (
            <p role="status">
              관리 화면 작업({jobKinds[plan.job.kind]}):{" "}
              {plan.job.status === "failed"
                ? `실패 · ${jobMessage(plan.job.errorCode)}`
                : plan.job.stale
                  ? "오래 멈춤 · 저장 여부는 재조회로 확인"
                  : jobStatuses[plan.job.status]}
            </p>
          )}
          <p>생성 모델: {plan.modelId ?? "규칙 기반"}</p>
          {plan.approval?.fields && (
            <p>
              승인한 항목:{" "}
              {plan.approval.fields
                .map((field) => fieldNames[field])
                .join(", ")}
            </p>
          )}
          <table>
            <thead>
              <tr>
                <th>승인 선택</th>
                <th>항목</th>
                <th>현재 값</th>
                <th>변경 값</th>
                <th>실행 방법·근거</th>
              </tr>
            </thead>
            <tbody>
              {plan.changes.map((change) => (
                <tr key={change.field}>
                  <td>
                    <input
                      aria-label={`${fieldNames[change.field]} 승인 선택`}
                      type="checkbox"
                      disabled={busy || plan.status !== "draft"}
                      checked={selected.includes(change.field)}
                      onChange={(event) =>
                        setSelected((current) =>
                          event.target.checked
                            ? [...current, change.field]
                            : current.filter((field) => field !== change.field),
                        )
                      }
                    />
                  </td>
                  <th>{fieldNames[change.field]}</th>
                  <td>
                    <pre>{change.before}</pre>
                  </td>
                  <td>
                    <pre>{change.proposed}</pre>
                  </td>
                  <td>
                    {change.method === "browser"
                      ? "관리자 화면 자동화"
                      : change.method === "api"
                        ? "API"
                        : "관리자 수동 편집"}
                    <ul>
                      {change.evidence.map((fact) => (
                        <li key={fact.key}>
                          {factNames[fact.key]}: {fact.value}
                        </li>
                      ))}
                    </ul>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {plan.deferred.length > 0 && (
            <p>
              보류:{" "}
              {plan.deferred
                .map((key) =>
                  key.startsWith("fact:")
                    ? factNames[key.slice(5) as FactKey]
                    : (fieldNames[key as keyof typeof fieldNames] ?? key),
                )
                .join(", ")}
            </p>
          )}
          {isLatest && plan.questions.length > 0 && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const values = formValues(event.currentTarget);
                // 답변을 저장하면 같은 기본 흐름으로 정비안을 다시 만든다.
                void run({
                  action: "answers",
                  answers: Object.fromEntries(
                    Object.entries(values).filter(([, value]) =>
                      String(value).trim(),
                    ),
                  ),
                }).then(
                  (saved) =>
                    saved && run({ action: "prepare", sourceUrls: [] }),
                );
              }}
            >
              <h4>필요한 정보 보완</h4>
              {plan.questions.map((question) => (
                <label key={question.field}>
                  {question.text}
                  <input name={question.field} maxLength={1000} />
                </label>
              ))}
              <button disabled={busy || active || !owner}>답변 저장</button>
              <p>답변을 저장하면 AI가 정비안을 다시 만듭니다.</p>
            </form>
          )}
          {isLatest && plan.status === "draft" && !owner && (
            <p>고객 승인 대기 · 운영자는 승인할 수 없습니다.</p>
          )}
          {isLatest && plan.status === "draft" && owner && (
            <>
              {editorConsent && (
                <label>
                  <input
                    type="checkbox"
                    checked={editorConfirmed}
                    onChange={(event) =>
                      setEditorConfirmed(event.target.checked)
                    }
                  />
                  선택한 상세설명의 HTML 전환을 별도로 확인했습니다.
                </label>
              )}
              <label>
                <input
                  type="checkbox"
                  checked={approved}
                  onChange={(event) => setApproved(event.target.checked)}
                />
                선택한 변경 값을 확인했습니다.
              </label>
              <button
                disabled={
                  busy ||
                  !approved ||
                  !validChanges(workspace, plan, selected) ||
                  Boolean(editorConsent && !editorConfirmed)
                }
                onClick={() =>
                  void run({
                    action: "approve",
                    planId: plan.id,
                    snapshotHash: workspace.product.snapshotHash,
                    fields: selected,
                    editorConversionConfirmed: editorConfirmed,
                  })
                }
              >
                정비안 승인
              </button>
            </>
          )}
          {plan.status === "approved" && !canExecute(plan) && (
            <p>고객이 직접 승인한 기록이 없어 운영자가 실행할 수 없습니다.</p>
          )}
          {plan.status === "approved" && canExecute(plan) && (
            <button
              disabled={busy}
              onClick={() => void run({ action: "apply", planId: plan.id })}
            >
              {approvedChanges(plan).some(
                (change) => change.method === "manual",
              )
                ? "수동 편집 요청"
                : "승인한 변경 적용"}
            </button>
          )}
          {verifiableStatuses.includes(plan.status) && (
            <button
              disabled={command.isPending}
              onClick={() => void run({ action: "verify", planId: plan.id })}
            >
              {editingLabel(workspace)}에서 저장 결과 재조회
            </button>
          )}
          {plan.status === "applied" && canExecute(plan) && (
            <>
              <h4>원본 값 복구</h4>
              <label>
                <input
                  type="checkbox"
                  checked={restore}
                  onChange={(event) => setRestore(event.target.checked)}
                />
                승인한 필드의 수정 전 값으로 복구합니다.
              </label>
              {!isLatest && (
                <p>
                  이전 정비안입니다. 이후 정비안이 같은 항목을 바꿨다면 서버가
                  원본 충돌로 복구를 중단합니다.
                </p>
              )}
              {workspace.store.platform === "smartstore" &&
                workspace.product.fieldSupport.mode === "api" && (
                  <p>편집기 형식의 복구는 별도 확인이 필요합니다.</p>
                )}
              <button
                disabled={busy || !restore}
                onClick={() =>
                  void run({
                    action: "rollback",
                    planId: plan.id,
                    confirmed: true,
                  })
                }
              >
                원본 값 복구
              </button>
            </>
          )}
          <h4>공개 반영</h4>
          <p>
            PC:{" "}
            {plan.publication.pc_matches === true
              ? "일치 확인"
              : plan.publication.pc_matches === false
                ? "불일치"
                : "미확인"}{" "}
            · 모바일:{" "}
            {plan.publication.mobile_matches === true
              ? "일치 확인"
              : plan.publication.mobile_matches === false
                ? "불일치"
                : "미확인"}
          </p>
          {publicationComplete(plan) && (
            <p>확인 시각: {plan.publication.checked_at}</p>
          )}
          {workspace.store.platform === "cafe24" && (
            <p>
              Google 등 외부 채널로 전송하는 필드와 수신 값은 별도 확인이
              필요합니다.
            </p>
          )}
          {admin && ["approved", "manual_required"].includes(plan.status) && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const values = formValues(event.currentTarget);
                if (values.confirmed !== "on") return;
                void run({
                  action: "manual-result",
                  planId: plan.id,
                  values: Object.fromEntries(
                    approvedChanges(plan).map((change) => [
                      change.field,
                      change.proposed,
                    ]),
                  ),
                  note: String(values.note),
                });
              }}
            >
              <h4>관리자 수동 편집 기록</h4>
              <label>
                <input name="confirmed" type="checkbox" required />
                관리 화면에 승인한 모든 값을 저장하고 재조회했습니다.
              </label>
              <label>
                작업 기록
                <textarea name="note" required maxLength={1000} />
              </label>
              <button
                disabled={busy || workspace.store.managerStatus !== "verified"}
              >
                수동 편집 결과 기록
              </button>
            </form>
          )}
          {admin &&
            ["applied", "manual_recorded", "rolled_back"].includes(
              plan.status,
            ) && (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  const values = formValues(event.currentTarget);
                  void run({
                    action: "publication",
                    planId: plan.id,
                    pcUrl: String(values.pcUrl),
                    mobileUrl: String(values.mobileUrl),
                    pcMatches: values.pcMatches === "on",
                    mobileMatches: values.mobileMatches === "on",
                    note: String(values.note),
                  });
                }}
              >
                <h4>관리자 공개 반영 확인</h4>
                <label>
                  PC 주소
                  <input name="pcUrl" type="url" required />
                </label>
                <label>
                  모바일 주소
                  <input name="mobileUrl" type="url" required />
                </label>
                <label>
                  <input name="pcMatches" type="checkbox" />
                  PC 값 일치
                </label>
                <label>
                  <input name="mobileMatches" type="checkbox" />
                  모바일 값 일치
                </label>
                <label>
                  확인 기록
                  <textarea name="note" required maxLength={1000} />
                </label>
                <button disabled={busy}>공개 반영 확인 기록</button>
              </form>
            )}
        </section>
      )}
      <details open={!isLatest}>
        <summary>
          {plan ? `정비안 #${plan.id}의 쓰기 이력` : "쓰기 이력"}
        </summary>
        <ErrorMessage error={planWrites.error} />
        {writes.length ? (
          writes.map((write) => (
            <pre key={write.id}>{JSON.stringify(write, null, 2)}</pre>
          ))
        ) : (
          <p>쓰기 이력이 없습니다.</p>
        )}
      </details>
      <details open={!isLatest}>
        <summary>정비안 이력</summary>
        <ul>
          {workspace.plans.map((item) => (
            <li key={item.id}>
              <Link
                to={`?plan=${item.id}`}
                aria-current={item.id === plan?.id ? "true" : undefined}
              >
                #{item.id}
              </Link>
              : {item.status}
              {item.id === latest?.id ? " · 최신" : ""}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
