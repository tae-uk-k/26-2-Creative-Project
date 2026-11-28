"""쇼핑몰 작업. 브라우저 작업은 worker-fix(Playwright 이미지·프로필 볼륨)의 commerce_browser 큐에서 돈다.

자동 재시도하지 않는다(Procrastinate 기본 retry 없음). 저장 결과가 불명확하면 재조회 작업을 따로 받는다.
"""

from seelo.services import commerce_jobs
from seelo.worker.app import app


@app.task(name="commerceBrowserJob", queue="commerce_browser")
async def commerce_browser_job(job_id: int) -> None:
    await commerce_jobs.run(job_id)


@app.task(name="commerceAiJob", queue="plan")
async def commerce_ai_job(job_id: int) -> None:
    await commerce_jobs.run(job_id)


@app.task(name="commerceMeasureOpenai", queue="ai_openai")
async def commerce_measure_openai(job_id: int) -> None:
    await commerce_jobs.run(job_id)


@app.task(name="commerceMeasureGemini", queue="ai_gemini")
async def commerce_measure_gemini(job_id: int) -> None:
    await commerce_jobs.run(job_id)
