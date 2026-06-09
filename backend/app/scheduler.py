from __future__ import annotations
import asyncio
import logging
from calendar import monthrange
from datetime import date, datetime

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


async def _run_sync_job() -> None:
    from .database import SessionLocal
    from .afip.siradig import run_sync

    logger.info("Monthly SiRADIG sync triggered by scheduler")
    db = SessionLocal()
    try:
        log = run_sync(db)
        logger.info("Sync completed: status=%s synced=%d", log.status, log.invoices_synced)
    except Exception as exc:
        logger.error("Sync job error: %s", exc)
    finally:
        db.close()


async def _check_and_notify_job() -> None:
    from .database import SessionLocal
    from .models import AppSettings, Invoice
    from .notifications import notify

    db = SessionLocal()
    try:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        if not s:
            return
        pending = db.query(Invoice).filter(Invoice.sync_status == "pending").count()
        if pending < s.min_invoice_threshold:
            next_date = _next_sync_date(s.sync_day_of_month)
            subject = "⚠️ Pocas facturas cargadas antes de la sincronización con ARCA"
            body = (
                f"Hola!\n\n"
                f"Tenés sólo {pending} factura(s) cargada(s), "
                f"pero la sincronización con SiRADIG está programada para el {next_date.strftime('%d/%m/%Y')}.\n\n"
                f"Por favor, cargá al menos {s.min_invoice_threshold} facturas antes de esa fecha.\n\n"
                f"— Factura SiRADIG"
            )
            results = await notify(s, subject, body)
            logger.info("Notification sent: %s", results)
    except Exception as exc:
        logger.error("Notification job error: %s", exc)
    finally:
        db.close()


def _reschedule(scheduler: AsyncIOScheduler, sync_day: int, notify_days_before: int) -> None:
    for job_id in ("monthly_sync", "pre_notification"):
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    scheduler.add_job(
        _run_sync_job,
        "cron",
        day=sync_day,
        hour=9,
        minute=0,
        id="monthly_sync",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    notify_day = max(1, sync_day - notify_days_before)
    scheduler.add_job(
        _check_and_notify_job,
        "cron",
        day=notify_day,
        hour=9,
        minute=0,
        id="pre_notification",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Scheduled: sync on day %d, notify on day %d", sync_day, notify_day)


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        jobstores = {"default": SQLAlchemyJobStore(url=settings.db_url)}
        _scheduler = AsyncIOScheduler(jobstores=jobstores, timezone="America/Argentina/Buenos_Aires")
    return _scheduler


def start_scheduler() -> None:
    from .database import SessionLocal
    from .models import AppSettings

    scheduler = get_scheduler()
    db = SessionLocal()
    try:
        s = db.query(AppSettings).filter(AppSettings.id == 1).first()
        sync_day = s.sync_day_of_month if s else 20
        notify_days = s.notification_days_before if s else 5
    finally:
        db.close()

    _reschedule(scheduler, sync_day, notify_days)
    scheduler.start()
    logger.info("Scheduler started")


def update_schedule(sync_day: int, notify_days_before: int) -> None:
    scheduler = get_scheduler()
    _reschedule(scheduler, sync_day, notify_days_before)


def next_sync_date(sync_day: int) -> date:
    return _next_sync_date(sync_day)
