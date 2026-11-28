"""재측정 값 비교·보고서 작업(06 4장, 10 2·3장)."""

from procrastinate import RetryStrategy

from seelo.services import remeasure_service, report_service
from seelo.worker.app import app


@app.task(name="compareFixValues", queue="fix", retry=RetryStrategy(max_attempts=1, wait=30))
async def compare_fix_values(fix_request_id: int, run_id: int) -> None:
    await remeasure_service.compare_fix_values(fix_request_id, run_id)


@app.task(name="generateComparisonReport", queue="report")
async def generate_comparison_report(report_id: int) -> None:
    await report_service.generate(report_id)
