"""measure·ai 큐 작업(06 4장, 13 12장). 본문은 services."""

from procrastinate import RetryStrategy

from seelo.services import extract_service, finalize_service, measure_service, question_service
from seelo.worker.app import app


@app.task(name="generateQuestions", queue="measure")
async def generate_questions(run_id: int) -> None:
    await question_service.generate(run_id)


@app.task(name="runMeasurement", queue="measure")
async def run_measurement(run_id: int) -> None:
    await measure_service.run(run_id)


@app.task(name="callAi", queue="ai_openai")  # 등록할 때 queue="ai_gemini"로 바꿀 수 있다
async def call_ai(execution_id: int) -> None:
    await measure_service.call_ai(execution_id)


@app.task(name="extractRecommendations", queue="measure")
async def extract_recommendations(response_id: int) -> None:
    await extract_service.extract(response_id)


@app.task(name="finalizeRun", queue="measure", retry=RetryStrategy(max_attempts=1, wait=10))
async def finalize_run(run_id: int) -> None:
    await finalize_service.finalize(run_id)
