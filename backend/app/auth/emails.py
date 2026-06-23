"""
Auth-related email delivery, using the *system* SMTP config (config.py /
SYSTEM_SMTP_*) — distinct from the per-user notification SMTP in AppSettings,
because a newly-registering user has no settings row yet.

The verification link is always logged at INFO so local testing works without
any SMTP configured.
"""
from __future__ import annotations

import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib

from ..config import settings

logger = logging.getLogger(__name__)


def verification_link(token: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}/verify?token={token}"


def reset_link(token: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}/reset-password?token={token}"


async def send_verification_email(to_email: str, token: str) -> None:
    link = verification_link(token)
    logger.info("Email verification link for %s: %s", to_email, link)

    if not settings.system_smtp_host:
        logger.warning(
            "SYSTEM_SMTP_HOST not configured — verification email not sent. "
            "Use the link logged above to verify locally."
        )
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Verificá tu cuenta — arcaInvoices"
    msg["From"] = settings.system_smtp_from or settings.system_smtp_user
    msg["To"] = to_email
    body = (
        "¡Hola!\n\n"
        "Para activar tu cuenta de arcaInvoices, hacé clic en el siguiente enlace:\n\n"
        f"{link}\n\n"
        "Si no creaste esta cuenta, ignorá este mensaje.\n"
    )
    msg.attach(MIMEText(body, "plain"))
    await _send(msg, to_email)


async def send_password_reset_email(to_email: str, token: str) -> None:
    link = reset_link(token)
    logger.info("Password reset link for %s: %s", to_email, link)

    if not settings.system_smtp_host:
        logger.warning(
            "SYSTEM_SMTP_HOST not configured — password reset email not sent. "
            "Use the link logged above to reset locally."
        )
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Restablecé tu contraseña — arcaInvoices"
    msg["From"] = settings.system_smtp_from or settings.system_smtp_user
    msg["To"] = to_email
    body = (
        "¡Hola!\n\n"
        "Recibimos un pedido para restablecer la contraseña de tu cuenta de "
        "arcaInvoices. Hacé clic en el siguiente enlace para elegir una nueva "
        "contraseña (el enlace vence en 2 horas):\n\n"
        f"{link}\n\n"
        "Si no pediste este cambio, ignorá este mensaje: tu contraseña sigue igual.\n"
    )
    msg.attach(MIMEText(body, "plain"))
    await _send(msg, to_email)


async def _send(msg: MIMEMultipart, to_email: str) -> None:
    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.system_smtp_host,
            port=settings.system_smtp_port,
            username=settings.system_smtp_user or None,
            password=settings.system_smtp_password or None,
            start_tls=True,
        )
    except Exception as exc:  # never block the request on email failure
        logger.error("Failed to send email to %s: %s", to_email, exc)
