from __future__ import annotations
import io
import re
import subprocess
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

import cv2
import imagehash
import numpy as np
import pytesseract
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from ..models import OcrCorrection
from ..schemas import OcrField, OcrResult
from . import patterns as P

CONFIDENCE_THRESHOLD = 0.6
_OCR_MAX_SIDE = 2000   # max pixels on longest side before resizing
_OCR_TMP_DIR  = Path(__file__).parent.parent.parent / "data" / "tmp"


# ── Image preprocessing ───────────────────────────────────────────────────────

def _resize_for_ocr(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= _OCR_MAX_SIDE:
        return img
    scale = _OCR_MAX_SIDE / longest
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def _preprocess(img: np.ndarray) -> np.ndarray:
    """
    CLAHE on grayscale.  Works for both scanned documents and smartphone
    photos with variable lighting.  Binary thresholding is avoided because
    it destroys tonal range in real photos.
    """
    img = _resize_for_ocr(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


# ── Tesseract runner ──────────────────────────────────────────────────────────

def _run_ocr(pil_image: Image.Image) -> str:
    """
    Write the image to our own data/tmp dir (not system TMPDIR) so the
    tesseract subprocess can always reach it regardless of macOS /tmp symlink
    restrictions.  Saves as JPEG because Leptonica is more reliable with it.
    """
    _OCR_TMP_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = _OCR_TMP_DIR / f"ocr_{uuid.uuid4().hex}.jpg"
    try:
        pil_image.save(str(tmp_path), format="JPEG", quality=95)
        result = subprocess.run(
            [pytesseract.pytesseract.tesseract_cmd, str(tmp_path),
             "stdout", "-l", "spa", "--psm", "6"],
            capture_output=True, timeout=60,
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Tesseract error (rc={result.returncode}): {err.strip()}")
        return result.stdout.decode("utf-8", errors="replace")
    finally:
        tmp_path.unlink(missing_ok=True)


# ── Field extractors ──────────────────────────────────────────────────────────

def _valid_cuit_digits(digits: str) -> bool:
    if len(digits) != 11 or not digits.isdigit():
        return False
    weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(d) * w for d, w in zip(digits[:10], weights))
    remainder = 11 - (total % 11)
    if remainder == 11:
        remainder = 0
    return remainder != 10 and remainder == int(digits[10])


def _extract_cuit(text: str) -> OcrField:
    """
    Three-pass CUIT extraction:
      1. Labelled: 'CUIT: XX-XXXXXXXX-X'
      2. Dashed:   anywhere in text matching XX-XXXXXXXX-X
      3. Plain:    any 11-digit run that passes the CUIT checksum

    All candidates are checksum-validated.  On tickets the CUIT often
    appears unlabelled at the top; the checksum is the reliability gate.
    """
    # Pass 1 — labelled
    m = P.CUIT_LABEL.search(text)
    if m:
        raw = re.sub(r"\D", "", m.group(1))
        if len(raw) == 11 and _valid_cuit_digits(raw):
            return OcrField(value=P.normalize_cuit(raw), confidence=0.97)

    # Pass 2 — dashed anywhere
    for m in P.CUIT_DASHED.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if _valid_cuit_digits(digits):
            return OcrField(value=P.normalize_cuit(digits), confidence=0.92)

    # Pass 3 — any valid 11-digit sequence (broad scan)
    for m in P.CUIT_PLAIN.finditer(text):
        raw = m.group(1)
        if _valid_cuit_digits(raw):
            return OcrField(value=P.normalize_cuit(raw), confidence=0.75)

    return OcrField(value=None, confidence=0.0)


def _extract_date(text: str) -> OcrField:
    """
    Prefer dates that appear after a 'Fecha' label; fall back to the first
    valid date found anywhere.  Filters out implausible years.
    """
    def _try_parse(d: str, mo: str, yr: str) -> Optional[date]:
        try:
            parsed = date(int(yr), int(mo), int(d))
            if 2000 <= parsed.year <= 2099:
                return parsed
        except ValueError:
            pass
        return None

    # Prefer labelled date
    label_m = P.DATE_LABEL.search(text)
    if label_m:
        after = text[label_m.end():label_m.end() + 30]
        for pat in (P.DATE_DMY_SLASH, P.DATE_DMY_DASH, P.DATE_DMY_DOT):
            m = pat.search(after)
            if m:
                parsed = _try_parse(m.group(1), m.group(2), m.group(3))
                if parsed:
                    return OcrField(value=str(parsed), confidence=0.95)

    # Scan full text
    for pat in (P.DATE_DMY_SLASH, P.DATE_DMY_DASH, P.DATE_DMY_DOT):
        for m in pat.finditer(text):
            parsed = _try_parse(m.group(1), m.group(2), m.group(3))
            if parsed:
                return OcrField(value=str(parsed), confidence=0.85)

    return OcrField(value=None, confidence=0.0)


def _extract_invoice_number(text: str) -> OcrField:
    """
    Official ARCA format (RG 1492/2003 + Oct-2018 extension):
      Punto de venta:  4 digits (legacy) or 5 digits (current)
      Nro comprobante: 8 digits
      Printed as:      XXXXX-XXXXXXXX

    Three passes:
      1. Exact joined token    XXXXX-XXXXXXXX / XXXX-XXXXXXXX
      2. Spaced pair           XXXXX  XXXXXXXX
      3. Label-guided          any label + following digit groups
    """
    # Pass 1 — joined
    m = P.INVOICE_JOINED.search(text)
    if m:
        pv = m.group(1).zfill(5)
        return OcrField(value=f"{pv}-{m.group(2)}", confidence=0.93)

    # Pass 2 — spaced
    m = P.INVOICE_SPACED.search(text)
    if m:
        pv = m.group(1).zfill(5)
        return OcrField(value=f"{pv}-{m.group(2)}", confidence=0.80)

    # Pass 3 — label-guided
    label_m = P.INVOICE_LABELS.search(text)
    if label_m:
        after = text[label_m.end():label_m.end() + 100]
        nums = re.findall(r"\d+", after)
        if len(nums) >= 2:
            pv  = nums[0].zfill(5)[:5]
            num = nums[1].zfill(8)[:8]
            return OcrField(value=f"{pv}-{num}", confidence=0.68)
        elif nums and len(nums[0]) >= 8:
            raw = nums[0]
            pv  = raw[:5].zfill(5)
            num = raw[5:13].zfill(8)
            return OcrField(value=f"{pv}-{num}", confidence=0.55)

    return OcrField(value=None, confidence=0.0)


def _extract_total(text: str) -> OcrField:
    """
    Search for the grand total.

    Strategy:
      1. Find the LAST 'total' label (the grand total is always last on a
         ticket/factura — subtotals come earlier).
      2. Within the next 150 chars, find the largest amount.
      3. If no label found, take the largest amount in the last 400 chars
         of the document (where totals always appear on Argentine documents).
    """
    best_label_pos = -1
    for m in P.TOTAL_LABEL.finditer(text):
        best_label_pos = m.end()

    if best_label_pos >= 0:
        search_area = text[best_label_pos: best_label_pos + 150]
        conf_boost = 0.85
    else:
        search_area = text[-400:]
        conf_boost = 0.55

    amounts = P.AMOUNT.findall(search_area)
    best_val, best_float = None, 0.0
    for raw in amounts:
        normalized = P.normalize_amount(raw)
        try:
            v = float(normalized)
            if v > best_float:
                best_float, best_val = v, normalized
        except ValueError:
            continue

    if best_val:
        return OcrField(value=best_val, confidence=conf_boost)
    return OcrField(value=None, confidence=0.0)


# ── Learning store ────────────────────────────────────────────────────────────

def _lookup_corrections(image_hash: str, db: Session) -> dict[str, str]:
    rows = (
        db.query(OcrCorrection)
        .filter(OcrCorrection.image_hash == image_hash)
        .all()
    )
    return {r.field_name: r.correct_value for r in rows}


# ── Main entry point ──────────────────────────────────────────────────────────

def extract(image_bytes: bytes, db: Optional[Session] = None) -> OcrResult:
    # Open via PIL and apply EXIF rotation (phone photos are often stored sideways)
    pil_original = ImageOps.exif_transpose(
        Image.open(io.BytesIO(image_bytes)).convert("RGB")
    )

    image_hash = str(imagehash.phash(pil_original))

    # Learning store — exact image match returns stored corrections
    known: dict[str, str] = {}
    if db is not None:
        known = _lookup_corrections(image_hash, db)

    img = cv2.cvtColor(np.array(pil_original), cv2.COLOR_RGB2BGR)
    processed = _preprocess(img)
    raw_text = _run_ocr(Image.fromarray(processed))

    cuit_field  = OcrField(value=known["cuit"],           confidence=1.0) if "cuit"           in known else _extract_cuit(raw_text)
    date_field  = OcrField(value=known["invoice_date"],   confidence=1.0) if "invoice_date"   in known else _extract_date(raw_text)
    inv_field   = OcrField(value=known["invoice_number"], confidence=1.0) if "invoice_number" in known else _extract_invoice_number(raw_text)
    total_field = OcrField(value=known["total_amount"],   confidence=1.0) if "total_amount"   in known else _extract_total(raw_text)

    unrecognized = [
        name for name, field in [
            ("cuit",           cuit_field),
            ("invoice_date",   date_field),
            ("invoice_number", inv_field),
            ("total_amount",   total_field),
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
