"""collect 큐 작업(06 4장). 본문은 services/collect_service.py."""

from seelo.services import collect_service
from seelo.worker.app import app


@app.task(name="collectStore", queue="collect")
async def collect_store(store_id: int, run_id: int | None) -> None:
    await collect_service.collect_store(store_id, run_id)
