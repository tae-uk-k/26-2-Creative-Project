import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { deleteConfirmText } from "../api/account";
import { useLogout, useRuntime } from "../app/runtime";
import { Button, TextButton } from "../ui/Button";
import { Facts, Notice, Panel } from "../ui/Display";
import { TextField } from "../ui/Field";
import { Page, PageHeader, Stack } from "../ui/Layout";
import { ConfirmDialog } from "../ui/Overlay";
import { day } from "../ui/labels";
import { ErrorMessage, QueryState, formValues } from "./common";
import styles from "./account.module.css";

const providers = { email: "이메일", google: "Google", kakao: "카카오" };
export function AccountPage() {
  const runtime = useRuntime();
  const navigate = useNavigate();
  const logout = useLogout();
  const account = useQuery({
    queryKey: ["account"],
    queryFn: ({ signal }) => runtime.account.get(signal),
  });
  const change = useMutation({ mutationFn: runtime.account.changePassword });
  const [leaving, setLeaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [typed, setTyped] = useState("");
  const remove = useMutation({
    mutationFn: () => runtime.account.remove(typed),
    onSuccess: async () => {
      await runtime.queryClient.cancelQueries();
      runtime.queryClient.clear();
      runtime.queryClient.setQueryData(["session"], null);
      navigate("/", { replace: true });
    },
  });
  return (
    <Page width="medium">
      <PageHeader title="계정" />
      <QueryState
        pending={account.isPending}
        error={account.error}
        retry={account.refetch}
        lines={2}
      />
      {account.data && (
        <Stack>
          <Panel title="로그인 정보" small>
            <Facts
              items={[
                ["이메일", account.data.email],
                ["로그인 방법", providers[account.data.provider]],
                ["가입일", day(account.data.createdAt)],
              ]}
            />
          </Panel>
          {account.data.canChangePassword && (
            <Panel
              title="비밀번호 변경"
              small
              action={
                !editing && !change.isSuccess ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setEditing(true)}
                  >
                    변경하기
                  </Button>
                ) : undefined
              }
            >
              {/* 자주 쓰지 않는 칸이라 접어 둔다. 누르면 입력칸을 연다. */}
              {!editing && !change.isSuccess ? (
                <p className={styles.hint}>
                  로그인할 때 쓰는 비밀번호를 바꿔요.
                </p>
              ) : change.isSuccess ? (
                <Notice tone="success" title="비밀번호를 바꿨어요">
                  다른 기기의 로그인은 끝났습니다.
                </Notice>
              ) : (
                <form
                  style={{ display: "grid", gap: "1rem" }}
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (!change.isPending)
                      change.mutate(formValues(event.currentTarget));
                  }}
                >
                  <TextField
                    label="지금 비밀번호"
                    name="currentPassword"
                    type="password"
                    autoComplete="current-password"
                    required
                  />
                  <TextField
                    label="새 비밀번호"
                    name="newPassword"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={8}
                    hint="영문과 숫자를 섞어 8자 이상"
                  />
                  <TextField
                    label="새 비밀번호 확인"
                    name="newPasswordConfirm"
                    type="password"
                    autoComplete="new-password"
                    required
                  />
                  <ErrorMessage error={change.error} />
                  <Button type="submit" loading={change.isPending}>
                    비밀번호 저장
                  </Button>
                </form>
              )}
            </Panel>
          )}
          {/* 로그아웃은 보조 버튼, 탈퇴는 맨 아래 흐린 글자 버튼. 자주 누르지 않는 일을 앞에 두지 않는다. */}
          {runtime.mode === "api" && (
            <Button
              variant="secondary"
              block
              icon={<LogOut aria-hidden="true" />}
              loading={logout.isPending}
              onClick={() =>
                logout.mutate(undefined, {
                  onSuccess: () => navigate("/", { replace: true }),
                })
              }
            >
              로그아웃
            </Button>
          )}
          <TextButton className={styles.leave} onClick={() => setLeaving(true)}>
            탈퇴
          </TextButton>
        </Stack>
      )}
      <ConfirmDialog
        open={leaving}
        title="탈퇴할까요?"
        confirmLabel="탈퇴"
        danger
        busy={remove.isPending}
        confirmDisabled={typed !== deleteConfirmText}
        onConfirm={() => remove.mutate()}
        onClose={() => {
          setLeaving(false);
          setTyped("");
          remove.reset();
        }}
      >
        <p>
          연결한 스토어, 불러온 상품, 정비안과 기록이 모두 지워지고 되돌릴 수
          없습니다. 쇼핑몰에 이미 반영한 내용은 그대로 남습니다. 쇼핑몰 관리자
          화면에서 seelo에 준 권한은 직접 해제해 주세요.
        </p>
        <TextField
          label={`확인을 위해 "${deleteConfirmText}"를 입력해 주세요`}
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          autoComplete="off"
        />
        <ErrorMessage error={remove.error} />
      </ConfirmDialog>
    </Page>
  );
}
