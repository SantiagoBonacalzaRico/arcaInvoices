from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Invoice, OcrCorrection
from ..schemas import InvoiceCreate, InvoiceOut, InvoiceUpdate, OcrCorrection as OcrCorrectionSchema, OcrResult

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


def _get_invoice_or_404(invoice_id: int, db: Session) -> Invoice:
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.post("/scan", response_model=OcrResult, status_code=status.HTTP_200_OK)
async def scan_invoice(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload an invoice image; run OCR; return extracted fields (not saved yet)."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported image type: {file.content_type}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    from ..ocr.extractor import extract
    try:
        result = extract(data, db=db)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"OCR failed: {exc}")
    return result


@router.post("/scan/save-image", status_code=status.HTTP_200_OK)
async def save_scanned_image(file: UploadFile = File(...)) -> dict:
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


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    inv = Invoice(**payload.model_dump())
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.get("", response_model=list[InvoiceOut])
def list_invoices(
    status: Optional[str] = Query(None, description="Filter by sync_status"),
    category: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Invoice)
    if status:
        q = q.filter(Invoice.sync_status == status)
    if category:
        q = q.filter(Invoice.category == category)
    return q.order_by(Invoice.invoice_date.desc()).offset(offset).limit(limit).all()


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return _get_invoice_or_404(invoice_id, db)


@router.put("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db)):
    inv = _get_invoice_or_404(invoice_id, db)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(inv, field, value)
    db.commit()
    db.refresh(inv)
    return inv


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = _get_invoice_or_404(invoice_id, db)
    db.delete(inv)
    db.commit()


@router.post("/corrections", status_code=status.HTTP_201_CREATED)
def record_correction(payload: OcrCorrectionSchema, db: Session = Depends(get_db)):
    """
    Record a user-provided correction for an unrecognized OCR field.
    This feeds the learning loop — future scans of the same invoice layout
    will use the stored correction.
    """
    corr = OcrCorrection(**payload.model_dump())
    db.add(corr)
    db.commit()
    return {"status": "saved"}
