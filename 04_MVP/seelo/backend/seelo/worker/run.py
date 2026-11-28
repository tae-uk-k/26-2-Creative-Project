"""워커 실행 진입점(06 1장): python -m seelo.worker.run --queues collect,measure --concurrency 4"""

import argparse
import asyncio

from seelo.config import get_settings
from seelo.logging import setup_logging
from seelo.worker.app import app


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="seelo Procrastinate worker")
    p.add_argument("--queues", required=True, help='쉼표로 구분한 큐 이름, 예 "collect,measure"')
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--name", default=None)
    return p.parse_args(argv)


async def run(queues: list[str], concurrency: int, name: str | None) -> None:
    async with app.open_async():
        await app.run_worker_async(
            queues=queues,
            concurrency=concurrency,
            name=name,
            shutdown_graceful_timeout=60,
        )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    setup_logging(get_settings().log_level)
    queues = [q.strip() for q in args.queues.split(",") if q.strip()]
    asyncio.run(run(queues, args.concurrency, args.name))


if __name__ == "__main__":
    main()
