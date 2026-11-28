"""Procrastinate 스키마가 없을 때만 적용한다(06 1장).

실행: python scripts/init_queue_schema.py  (DATABASE_URL·QUEUE_DATABASE_DSN 필요)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from seelo.config import get_settings  # noqa: E402
from seelo.worker.app import app  # noqa: E402


async def queue_schema_exists(dsn: str) -> bool:
    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        cur = await conn.execute("SELECT to_regclass('procrastinate_jobs') IS NOT NULL")
        row = await cur.fetchone()
        return bool(row and row[0])


async def main() -> int:
    dsn = get_settings().queue_database_dsn
    if await queue_schema_exists(dsn):
        print("procrastinate schema: already applied")
        return 0
    async with app.open_async():
        await app.schema_manager.apply_schema_async()
    print("procrastinate schema: applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
