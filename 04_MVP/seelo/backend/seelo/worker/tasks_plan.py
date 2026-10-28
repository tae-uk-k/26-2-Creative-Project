"""plan 큐 작업(06 4장): 정비안 글 만들기. 본문은 services/fix_plan_service."""

from seelo.services import fix_plan_service
from seelo.worker.app import app


@app.task(name="generateFixPlan", queue="plan")
async def generate_fix_plan(fix_plan_id: int) -> None:
    await fix_plan_service.generate(fix_plan_id)
