"""실행 중인 서버·DB·비밀 값 없이 API 계약을 내보낸다(17 4장)."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI  # noqa: E402

from seelo.api.router import api_router  # noqa: E402

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def schema() -> dict:
    """실제 라우터를 쓰되 앱 시작·설정 읽기·외부 연결은 하지 않는다."""
    app = FastAPI(title="seelo API", docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(api_router, prefix="/api")
    return app.openapi()


def export(output: Path, *, check: bool = False) -> bool:
    content = json.dumps(schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    same = output.is_file() and output.read_text(encoding="utf-8") == content
    if check:
        return same
    if not same:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8", newline="\n")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="API 계약 내보내기(17 4장)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="파일을 바꾸지 않고 최신 계약인지 확인")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    ok = export(output, check=args.check)
    print(f"openapi={'current' if ok else 'stale'} path={output}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
