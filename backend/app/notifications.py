from __future__ import annotations
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import aiosmtplib
from sqlalchemy.orm import Session

from .models import AppSettings


async def send_email(settings: AppSettings, subject: str, body: str) -> None:
    if not settings.notify_email or not settings.email_address:
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user or settings.email_address
    msg["To"] = settings.email_address
    msg.attach(MIMEText(body, "plain"))
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host or "smtp.gmail.com",
        port=settings.smtp_port or 587,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
    )


def send_sms(settings: AppSettings, body: str) -> None:
    if not settings.notify_sms or not settings.phone_number:
        return
    try:
        from twilio.rest import Client as TwilioClient
    except ImportError:
        raise ImportError("twilio package required for SMS. Run: pip install twilio")

    import os
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_number = os.environ.get("TWILIO_FROM_NUMBER", "")
    if not all([account_sid, auth_token, from_number]):
        raise ValueError(
            "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER env vars."
        )
    client = TwilioClient(account_sid, auth_token)
    client.messages.create(body=body, from_=from_number, to=settings.phone_number)


async def notify(settings: AppSettings, subject: str, body: str) -> dict[str, str]:
    results: dict[str, str] = {}
    if settings.notify_email:
        try:
            await send_email(settings, subject, body)
            results["email"] = "sent"
        except Exception as exc:
            results["email"] = f"error: {exc}"
    if settings.notify_sms:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, send_sms, settings, body)
            results["sms"] = "sent"
        except Exception as exc:
            results["sms"] = f"error: {exc}"
    return results
