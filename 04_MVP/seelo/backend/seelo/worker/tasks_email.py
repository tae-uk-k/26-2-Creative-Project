"""메일 발송 작업(06 4장 sendEmail)."""

from procrastinate import RetryStrategy

from seelo.worker.app import app


# max_attempts는 "재시도" 횟수다(첫 실행 제외): 처음 1번 + 재시도 3번 = 최대 4번.
# email_service.MAX_ATTEMPTS(4)번째 실패는 예외를 올리지 않고 failed로 끝낸다.
@app.task(name="sendEmail", queue="email", retry=RetryStrategy(max_attempts=3, exponential_wait=5))
async def send_email(email_log_id: int) -> None:
    from seelo.services import email_service

    await email_service.send(email_log_id)
