"""initial schema (02 4장 DDL 그대로)

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-24
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL_FILE = Path(__file__).resolve().parents[1] / "sql" / "0001_initial.sql"


def upgrade() -> None:
    # text()를 거치면 ':숫자' 같은 문자열이 바인드 변수로 해석되므로 드라이버에 그대로 보낸다.
    op.get_bind().exec_driver_sql(SQL_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("초기 스키마는 되돌리지 않는다. DB를 새로 만든다.")
