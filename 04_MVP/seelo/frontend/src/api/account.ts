import { z } from "zod";
import type { ApiClient } from "./client";

export const accountSchema = z.object({
  email: z.string(),
  provider: z.enum(["email", "google", "kakao"]),
  createdAt: z.string(),
  canChangePassword: z.boolean(),
});
export type Account = z.infer<typeof accountSchema>;
export const deleteConfirmText = "탈퇴합니다";
const password = z
  .string()
  .min(8, "비밀번호는 8자 이상이어야 합니다.")
  .max(128)
  .regex(/[a-zA-Z]/, "영문을 포함해 주세요.")
  .regex(/[0-9]/, "숫자를 포함해 주세요.");
export const passwordChangeSchema = z
  .object({
    currentPassword: z.string().min(1, "지금 비밀번호를 입력해 주세요."),
    newPassword: password,
    newPasswordConfirm: z.string(),
  })
  .refine((value) => value.newPassword === value.newPasswordConfirm, {
    message: "새 비밀번호가 서로 다릅니다.",
    path: ["newPasswordConfirm"],
  });
// 계정 조회·비밀번호 변경·탈퇴. 탈퇴는 확인 문구가 정확히 같아야 서버가 받는다.
export function createAccountApi(client: ApiClient) {
  return {
    get: (signal?: AbortSignal) =>
      client.request("/api/account", accountSchema, { signal }),
    changePassword: (input: unknown) =>
      client.request("/api/account/password", z.undefined(), {
        method: "POST",
        body: passwordChangeSchema.parse(input),
      }),
    remove: (confirmText: string) =>
      client.request("/api/account", z.undefined(), {
        method: "DELETE",
        body: { confirmText },
      }),
  };
}
export type AccountApi = ReturnType<typeof createAccountApi>;
