"""외부 호출·DB 없이 실제 백엔드 Pydantic 입력 계약을 검사한다."""

import json
import sys
from pathlib import Path

frontend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(frontend.parent / "backend"))
from seelo.schemas import commerce as schemas  # noqa: E402

payloads = json.loads((frontend / "tests" / "fixtures" / "requests.json").read_text(encoding="utf-8"))
count = 0
for name, value in payloads.items():
    for payload in value if isinstance(value, list) else [value]:
        model = getattr(schemas, name).model_validate(payload)
        assert model.model_dump(by_alias=True, exclude_unset=True) == payload, name
        count += 1
print(f"백엔드 요청 계약 {count}개 검증 통과")
