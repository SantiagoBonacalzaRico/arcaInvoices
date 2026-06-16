from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from typing import List
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Invoice, OcrCorrection, User
from ..auth.security import get_current_user
from ..schemas import (
    InvoiceCreate,
    InvoiceOut,
    InvoiceUpdate,
    OcrCorrection as OcrCorrectionSchema,
    OcrResult,
    SyncStatusUpdate,
)

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


def _get_invoice_or_404(invoice_id: int, db: Session, user_id: int) -> Invoice:
    inv = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.user_id == user_id)
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


def _to_out(inv: Invoice, db: Session, user_id: int, memo: Optional[dict] = None) -> InvoiceOut:
    """
    Build an InvoiceOut enriched with the emisor's razón social.
    Reads the razón social from the cache ONLY (no network) so list/get stay
    fast — the cache is populated in the background when an invoice is created.
    `memo` dedupes cache reads within a single request for shared CUITs.
    """
    from ..afip.padron import cached_razon_social

    out = InvoiceOut.model_validate(inv)
    if memo is not None and inv.cuit in memo:
        out.razon_social = memo[inv.cuit]
    else:
        razon = cached_razon_social(inv.cuit, db, user_id) or None
        if memo is not None:
            memo[inv.cuit] = razon
        out.razon_social = razon
    return out


@router.post("/scan/detect", status_code=status.HTTP_200_OK)
async def detect_codes(
    files: List[UploadFile] = File(...),
    user: User = Depends(get_current_user),
):
    """
    Fast barcode/QR pre-scan — no OCR.  Returns within ~100 ms.
    Frontend uses this to show an accurate status label before the slow OCR starts.
    """
    import io
    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    source: str | None = None
    qr_url: str | None = None

    for file in files:
        data = await file.read()
        try:
            pil = ImageOps.exif_transpose(
                Image.open(io.BytesIO(data)).convert("RGB")
            )
            img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        except Exception:
            continue

        from ..ocr.barcode import scan as barcode_scan
        bc = barcode_scan(img)
        if bc:
            if bc.source == "arca_qr":
                return {"barcode_source": "arca_qr", "qr_url": None}
            if source is None:
                source = bc.source
            if qr_url is None:
                qr_url = bc.other_qr_url

    return {"barcode_source": source, "qr_url": qr_url}


@router.post("/scan", response_model=OcrResult, status_code=status.HTTP_200_OK)
async def scan_invoice(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload one or more invoice images; run OCR; return merged extracted fields."""
    if not files:
        raise HTTPException(status_code=422, detail="At least one image is required")

    images_bytes: list[bytes] = []
    for file in files:
        if file.content_type not in ALLOWED_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported image type: {file.content_type}",
            )
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 20 MB)")
        images_bytes.append(data)

    from ..ocr.extractor import extract_multi
    try:
        result = extract_multi(images_bytes, db=db)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"OCR failed: {exc}")
    return result


@router.post("/scan/save-image", status_code=status.HTTP_200_OK)
async def save_scanned_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict:
    """
    Save the uploaded invoice image to disk and return its path.
    Call this before POST /api/invoices so the invoice record can reference the file.
    """
    from ..config import settings as cfg
    dest_dir = Path(cfg.invoice_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "invoice.jpg").suffix or ".jpg"
    filename = f"{uuid4().hex}{ext}"
    dest = dest_dir / filename
    data = await file.read()
    dest.write_bytes(data)
    return {"image_path": str(dest)}


def _prefetch_razon_social(cuit: str, user_id: int) -> None:
    """
    Background job: resolve and cache the razón social for a CUIT.
    Runs after the response is sent, with its own DB session, so a slow or
    failing ARCA/WSAA call never blocks invoice creation.
    """
    from ..database import SessionLocal
    from ..afip.padron import lookup

    db = SessionLocal()
    try:
        lookup(cuit, db, user_id)  # cache-first; caches the result if found
    except Exception:
        pass
    finally:
        db.close()


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    inv = Invoice(**payload.model_dump(), user_id=user.id)
    db.add(inv)
    db.commit()
    db.refresh(inv)
    # Fill the razón social cache in the background so the list view never has
    # to hit ARCA on render (and so a slow WSAA call doesn't delay this save).
    background_tasks.add_task(_prefetch_razon_social, inv.cuit, user.id)
    return _to_out(inv, db, user.id)


@router.get("", response_model=list[InvoiceOut])
def list_invoices(
    status: Optional[str] = Query(None, description="Filter by sync_status"),
    category: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Invoice).filter(Invoice.user_id == user.id)
    if status:
        q = q.filter(Invoice.sync_status == status)
    if category:
        q = q.filter(Invoice.category == category)
    rows = q.order_by(Invoice.invoice_date.desc()).offset(offset).limit(limit).all()
    memo: dict[str, Optional[str]] = {}
    return [_to_out(inv, db, user.id, memo) for inv in rows]


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _to_out(_get_invoice_or_404(invoice_id, db, user.id), db, user.id)


@router.patch("/{invoice_id}/sync-status", response_model=InvoiceOut)
def set_sync_status(
    invoice_id: int,
    payload: SyncStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Manually flip an invoice's sync status (no AFIP call).
    'synced' stamps synced_at = now; 'pending' clears it.
    """
    inv = _get_invoice_or_404(invoice_id, db, user.id)
    inv.sync_status = payload.sync_status
    inv.synced_at = datetime.utcnow() if payload.sync_status == "synced" else None
    db.commit()
    db.refresh(inv)
    return _to_out(inv, db, user.id)


@router.put("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: int,
    payload: InvoiceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    inv = _get_invoice_or_404(invoice_id, db, user.id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(inv, field, value)
    db.commit()
    db.refresh(inv)
    return _to_out(inv, db, user.id)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    inv = _get_invoice_or_404(invoice_id, db, user.id)
    db.delete(inv)
    db.commit()


@router.post("/corrections", status_code=status.HTTP_201_CREATED)
def record_correction(
    payload: OcrCorrectionSchema,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Record a user-provided correction for an unrecognized OCR field.
    This feeds the learning loop — future scans of the same invoice layout
    will use the stored correction.
    """
    corr = OcrCorrection(**payload.model_dump(), user_id=user.id)
    db.add(corr)
    db.commit()
    return {"status": "saved"}
