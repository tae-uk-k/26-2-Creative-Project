import { messageOf } from "../api/client";
import { Button, ButtonLink } from "../ui/Button";
import { EmptyState, Notice, Skeleton } from "../ui/Display";
import { Page } from "../ui/Layout";

export function ErrorMessage({ error }: { error: unknown }) {
  return error ? <Notice tone="error">{messageOf(error)}</Notice> : null;
}
export function QueryState({
  pending,
  error,
  retry,
  lines = 3,
}: {
  pending: boolean;
  error: unknown;
  retry: () => unknown;
  lines?: number;
}) {
  if (pending)
    return (
      <div
        role="status"
        aria-label="불러오는 중"
        style={{ display: "grid", gap: "0.75rem" }}
      >
        <Skeleton height="1.5rem" width="40%" />
        {Array.from({ length: lines }, (_, index) => (
          <Skeleton key={index} height="4.5rem" />
        ))}
      </div>
    );
  if (error)
    return (
      <Notice
        tone="error"
        action={
          <Button size="sm" variant="secondary" onClick={() => retry()}>
            다시 조회
          </Button>
        }
      >
        {messageOf(error)}
      </Notice>
    );
  return null;
}
export function formValues(
  form: HTMLFormElement,
): Record<string, FormDataEntryValue> {
  return Object.fromEntries(new FormData(form));
}
export function NotFoundPage() {
  return (
    <Page width="medium">
      <EmptyState
        emoji="🧭"
        title="페이지를 찾을 수 없습니다."
        action={<ButtonLink to="/home">홈으로</ButtonLink>}
      />
    </Page>
  );
}
export function InvalidPath() {
  return (
    <Page width="medium">
      <EmptyState
        emoji="🔗"
        title="주소가 올바르지 않습니다."
        action={<ButtonLink to="/stores">스토어 목록</ButtonLink>}
      />
    </Page>
  );
}
