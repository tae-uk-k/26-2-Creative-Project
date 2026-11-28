"""스마트스토어·카페24 데이터. 기존 지도 테이블·데이터는 변경하지 않는다."""

from pathlib import Path

from alembic import op

revision = "0002_commerce"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path(__file__).resolve().parents[1] / "sql" / "0002_commerce.sql"
    op.get_bind().exec_driver_sql(sql.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("상품 이력을 보존한다. 되돌림은 검토한 별도 마이그레이션으로 수행한다.")
