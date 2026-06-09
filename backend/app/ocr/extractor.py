from __future__ import annotations
import io
import re
from datetime import date
from pathlib import Path
from typing import Optional

import cv2
import imagehash
import numpy as np
import pytesseract
from PIL import Image
from sqlalchemy.orm import Session

from ..models import OcrCorrection
from ..schemas import OcrField, OcrResult
from . import patterns as P

CONFIDENCE_THRESHOLD = 0.6


def _preprocess(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Deskew
    coords = np.column_stack(np.where(gray < 200))
    if len(coords) > 0:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) > 0.5:
            (h, w) = gray.shape
            M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            gray = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    # Adaptive threshold to improve contrast
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    thresh = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
    return thresh


def _compute_hash(img: np.ndarray) -> str:
    pil = Image.fromarray(img)
    return str(imagehash.phash(pil))


def _extract_cuit(text: str) -> OcrField:
    m = P.CUIT_DASHED.search(text)
    if m:
        digits = re.sub(r"\D", "", m.group(0))
        conf = 0.95 if _valid_cuit_digits(digits) else 0.45
        return OcrField(value=m.group(0), confidence=conf)
    m = P.CUIT_PLAIN.search(text)
    if m:
        raw = m.group(1)
        if _valid_cuit_digits(raw):
            return OcrField(value=P.normalize_cuit(raw), confidence=0.80)
    return OcrField(value=None, confidence=0.0)


def _valid_cuit_digits(digits: str) -> bool:
    weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(d) * w for d, w in zip(digits[:10], weights))
    remainder = 11 - (total % 11)
    if remainder == 11:
        remainder = 0
    if remainder == 10:
        return False
    return remainder == int(digits[10])


def _extract_date(text: str) -> OcrField:
    for pat in (P.DATE_DMY_SLASH, P.DATE_DMY_DASH, P.DATE_DMY_DOT):
        m = pat.search(text)
        if m:
            d, mo, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                parsed = date(yr, mo, d)
                return OcrField(value=str(parsed), confidence=0.90)
            except ValueError:
                continue
    return OcrField(value=None, confidence=0.0)


def _extract_invoice_number(text: str) -> OcrField:
    # Pass 1: joined token
    m = P.INVOICE_JOINED.search(text)
    if m:
        val = f"{m.group(1)}-{m.group(2)}"
        return OcrField(value=val, confidence=0.92)

    # Pass 2: spaced tokens on the same line
    m = P.INVOICE_SPACED.search(text)
    if m:
        val = f"{m.group(1)}-{m.group(2)}"
        return OcrField(value=val, confidence=0.80)

    # Pass 3: label-guided — find label then grab next numeric sequence(s)
    label_m = P.INVOICE_LABELS.search(text)
    if label_m:
        after = text[label_m.end():]
        nums = re.findall(r"\d+", after[:80])
        if len(nums) >= 2:
            p1, p2 = nums[0].zfill(4), nums[1].zfill(8)
            if len(p1) <= 4 and len(p2) <= 8:
                return OcrField(value=f"{p1}-{p2}", confidence=0.65)
        elif len(nums) == 1 and len(nums[0]) >= 8:
            raw = nums[0]
            return OcrField(value=f"{raw[:4]}-{raw[4:12]}", confidence=0.55)

    return OcrField(value=None, confidence=0.0)


def _extract_total(text: str) -> OcrField:
    label_m = P.TOTAL_LABEL.search(text)
    search_area = text[label_m.end():label_m.end() + 120] if label_m else text[-300:]
    amounts = P.AMOUNT.findall(search_area)
    if amounts:
        # Take the last (largest) amount — usually the grand total
        raw = amounts[-1]
        normalized = P.normalize_amount(raw)
        try:
            float(normalized)
            conf = 0.85 if label_m else 0.55
            return OcrField(value=normalized, confidence=conf)
        except ValueError:
            pass
    return OcrField(value=None, confidence=0.0)


def _lookup_corrections(image_hash: str, db: Session) -> dict[str, str]:
    corrections = (
        db.query(OcrCorrection)
        .filter(OcrCorrection.image_hash == image_hash)
        .all()
    )
    return {c.field_name: c.correct_value for c in corrections}


def extract(image_bytes: bytes, db: Optional[Session] = None) -> OcrResult:
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    processed = _preprocess(img)
    image_hash = _compute_hash(processed)

    # Check learning store first
    known: dict[str, str] = {}
    if db is not None:
        known = _lookup_corrections(image_hash, db)

    raw_text = pytesseract.image_to_string(processed, lang="spa", config="--psm 6")

    cuit_field = OcrField(value=known.get("cuit"), confidence=1.0) if "cuit" in known else _extract_cuit(raw_text)
    date_field = OcrField(value=known.get("invoice_date"), confidence=1.0) if "invoice_date" in known else _extract_date(raw_text)
    inv_field = OcrField(value=known.get("invoice_number"), confidence=1.0) if "invoice_number" in known else _extract_invoice_number(raw_text)
    total_field = OcrField(value=known.get("total_amount"), confidence=1.0) if "total_amount" in known else _extract_total(raw_text)

    unrecognized = [
        name for name, field in [
            ("cuit", cuit_field),
            ("invoice_date", date_field),
            ("invoice_number", inv_field),
            ("total_amount", total_field),
        ]
        if field.confidence < CONFIDENCE_THRESHOLD
    ]

    return OcrResult(
        cuit=cuit_field,
        invoice_date=date_field,
        invoice_number=inv_field,
        total_amount=total_field,
        raw_text=raw_text,
        image_hash=image_hash,
        unrecognized_fields=unrecognized,
    )
