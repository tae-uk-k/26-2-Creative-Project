import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ChevronRight,
  Copy,
  ExternalLink,
  PackagePlus,
  Plus,
  Search,
  Settings,
} from "lucide-react";
import {
  activeJob,
  useAddStore,
  useCatalog,
  useImportProduct,
  useJob,
  useProducts,
  useShopAction,
  useStore,
  useStores,
} from "../app/commerce";
import { useRuntime, useSession } from "../app/runtime";
import {
  apiStoreSteps,
  storeReady,
  storeStage,
  storeSteps,
  summaryState,
} from "../commerce/progress";
import { jobMessage } from "../commerce/rules";
import {
  manualSnapshotSchema,
  platformNames,
  productNoSchema,
  storeInputSchema,
  type Platform,
  type ProductTarget,
  type Store,
} from "../commerce/schemas";
import { Button, ButtonLink, ExternalButton, TextButton } from "../ui/Button";
import { Badge, EmptyState, Notice, Panel } from "../ui/Display";
import { Checkbox, InlineForm, Select, TextArea, TextField } from "../ui/Field";
import { CardGrid, Page, PageHeader, Stack } from "../ui/Layout";
import { Card, CardTop, List, ListRow } from "../ui/List";
import { ConfirmDialog } from "../ui/Overlay";
import { Stepper, Timeline, type StepState } from "../ui/Steps";
import { PlatformMark } from "../ui/AppShell";
import { apiLabels, managerLabels, managerTones, when } from "../ui/labels";
import { ErrorMessage, InvalidPath, QueryState, formValues } from "./common";
import styles from "./stores.module.css";

const storeLine = (store: Store) =>
  `${platformNames[store.platform]} · ${store.externalId}${
    store.platform === "cafe24" && store.shopNo > 1
      ? ` · ${store.shopNo}번 쇼핑몰`
      : ""
  }`;
function StoreTitle({ store }: { store: Store }) {
  return (
    <span className={styles.storeName}>
      <strong>{store.name}</strong>
      <span>{storeLine(store)}</span>
    </span>
  );
}
function ConnectionBadge({ store }: { store: Store }) {
  if (store.editingMode !== "browser")
    return storeReady(store) ? (
      <Badge tone="green" dot>
        연결됨
      </Badge>
    ) : (
      <Badge dot>API 연결 전</Badge>
    );
  return (
    <Badge tone={managerTones[store.managerStatus]} dot>
      {managerLabels[store.managerStatus]}
    </Badge>
  );
}
export function StoresPage() {
  const stores = useStores();
  return (
    <Page>
      <PageHeader
        title="스토어"
        actions={
          stores.data?.length ? (
            <ButtonLink to="/stores/new" icon={<Plus aria-hidden="true" />}>
              스토어 연결
            </ButtonLink>
          ) : undefined
        }
      />
      <QueryState
        pending={stores.isPending}
        error={stores.error}
        retry={stores.refetch}
      />
      {stores.data?.length === 0 && (
        <Panel>
          <EmptyState
            image="/images/stores-studio.webp"
            title="첫 스토어를 연결하세요"
            action={
              <ButtonLink to="/stores/new" size="lg">
                스토어 연결
              </ButtonLink>
            }
          >
            스마트스토어나 카페24 주소만 있으면 됩니다.
          </EmptyState>
        </Panel>
      )}
      {!!stores.data?.length && (
        <CardGrid label="연결한 스토어">
          {stores.data.map((store) => {
            const steps =
              store.editingMode === "browser" ? storeSteps : apiStoreSteps;
            return (
              <Card key={store.id} to={`/stores/${store.id}`}>
                <CardTop>
                  <PlatformMark platform={store.platform} />
                  <StoreTitle store={store} />
                </CardTop>
                {/* 연결을 마친 스토어에는 다 찬 단계 표시가 필요 없다. */}
                {!storeReady(store) && (
                  <Stepper
                    label={`${store.name} 연결 단계`}
                    steps={steps}
                    current={storeStage(store)}
                    error={store.managerStatus === "revoked"}
                  />
                )}
                <div className={styles.cardFoot}>
                  <ConnectionBadge store={store} />
                  <ChevronRight size={18} aria-hidden="true" />
                </div>
              </Card>
            );
          })}
        </CardGrid>
      )}
    </Page>
  );
}
// 주소만 보고 플랫폼을 미리 알려 준다. 실제 판별은 서버가 한다.
function guessPlatform(
  value: string,
): { platform: Platform; id: string } | null {
  try {
    const url = new URL(value.includes("://") ? value : `https://${value}`);
    const host = url.hostname.toLowerCase();
    if (host.endsWith("smartstore.naver.com")) {
      const id = url.pathname.split("/").filter(Boolean)[0];
      return id ? { platform: "smartstore", id } : null;
    }
    if (host.endsWith(".cafe24.com"))
      return { platform: "cafe24", id: host.split(".")[0] };
  } catch {
    return null;
  }
  return null;
}
export function StoreNewPage() {
  const add = useAddStore();
  const navigate = useNavigate();
  const [address, setAddress] = useState("");
  const [error, setError] = useState<unknown>(null);
  const guess = useMemo(() => guessPlatform(address.trim()), [address]);
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
      add.mutate(input, {
        onSuccess: (store) => navigate(`/stores/${store.id}`),
      });
    } catch (error) {
      setError(error);
    }
  };
  return (
    <Page width="narrow">
      <PageHeader back={{ to: "/stores", label: "스토어" }} title="스토어 연결">
        <Stepper label="스토어 연결 단계" steps={storeSteps} current={0} />
      </PageHeader>
      <Panel>
        <form onSubmit={submit} style={{ display: "grid", gap: "1.25rem" }}>
          <TextField
            label="스토어 주소"
            name="storeUrl"
            maxLength={2048}
            inputMode="url"
            autoComplete="url"
            placeholder="smartstore.naver.com/내스토어"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
          />
          <div
            className={[styles.detect, guess && styles.found]
              .filter(Boolean)
              .join(" ")}
            aria-live="polite"
          >
            {guess ? (
              <>
                <PlatformMark platform={guess.platform} size="2.25rem" />
                <span>
                  <strong>{platformNames[guess.platform]}</strong> · {guess.id}
                </span>
              </>
            ) : (
              <span>스마트스토어·카페24 주소를 넣으면 바로 알아봅니다.</span>
            )}
          </div>
          <TextField label="스토어 이름 (선택)" name="name" maxLength={100} />
          <details className={styles.more}>
            <summary>연결 도메인이라 주소로 찾지 못할 때</summary>
            <div className={styles.moreBody}>
              <Select label="플랫폼" name="platform" defaultValue="">
                <option value="">주소로 판별</option>
                <option value="cafe24">카페24</option>
                <option value="smartstore">스마트스토어</option>
              </Select>
              <TextField
                label="스토어 ID (카페24 몰 아이디)"
                name="externalId"
                maxLength={50}
              />
              <TextField
                label="쇼핑몰 번호 (카페24 다중 쇼핑몰일 때만)"
                name="shopNo"
                type="number"
                min={1}
                max={1000}
              />
            </div>
          </details>
          <ErrorMessage error={error ?? add.error} />
          <Button type="submit" size="lg" block loading={add.isPending}>
            스토어 등록
          </Button>
        </form>
      </Panel>
    </Page>
  );
}
// 이 스토어의 주인(판매자)인지, seelo 운영자인지. 두 화면에 보이는 행동을 가른다.
function useStoreViewer(store: Store) {
  const session = useSession();
  return {
    owner: !session.data || session.data.id === store.ownerId,
    admin: session.data?.role === "admin",
  };
}
function useStoreId() {
  const { storeId = "" } = useParams();
  const id = Number(storeId);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}
export function StoreHomePage() {
  const id = useStoreId();
  const store = useStore(id ?? 0);
  if (id === null) return <InvalidPath />;
  return (
    <Page width="medium">
      <QueryState
        pending={store.isPending}
        error={store.error}
        retry={store.refetch}
      />
      {store.data && <StoreHome store={store.data} />}
    </Page>
  );
}
// 연결을 마친 스토어는 상품 목록을 먼저 보여 준다. 연결 단계는 연결 전에만 보여 준다.
function StoreHome({ store }: { store: Store }) {
  const browser = store.editingMode === "browser";
  const ready = storeReady(store);
  const viewer = useStoreViewer(store);
  return (
    <>
      <PageHeader
        back={
          viewer.owner
            ? { to: "/stores", label: "스토어" }
            : { to: "/operator?tab=shops", label: "고객 스토어" }
        }
        eyebrow={
          <>
            <PlatformMark platform={store.platform} size="1.75rem" />
            {storeLine(store)}
          </>
        }
        title={store.name}
        actions={
          <ButtonLink
            to={`/stores/${store.id}/settings`}
            variant="ghost"
            size="sm"
            icon={<Settings aria-hidden="true" />}
          >
            연결 관리
          </ButtonLink>
        }
      >
        {!ready && (
          <Stepper
            label="스토어 연결 단계"
            steps={browser ? storeSteps : apiStoreSteps}
            current={storeStage(store)}
            error={store.managerStatus === "revoked"}
          />
        )}
      </PageHeader>
      <Stack>
        {/* seelo 담당자 브라우저 상태다. 판매자가 할 수 있는 일이 없어 운영자에게만 보인다. */}
        {viewer.admin &&
          browser &&
          store.browserSession &&
          store.browserSession.status !== "ok" && (
            <Notice tone="warning" title="담당자 로그인이 필요해요">
              {jobMessage(store.browserSession.status)}
            </Notice>
          )}
        {ready ? (
          <ProductsSection store={store} />
        ) : browser ? (
          <Delegation store={store} />
        ) : (
          <ApiConnect store={store} />
        )}
      </Stack>
    </>
  );
}
function CopyButton({ label, value }: { label: string; value: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className={styles.copy}
      onClick={() => {
        void navigator.clipboard?.writeText(value).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1600);
        });
      }}
      aria-label={`${label} ${value} 복사`}
    >
      <small>{label}</small>
      {value}
      <Copy aria-hidden="true" />
      {done && <span className="visually-hidden">복사했어요</span>}
    </button>
  );
}
function MenuPath({ items }: { items: string[] }) {
  return (
    <div className={styles.path} aria-label={`메뉴 경로 ${items.join(" > ")}`}>
      {items.map((item, index) => (
        <span key={item} style={{ display: "contents" }}>
          {index > 0 && (
            <ChevronRight className={styles.sep} aria-hidden="true" />
          )}
          <span
            className={[styles.crumb, index === items.length - 1 && styles.last]
              .filter(Boolean)
              .join(" ")}
          >
            {item}
          </span>
        </span>
      ))}
    </div>
  );
}
// 초대할 seelo 담당자 정보. 빌드 설정에서 받는다(VITE_SEELO_MANAGER_NAME·PHONE).
function managerContact(demo: boolean) {
  const name = import.meta.env.VITE_SEELO_MANAGER_NAME as string | undefined;
  const phone = import.meta.env.VITE_SEELO_MANAGER_PHONE as string | undefined;
  if (name && phone) return { name, phone };
  return demo ? { name: "seelo 시연 담당자", phone: "010-0000-0000" } : null;
}
const guides: Record<
  Platform,
  {
    admin: string;
    adminLabel: string;
    path: string[];
    steps: (contact: ReturnType<typeof managerContact>) => {
      title: string;
      content?: ReactNode;
    }[];
    done: string;
  }
> = {
  smartstore: {
    admin: "https://sell.smartstore.naver.com/",
    adminLabel: "판매자센터 열기",
    path: ["판매자정보", "판매자 관리", "매니저 관리"],
    steps: (contact) => [
      { title: "판매자센터에 통합매니저 계정으로 로그인" },
      {
        title: "매니저 관리 열기",
        content: (
          <MenuPath items={["판매자정보", "판매자 관리", "매니저 관리"]} />
        ),
      },
      {
        title: "seelo 담당자를 대행사 매니저로 초대",
        content: contact ? (
          <div className={styles.copyRow}>
            <CopyButton label="이름" value={contact.name} />
            <CopyButton label="휴대전화" value={contact.phone} />
            <Badge tone="blue">권한 · 대행사</Badge>
          </div>
        ) : (
          <Badge tone="blue">권한 · 대행사</Badge>
        ),
      },
    ],
    done: "초대를 보냈어요",
  },
  cafe24: {
    admin: "https://eclogin.cafe24.com/Shop/",
    adminLabel: "카페24 관리자 열기",
    path: ["쇼핑몰 설정", "운영자 설정", "운영자 관리", "운영자 계정 관리"],
    steps: () => [
      { title: "쇼핑몰 관리자에 대표운영자로 로그인" },
      {
        title: "운영자 계정 관리에서 등록",
        content: (
          <MenuPath
            items={[
              "쇼핑몰 설정",
              "운영자 설정",
              "운영자 관리",
              "운영자 계정 관리",
            ]}
          />
        ),
      },
      {
        title: "seelo 전용 부운영자 만들기",
        content: (
          <div className={styles.copyRow}>
            <Badge tone="blue">상품 메뉴 접근</Badge>
            <Badge tone="blue">상품 수정</Badge>
          </div>
        ),
      },
      {
        title: "아이디·비밀번호는 seelo 운영자에게 전화·문자로 전달",
      },
    ],
    done: "부운영자를 만들었어요",
  },
};
function Delegation({ store }: { store: Store }) {
  const action = useShopAction(store.id);
  const runtime = useRuntime();
  const [reopen, setReopen] = useState(false);
  const { owner, admin } = useStoreViewer(store);
  const guide = guides[store.platform];
  const invited = store.managerStatus === "invited";
  const invoke = (value: Parameters<typeof action.run>[0]) =>
    void action.run(value).catch(() => undefined);
  // 운영자는 판매자용 안내 대신 지금 상태와 권한 확인 칸만 본다.
  if (!owner)
    return (
      <>
        <Notice
          tone={invited ? "info" : "warning"}
          title={
            invited
              ? "판매자가 권한을 줬다고 알려 왔어요"
              : store.managerStatus === "revoked"
                ? "권한이 해제됐어요"
                : "판매자가 아직 권한을 주지 않았어요"
          }
        >
          {invited
            ? `${platformNames[store.platform]} 관리 화면에서 위임을 확인하고 아래에 기록해 주세요.`
            : "판매자가 권한을 주면 이 화면에서 확인할 수 있어요."}
        </Notice>
        {admin && <OperatorVerify store={store} />}
      </>
    );
  return (
    <>
      {store.managerStatus === "revoked" && (
        <Notice tone="error" title="연결이 끊겼어요">
          아래 순서로 다시 권한을 주세요.
        </Notice>
      )}
      {invited && !reopen ? (
        <Panel>
          <div className={styles.wait}>
            <span className={styles.waitArt} aria-hidden="true">
              🔍
            </span>
            <div className={styles.waitText}>
              <strong>seelo가 권한을 확인하고 있어요</strong>
              <span>확인이 끝나면 이 화면에서 상품을 불러올 수 있어요.</span>
            </div>
          </div>
          <div style={{ marginTop: "1.5rem" }}>
            <Timeline
              label="연결 진행"
              items={[
                { key: "invite", title: "권한 위임", state: "done" },
                {
                  key: "check",
                  title: "seelo 확인",
                  state: "current",
                  busy: true,
                },
                { key: "ready", title: "상품 정비", state: "todo" },
              ]}
            />
          </div>
          <div className={styles.guideActions}>
            <Button variant="secondary" onClick={() => setReopen(true)}>
              안내 다시 보기
            </Button>
          </div>
        </Panel>
      ) : (
        <Panel title={`${platformNames[store.platform]}에서 권한 주기`}>
          <Timeline
            guide
            label="권한 위임 순서"
            items={guide
              .steps(managerContact(runtime.mode === "demo"))
              .map((step) => ({
                key: step.title,
                title: step.title,
                content: step.content,
                state: "todo" as StepState,
              }))}
          />
          <div className={styles.guideActions}>
            <ExternalButton
              href={guide.admin}
              variant="secondary"
              icon={<ExternalLink aria-hidden="true" />}
            >
              {guide.adminLabel}
            </ExternalButton>
            <Button
              loading={action.isPending}
              onClick={() => {
                setReopen(false);
                invoke({ action: "manager", status: "invited" });
              }}
            >
              {guide.done}
            </Button>
          </div>
        </Panel>
      )}
      <ErrorMessage error={action.error} />
      {/* 판매자이면서 관리자인 계정만 여기서 바로 확인한다. */}
      {admin && <OperatorVerify store={store} />}
    </>
  );
}
// 운영자만 본다. 위임 목록·관리 화면에 보이는 값을 그대로 기록해야 실행기가 대조한다.
function OperatorVerify({ store }: { store: Store }) {
  const action = useShopAction(store.id);
  return (
    <Panel title="운영자 · 권한 확인" small flat>
      <form
        style={{ display: "grid", gap: "1rem" }}
        onSubmit={(event) => {
          event.preventDefault();
          const values = formValues(event.currentTarget);
          void action
            .run({
              action: "manager",
              status: "verified",
              identity: {
                storeName: String(values.storeName ?? ""),
                storeId: String(values.storeId ?? ""),
              },
            })
            .catch(() => undefined);
        }}
      >
        <TextField
          label="관리 화면에 보이는 스토어 이름"
          name="storeName"
          maxLength={100}
          defaultValue={store.delegatedIdentity?.storeName ?? ""}
          hint="실행기가 이 값과 화면 값을 정확히 대조합니다."
        />
        <TextField
          label="위임 목록의 고유 ID (확인한 경우)"
          name="storeId"
          maxLength={100}
          pattern="[A-Za-z0-9_.:-]+"
          defaultValue={store.delegatedIdentity?.storeId ?? ""}
        />
        <ErrorMessage error={action.error} />
        <Button type="submit" loading={action.isPending}>
          권한 확인 완료
        </Button>
      </form>
    </Panel>
  );
}
function ApiConnect({ store }: { store: Store }) {
  const action = useShopAction(store.id);
  const runtime = useRuntime();
  const { owner } = useStoreViewer(store);
  // 버튼 하나로 카페24 인증 화면까지 간다. 인증 주소를 받은 뒤 다시 누르게 하지 않는다.
  const authorize = () =>
    void action
      .run({ action: "authorize" })
      .then((url) => {
        if (url) window.location.assign(url);
      })
      .catch(() => undefined);
  return (
    <Panel title="API 연결">
      {store.platform === "cafe24" ? (
        owner ? (
          <Stack>
            <p style={{ color: "var(--s-grey600)" }}>
              카페24 인증 화면에서 상품 권한을 허용하면 연결돼요.
            </p>
            <Button
              loading={action.isPending}
              icon={<ExternalLink aria-hidden="true" />}
              onClick={authorize}
            >
              {runtime.mode === "demo"
                ? "시연 API 인증 완료"
                : "카페24에서 허용하기"}
            </Button>
          </Stack>
        ) : (
          <Notice title="판매자의 API 허용을 기다려요">
            판매자가 카페24 인증 화면에서 상품 권한을 허용하면 연결돼요.
          </Notice>
        )
      ) : (
        <Notice title="seelo가 연결해요">
          스마트스토어 API는 seelo가 공식 절차로 따로 인증해요. 연결이 끝나면 이
          화면에서 상품을 불러올 수 있어요.
        </Notice>
      )}
      <ErrorMessage error={action.error} />
    </Panel>
  );
}
// 숫자만 입력하면 상품번호, 주소면 서버가 같은 몰의 카페24 상품번호로 바꾼다.
function productTarget(value: string): ProductTarget {
  const text = value.trim();
  return /^[1-9][0-9]{0,18}$/.test(text)
    ? { externalId: productNoSchema.parse(text) }
    : { productUrl: text };
}
// 스토어 화면 본문. 상품 목록 하나만 둔다. 상품을 더하는 방법(번호·쇼핑몰 목록·직접 입력)은
// 모두 `상품 추가` 안에 모은다.
function ProductsSection({ store }: { store: Store }) {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const runtime = useRuntime();
  const browser = store.editingMode === "browser";
  const candidate = Number(params.get("page"));
  const page = Number.isSafeInteger(candidate) && candidate > 0 ? candidate : 1;
  const query = (params.get("query") ?? "").slice(0, 200);
  const catalog = browser && params.get("view") === "catalog";
  const products = useProducts(store.id, { page, query });
  const importer = useImportProduct(store.id);
  const rawJob = Number(params.get("job"));
  const jobId = Number.isSafeInteger(rawJob) && rawJob > 0 ? rawJob : undefined;
  const job = useJob(jobId);
  const [error, setError] = useState<unknown>(null);
  const collected =
    job.data?.status === "succeeded" && job.data.shopId === store.id
      ? Number(job.data.result.productId)
      : undefined;
  useEffect(() => {
    if (!collected || !Number.isSafeInteger(collected)) return;
    void runtime.queryClient.invalidateQueries({
      queryKey: ["commerce", "products", store.id],
    });
    navigate(`/stores/${store.id}/products/${collected}`);
  }, [collected, store.id, navigate, runtime.queryClient]);
  const afterImport = (
    result: Awaited<ReturnType<typeof importer.mutateAsync>>,
  ) =>
    result.kind === "job"
      ? // 브라우저 수집은 worker가 실행한다. 작업 번호를 주소에 남겨 새로고침해도 이어서 조회한다.
        setParams({ ...Object.fromEntries(params), job: String(result.job.id) })
      : navigate(`/stores/${store.id}/products/${result.product.id}`);
  const importProduct = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (importer.isPending) return;
    setError(null);
    try {
      afterImport(
        await importer.mutateAsync(
          productTarget(String(formValues(event.currentTarget).externalId)),
        ),
      );
    } catch (error) {
      setError(error);
    }
  };
  const collecting = job.data && job.data.shopId === store.id ? job.data : null;
  // 상품이 없거나 불러오는 중이면 추가 칸을 닫지 않는다.
  const empty = products.data?.total === 0 && !query;
  const requested = params.get("add") === "1" || catalog;
  const adding = requested || jobId !== undefined || empty;
  const closeAdd = () => {
    const next = Object.fromEntries(params);
    delete next.add;
    delete next.view;
    setParams(next);
  };
  const toggleCatalog = () => {
    const next = Object.fromEntries(params);
    if (catalog) delete next.view;
    else next.view = "catalog";
    setParams({ ...next, add: "1" });
  };
  return (
    <>
      {adding && (
        <Panel
          title="상품 추가"
          action={
            requested && !empty && !jobId ? (
              <TextButton onClick={closeAdd}>닫기</TextButton>
            ) : undefined
          }
        >
          <form
            className={styles.importForm}
            onSubmit={(event) => void importProduct(event)}
          >
            <InlineForm>
              <TextField
                label={
                  store.platform === "cafe24"
                    ? "상품번호 또는 카페24 상품 주소"
                    : "원상품번호"
                }
                name="externalId"
                required
                maxLength={2048}
                hint={
                  store.platform === "smartstore"
                    ? "판매자센터 상품 목록의 원상품번호예요. 공개 주소의 번호와 달라요."
                    : undefined
                }
              />
              <div className={styles.importAction}>
                <Button
                  type="submit"
                  size="lg"
                  loading={
                    importer.isPending ||
                    Boolean(collecting && activeJob(collecting))
                  }
                  icon={<PackagePlus aria-hidden="true" />}
                >
                  불러오기
                </Button>
              </div>
            </InlineForm>
          </form>
          <div style={{ display: "grid", gap: "0.75rem", marginTop: "1rem" }}>
            {collecting && (
              <Notice
                tone={
                  collecting.status === "failed"
                    ? "error"
                    : collecting.stale
                      ? "warning"
                      : collecting.status === "succeeded"
                        ? "success"
                        : "progress"
                }
              >
                {collecting.status === "failed"
                  ? `불러오지 못했어요 · ${jobMessage(collecting.errorCode)}`
                  : collecting.stale
                    ? "불러오기가 오래 멈췄어요. 다시 불러올 수 있어요."
                    : collecting.status === "succeeded"
                      ? "불러왔어요"
                      : "상품을 불러오는 중이에요"}
              </Notice>
            )}
            <ErrorMessage error={error ?? job.error} />
            {browser && (
              <TextButton className={styles.pick} onClick={toggleCatalog}>
                {catalog
                  ? "쇼핑몰 상품 목록 닫기"
                  : "쇼핑몰 상품 목록에서 고를게요"}
              </TextButton>
            )}
            {catalog && (
              <CatalogPanel
                store={store}
                busy={importer.isPending}
                onImport={(productNo) =>
                  void importer
                    .mutateAsync({ externalId: productNo })
                    .then(afterImport)
                    .catch(setError)
                }
              />
            )}
            <ManualSnapshot store={store} />
          </div>
        </Panel>
      )}
      {
        <section aria-label="불러온 상품" className={styles.products}>
          {/* 목록 머리: 왼쪽 제목과 개수, 오른쪽 추가. 토스 ListHeader와 같은 배치다. */}
          <div className={styles.listHead}>
            <h2 className={styles.listTitle}>
              상품
              {products.data ? <span>{products.data.total}</span> : null}
            </h2>
            {!adding && (
              <TextButton
                className={styles.addButton}
                onClick={() =>
                  setParams({ ...Object.fromEntries(params), add: "1" })
                }
              >
                <Plus aria-hidden="true" />
                상품 추가
              </TextButton>
            )}
          </div>
          {(products.data?.total ?? 0) > 5 || query ? (
            <div className={styles.toolbar}>
              <form
                role="search"
                onSubmit={(event) => {
                  event.preventDefault();
                  setParams({
                    query: String(formValues(event.currentTarget).query).trim(),
                    page: "1",
                  });
                }}
              >
                <InlineForm>
                  <TextField
                    key={query}
                    label="상품 검색"
                    hideLabel
                    name="query"
                    defaultValue={query}
                    maxLength={200}
                    placeholder="상품명·상품번호"
                  />
                  <Button
                    type="submit"
                    variant="secondary"
                    size="lg"
                    aria-label="검색"
                    icon={<Search aria-hidden="true" />}
                  >
                    검색
                  </Button>
                </InlineForm>
              </form>
            </div>
          ) : null}
          <QueryState
            pending={products.isPending}
            error={products.error}
            retry={products.refetch}
            lines={2}
          />
          {products.data?.items.length === 0 && (
            <Panel>
              <EmptyState
                emoji="📦"
                title={
                  query ? "찾는 상품이 없어요" : "아직 불러온 상품이 없어요"
                }
              >
                {query
                  ? "다른 이름이나 번호로 찾아보세요."
                  : "위에서 상품번호를 넣어 불러오세요."}
              </EmptyState>
            </Panel>
          )}
          {!!products.data?.items.length && (
            <List label="불러온 상품 목록">
              {products.data.items.map((product) => {
                const state = summaryState(product);
                return (
                  <ListRow
                    key={product.id}
                    to={`/stores/${store.id}/products/${product.id}`}
                    title={product.name}
                    sub={`상품번호 ${product.externalId}`}
                    meta={
                      <Badge tone={state.tone} dot>
                        {state.label}
                      </Badge>
                    }
                  />
                );
              })}
            </List>
          )}
          {products.data && products.data.total > products.data.pageSize && (
            <div className={styles.pager}>
              <Button
                variant="secondary"
                size="sm"
                disabled={page === 1}
                onClick={() => setParams({ query, page: String(page - 1) })}
              >
                이전
              </Button>
              <span>{page}페이지</span>
              <Button
                variant="secondary"
                size="sm"
                disabled={page * products.data.pageSize >= products.data.total}
                onClick={() => setParams({ query, page: String(page + 1) })}
              >
                다음
              </Button>
            </div>
          )}
        </section>
      }
    </>
  );
}
// 판매자가 직접 붙여 넣은 원본. 자동 반영의 근거로 쓰지 않으므로 접어 둔다.
function ManualSnapshot({ store }: { store: Store }) {
  const importer = useImportProduct(store.id);
  const navigate = useNavigate();
  const [error, setError] = useState<unknown>(null);
  return (
    <details className={styles.more}>
      <summary>원본을 직접 입력할게요</summary>
      <form
        className={styles.moreBody}
        onSubmit={(event) => {
          event.preventDefault();
          if (importer.isPending) return;
          const raw = formValues(event.currentTarget);
          setError(null);
          try {
            const input = manualSnapshotSchema.parse({
              externalId: raw.externalId,
              name: raw.name,
              identity: raw.identity,
              fields: { description: String(raw.description) },
            });
            void importer
              .mutateAsync(input)
              .then((result) =>
                result.kind === "product"
                  ? navigate(
                      `/stores/${store.id}/products/${result.product.id}`,
                    )
                  : undefined,
              )
              .catch(setError);
          } catch (error) {
            setError(error);
          }
        }}
      >
        <Notice>
          직접 입력한 원본은 참고용이에요. 쇼핑몰에 자동 반영하지 않아요.
        </Notice>
        <TextField label="상품번호" name="externalId" required />
        <TextField label="상품명" name="name" required maxLength={250} />
        <TextField
          label="모델·옵션 식별값"
          name="identity"
          required
          maxLength={250}
        />
        <TextArea
          label="현재 상세설명"
          name="description"
          required
          maxLength={200000}
        />
        <ErrorMessage error={error} />
        <Button type="submit" variant="secondary" loading={importer.isPending}>
          제공 원본 등록
        </Button>
      </form>
    </details>
  );
}
// 위임받은 관리 화면의 상품 목록. 불러온 상품과 구분해 보여 준다.
function CatalogPanel({
  store,
  busy,
  onImport,
}: {
  store: Store;
  busy: boolean;
  onImport: (productNo: string) => void;
}) {
  const runtime = useRuntime();
  const catalog = useCatalog(store.id, true);
  const [jobId, setJobId] = useState<number>();
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const job = useJob(jobId);
  const finished = job.data?.status === "succeeded" ? job.data.id : undefined;
  useEffect(() => {
    if (finished)
      void runtime.queryClient.invalidateQueries({
        queryKey: ["commerce", "catalog", store.id],
      });
  }, [finished, runtime.queryClient, store.id]);
  const request = async () => {
    setError(null);
    setPending(true);
    try {
      const result = await runtime.gateway.requestCatalog(store.id);
      if (result.kind === "job") setJobId(result.job.id);
      else
        runtime.queryClient.setQueryData(
          ["commerce", "catalog", store.id],
          result.catalog,
        );
    } catch (error) {
      setError(error);
    } finally {
      setPending(false);
    }
  };
  const loading = pending || Boolean(job.data && activeJob(job.data));
  return (
    <section
      aria-label="쇼핑몰 상품 목록"
      style={{ display: "grid", gap: "0.75rem" }}
    >
      <div className={styles.toolbar}>
        <span style={{ color: "var(--s-grey600)", fontSize: "var(--s-t6)" }}>
          {catalog.data?.collectedAt
            ? `${when(catalog.data.collectedAt)} 기준 · ${catalog.data.items.length}개${catalog.data.truncated ? "(일부)" : ""}`
            : "쇼핑몰에서 상품번호와 이름만 읽어 와요."}
        </span>
        <Button
          variant="secondary"
          loading={loading}
          onClick={() => void request()}
        >
          쇼핑몰 상품 목록 가져오기
        </Button>
      </div>
      {job.data?.status === "failed" && (
        <Notice tone="error">
          목록을 불러오지 못했어요 · {jobMessage(job.data.errorCode)}
        </Notice>
      )}
      <ErrorMessage error={error ?? catalog.error} />
      {!!catalog.data?.items.length && (
        <List label="플랫폼 상품">
          {catalog.data.items.map((item) => (
            <ListRow
              key={item.productNo}
              title={item.name}
              sub={`상품번호 ${item.productNo}`}
              meta={
                item.importedProductId ? (
                  <ButtonLink
                    size="sm"
                    variant="secondary"
                    to={`/stores/${store.id}/products/${item.importedProductId}`}
                  >
                    가져온 상품 열기
                  </ButtonLink>
                ) : (
                  <Button
                    size="sm"
                    variant="tertiary"
                    disabled={busy}
                    onClick={() => onImport(item.productNo)}
                  >
                    가져오기
                  </Button>
                )
              }
            />
          ))}
        </List>
      )}
    </section>
  );
}
export function StoreSettingsPage() {
  const id = useStoreId();
  const store = useStore(id ?? 0);
  if (id === null) return <InvalidPath />;
  return (
    <Page width="medium">
      <QueryState
        pending={store.isPending}
        error={store.error}
        retry={store.refetch}
        lines={2}
      />
      {store.data && <StoreSettings store={store.data} />}
    </Page>
  );
}
function StoreSettings({ store }: { store: Store }) {
  const action = useShopAction(store.id);
  const session = useSession();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState(false);
  const [checked, setChecked] = useState(false);
  const owner = session.data?.id === store.ownerId;
  const admin = session.data?.role === "admin";
  const connected =
    store.managerStatus !== "revoked" ||
    !["not_connected", "revoked"].includes(store.apiStatus);
  return (
    <>
      <PageHeader
        back={{ to: `/stores/${store.id}`, label: store.name }}
        title="연결 관리"
        eyebrow={
          <>
            <PlatformMark platform={store.platform} size="1.75rem" />
            {storeLine(store)}
          </>
        }
      />
      <Stack>
        <Panel title="상태" small>
          {/* 판매자에게는 연결 여부와 방식만, 운영자에게는 실행에 필요한 상태를 모두 보여 준다. */}
          <div className={styles.statusGrid} aria-label="연결 상태">
            <div className={styles.status}>
              <span>연결 상태</span>
              <ConnectionBadge store={store} />
            </div>
            <div className={styles.status}>
              <span>연결 방식</span>
              <strong>
                {store.editingMode === "browser" ? "관리자 권한 위임" : "API"}
              </strong>
            </div>
            {admin && store.editingMode !== "browser" && (
              <div className={styles.status}>
                <span>API 인증</span>
                <strong>{apiLabels[store.apiStatus]}</strong>
              </div>
            )}
            {admin && (
              <div className={styles.status}>
                <span>자동 수정</span>
                <strong>
                  {store.automaticWritesEnabled ? "켜짐" : "꺼짐"}
                </strong>
              </div>
            )}
          </div>
          {admin && store.delegatedIdentity?.storeName && (
            <p
              style={{
                marginTop: "1rem",
                color: "var(--s-grey600)",
                fontSize: "var(--s-t6)",
              }}
            >
              확인한 스토어: {store.delegatedIdentity.storeName}
              {store.delegatedIdentity.storeId
                ? ` · 고유 ID ${store.delegatedIdentity.storeId}`
                : ""}
            </p>
          )}
        </Panel>
        {admin && store.managerStatus === "verified" && (
          <Panel title="운영자 · 권한 해제 기록" small flat>
            <Button
              variant="secondary"
              loading={action.isPending}
              onClick={() =>
                void action
                  .run({ action: "manager", status: "revoked" })
                  .catch(() => undefined)
              }
            >
              권한 회수 확인 기록
            </Button>
          </Panel>
        )}
        {owner && connected && (
          <Panel title="연결 해제" small>
            <p
              style={{
                color: "var(--s-grey600)",
                fontSize: "var(--s-t6)",
                marginBottom: "1rem",
              }}
            >
              seelo가 이 스토어의 상품을 더 읽거나 고치지 않아요.
            </p>
            <Button variant="dangerSoft" onClick={() => setConfirm(true)}>
              연결 해제
            </Button>
          </Panel>
        )}
        <ErrorMessage error={action.error} />
      </Stack>
      <ConfirmDialog
        open={confirm}
        title="연결을 해제할까요?"
        confirmLabel="연결 해제"
        danger
        busy={action.isPending}
        confirmDisabled={!checked}
        onClose={() => {
          setConfirm(false);
          setChecked(false);
        }}
        onConfirm={() =>
          void action
            .run({ action: "disconnect", confirmed: true })
            .then(() => {
              setConfirm(false);
              navigate(`/stores/${store.id}`);
            })
            .catch(() => undefined)
        }
      >
        <p>
          대기 중인 작업을 취소하고 보관한 연결 정보를 지웁니다. 쇼핑몰의
          매니저·부운영자·앱 권한은 쇼핑몰 관리 화면에서 직접 지워 주세요.
        </p>
        <Checkbox
          label="이 스토어의 seelo 연결을 해제합니다."
          checked={checked}
          onChange={(event) => setChecked(event.target.checked)}
        />
      </ConfirmDialog>
    </>
  );
}
