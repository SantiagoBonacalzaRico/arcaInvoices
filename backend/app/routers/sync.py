from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSettings, Invoice, SyncLog, User
from ..auth.security import get_current_user
from ..schemas import SyncLogOut, SyncStatusOut
from ..scheduler import next_sync_date

router = APIRouter(prefix="/api/sync", tags=["sync"])

# Note: there is no public ARCA API to submit the F.572, so there is no
# automated "sync". Invoices are loaded manually via the SiRADIG co-pilot;
# these endpoints only report progress + the target load date.


@router.get("/status", response_model=SyncStatusOut)
def sync_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    last_log = (
        db.query(SyncLog)
        .filter(SyncLog.user_id == user.id)
        .order_by(SyncLog.started_at.desc())
        .first()
    )
    pending_count = (
        db.query(Invoice)
        .filter(Invoice.user_id == user.id, Invoice.sync_status == "pending")
        .count()
    )
    s = db.query(AppSettings).filter(AppSettings.user_id == user.id).first()
    sync_day = s.sync_day_of_month if s else 20
    return SyncStatusOut(
        last_sync=last_log,
        pending_count=pending_count,
        next_sync_date=next_sync_date(sync_day),
    )


@router.get("/history", response_model=list[SyncLogOut])
def sync_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return (
        db.query(SyncLog)
        .filter(SyncLog.user_id == user.id)
        .order_by(SyncLog.started_at.desc())
        .limit(limit)
        .all()
    )
