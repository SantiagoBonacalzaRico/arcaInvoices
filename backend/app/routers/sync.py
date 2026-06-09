from __future__ import annotations
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSettings, Invoice, SyncLog
from ..schemas import SyncLogOut, SyncStatusOut
from ..scheduler import next_sync_date

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/trigger", response_model=SyncLogOut)
def trigger_sync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Manually trigger a sync to ARCA/SiRADIG."""
    from ..afip.siradig import run_sync
    log = run_sync(db)
    return log


@router.get("/status", response_model=SyncStatusOut)
def sync_status(db: Session = Depends(get_db)):
    last_log = (
        db.query(SyncLog)
        .order_by(SyncLog.started_at.desc())
        .first()
    )
    pending_count = db.query(Invoice).filter(Invoice.sync_status == "pending").count()
    s = db.query(AppSettings).filter(AppSettings.id == 1).first()
    sync_day = s.sync_day_of_month if s else 20
    return SyncStatusOut(
        last_sync=last_log,
        pending_count=pending_count,
        next_sync_date=next_sync_date(sync_day),
    )


@router.get("/history", response_model=list[SyncLogOut])
def sync_history(limit: int = 20, db: Session = Depends(get_db)):
    return (
        db.query(SyncLog)
        .order_by(SyncLog.started_at.desc())
        .limit(limit)
        .all()
    )
