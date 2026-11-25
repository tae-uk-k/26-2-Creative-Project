import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const interpreter = fileURLToPath(
  new URL(
    process.platform === "win32"
      ? "../../backend/.venv/Scripts/python.exe"
      : "../../backend/.venv/bin/python",
    import.meta.url,
  ),
);
if (!existsSync(interpreter)) {
  process.stderr.write(
    "백엔드 가상환경이 필요합니다. backend 폴더에서 uv sync를 먼저 실행해 주세요.\n",
  );
  process.exit(1);
}
const result = spawnSync(
  interpreter,
  [fileURLToPath(new URL("./check_backend_contract.py", import.meta.url))],
  { stdio: "inherit" },
);
if (result.error) {
  process.stderr.write(`${result.error.message}\n`);
}
process.exit(result.status ?? 1);
