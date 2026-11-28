"""SMTP 발송(10 4장). 개발은 Mailpit, 운영은 D-08 서비스."""

from email.message import EmailMessage
from email.utils import make_msgid

import aiosmtplib

from seelo.config import get_settings

SEND_TIMEOUT_S = 30


class SmtpMailer:
    """aiosmtplib로 텍스트+HTML 메일 한 통을 보낸다. 실패하면 예외를 그대로 올린다."""

    async def send(self, *, to: list[str], subject: str, text: str, html: str) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"] = s.mail_from
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain="seelo")
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        password = s.smtp_password.get_secret_value()
        await aiosmtplib.send(
            msg,
            hostname=s.smtp_host,
            port=s.smtp_port,
            username=s.smtp_username or None,
            password=password or None,
            start_tls=s.smtp_starttls,
            timeout=SEND_TIMEOUT_S,
        )
