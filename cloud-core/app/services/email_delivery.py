"""SMTP delivery. No fake sending: if SMTP is not configured, delivery is
refused and the caller must say so."""
import smtplib
from email.message import EmailMessage

from app.core.config import settings


class DeliveryNotConfigured(RuntimeError):
    pass


class DeliveryFailed(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.SMTP_HOST)


def send(*, to: str, subject: str, body: str) -> None:
    if not is_configured():
        raise DeliveryNotConfigured("SMTP is not configured")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.SMTP_FROM, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            if settings.SMTP_STARTTLS:
                smtp.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD.get_secret_value())
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        raise DeliveryFailed(type(exc).__name__) from None
