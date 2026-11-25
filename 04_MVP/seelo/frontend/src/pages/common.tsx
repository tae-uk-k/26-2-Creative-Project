import { messageOf } from "../api/client";
export function ErrorMessage({ error }: { error: unknown }) {
  return error ? <p role="alert">{messageOf(error)}</p> : null;
}
export function QueryState({
  pending,
  error,
  retry,
}: {
  pending: boolean;
  error: unknown;
  retry: () => unknown;
}) {
  if (pending) return <p role="status">조회 중입니다.</p>;
  if (error)
    return (
      <>
        <ErrorMessage error={error} />
        <button onClick={() => retry()}>다시 조회</button>
      </>
    );
  return null;
}
export function formValues(
  form: HTMLFormElement,
): Record<string, FormDataEntryValue> {
  return Object.fromEntries(new FormData(form));
}
