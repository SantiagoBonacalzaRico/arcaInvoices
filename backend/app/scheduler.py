from __future__ import annotations
import logging
from calendar import monthrange
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from .config import settings

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


def _next_sync_date(sync_day: int) -> date:
    today = date.today()
    year, month = today.year, today.month
    max_day = monthrange(year, month)[1]
    day = min(sync_day, max_day)
    candidate = date(year, month, day)
    if candidate <= today:
        # Move to next month
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        max_day = monthrange(year, month)[1]
        candidate = date(year, month, min(sync_day, max_day))
    return candidate


def _effective_day(target_day: int, today: date) -> int:
    """Clamp a configured day-of-month to the current month's length."""
    return min(target_day, monthrange(today.year, today.month)[1])


async def _notify_user(user_id: int) -> None:
    from .database import SessionLocal
    from .models import AppSettings, Invoice
    from .notifications import notify

    db = SessionLocal()
    try:
        s = db.query(AppSettings).filter(AppSettings.user_id == user_id).first()
        if not s:
            return
        pending = (
            db.query(Invoice)
            .filter(Invoice.user_id == user_id, Invoice.sync_status == "pending")
            .count()
        )
        if pending < s.min_invoice_threshold:
            next_date = _next_sync_date(s.sync_day_of_month)
            subject = "⚠️ Pocas facturas cargadas antes de la sincronización con ARCA"
            body = (
                f"Hola!\n\n"
                f"Tenés sólo {pending} factura(s) cargada(s), "
                f"pero la sincronización con SiRADIG está programada para el {next_date.strftime('%d/%m/%Y')}.\n\n"
                f"Por favor, cargá al menos {s.min_invoice_threshold} facturas antes de esa fecha.\n\n"
                f"— arcaInvoices"
            )
            results = await notify(s, subject, body)
            logger.info("Notification sent (user %s): %s", user_id, results)
    except Exception as exc:
        logger.error("Notification job error (user %s): %s", user_id, exc)
    finally:
        db.close()


async def _daily_tick() -> None:
    """
    Runs once a day at 09:00. Iterates every user's settings and sends the
    pre-load reminder to users whose notification day matches today.
    Reading settings live each day means no per-user cron jobs to manage.
    """
    from .database import SessionLocal
    from .models import AppSettings

    today = date.today()
    db = SessionLocal()
    try:
        all_settings = db.query(AppSettings).all()
        # Snapshot the values we need before closing the session.
        rows = [
            (s.user_id, s.sync_day_of_month, s.notification_days_before)
            for s in all_settings
            if s.user_id is not None
        ]
    finally:
        db.close()

    # Reminder only — there is no ARCA API, so nothing is submitted automatically.
    # Users load their invoices manually via the SiRADIG co-pilot.
    for user_id, sync_day, notify_days in rows:
        notify_d = _effective_day(max(1, sync_day - notify_days), today)
        if today.day == notify_d:
            await _notify_user(user_id)


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        jobstores = {"default": SQLAlchemyJobStore(url=settings.db_url)}
        _scheduler = AsyncIOScheduler(jobstores=jobstores, timezone="America/Argentina/Buenos_Aires")
    return _scheduler


def start_scheduler() -> None:
    scheduler = get_scheduler()
    scheduler.add_job(
        _daily_tick,
        "cron",
        hour=9,
        minute=0,
        id="daily_tick",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("Scheduler started (daily multi-user tick at 09:00)")


def update_schedule() -> None:
    """
    No-op kept for API compatibility. The daily tick reads each user's settings
    live, so changing a user's sync/notify day takes effect without rescheduling.
    """
    return None


def next_sync_date(sync_day: int) -> date:
    return _next_sync_date(sync_day)
