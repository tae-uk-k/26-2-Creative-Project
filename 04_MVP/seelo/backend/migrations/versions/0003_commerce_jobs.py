"""쇼핑몰 작업 상태·위임 가게 식별값. 기존 데이터는 변경하지 않는다."""

from pathlib import Path

from alembic import op

revision = "0003_commerce_jobs"
down_revision = "0002_commerce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path(__file__).resolve().parents[1] / "sql" / "0003_commerce_jobs.sql"
    op.get_bind().exec_driver_sql(sql.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("작업 이력을 보존한다. 되돌림은 검토한 별도 마이그레이션으로 수행한다.")
