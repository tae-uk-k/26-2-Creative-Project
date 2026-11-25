"""쇼핑몰 AI 노출 진단·전후 비교. 지도 측정 테이블은 변경하지 않는다."""

from pathlib import Path

from alembic import op

revision = "0004_commerce_measure"
down_revision = "0003_commerce_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path(__file__).resolve().parents[1] / "sql" / "0004_commerce_measure.sql"
    op.get_bind().exec_driver_sql(sql.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("측정 원문을 보존한다. 되돌림은 검토한 별도 마이그레이션으로 수행한다.")
