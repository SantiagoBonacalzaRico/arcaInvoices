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
_OCR_MAX_SIDE = 2000  # max pixels on longest side before resizing
_OCR_TMP_DIR  = Path(__file__).parent.parent.parent / "data" / "tmp"


# ── Image preprocessing ───────────────────────────────────────────────────────

def _resize_for_ocr(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= _OCR_MAX_SIDE:
        return img
    scale = _OCR_MAX_SIDE / longest
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def _to_gray(img: np.ndarray) -> np.ndarray:
    """Resize + convert to grayscale. No thresholding — preserves tonal range for photos."""
    return cv2.cvtColor(_resize_for_ocr(img), cv2.COLOR_BGR2GRAY)


# ── Tesseract runner ──────────────────────────────────────────────────────────

def _tesseract(gray: np.ndarray, psm: str) -> str:
    """
    Run Tesseract on a grayscale numpy array.
    Writes to backend/data/tmp/ to avoid macOS /tmp symlink restrictions.
    """
    _OCR_TMP_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = _OCR_TMP_DIR / f"ocr_{uuid.uuid4().hex}.jpg"
    try:
        Image.fromarray(gray).save(str(tmp_path), format="JPEG", quality=95)
        result = subprocess.run(
            [pytesseract.pytesseract.tesseract_cmd, str(tmp_path),
             "stdout", "-l", "spa", "--psm", psm],
            capture_output=True, timeout=60,
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Tesseract error (rc={result.returncode}): {err.strip()}")
        return result.stdout.decode("utf-8", errors="replace")
    finally:
        tmp_path.unlink(missing_ok=True)


def _run_ocr(img: np.ndarray) -> str:
    """
    Two-pass OCR for maximum field coverage:
      Pass 1 — PSM 4 (single-column variable-size text) on the full image:
               best for body text, product lines, TOTAL label.
      Pass 2 — PSM 6 (uniform block) on the bottom 25% of the image:
               better for the dense receipt footer where CUIT, CAE,
               and comprobante number are printed in small uniform text.
    Both results are concatenated; field extractors scan the combined text.
    """
    gray = _to_gray(img)
    full_text   = _tesseract(gray, "4")
    footer_gray = gray[int(gray.shape[0] * 0.75):, :]
    footer_text = _tesseract(footer_gray, "6")
    return full_text + "\n" + footer_text


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

    CAE numbers (14 digits, labelled C.A.E. / CAE) are explicitly skipped.
    """
    # Mask CAE numbers: any 10-18 digit sequence (possibly garbled with slashes/spaces)
    # that appears within 200 chars of the word COMPROBANTE or the C.A.E label.
    # On receipts the only large numbers in those sections are CAE codes — never
    # the XXXXX-XXXXXXXX comprobante number.
    def _mask_cae(m: re.Match) -> str:
        # Replace only the digit (and slash) run with placeholders
        return m.group(0)[:m.start(1) - m.start(0)] + "X" * len(m.group(1))

    clean = re.sub(
        r"(?i)COMPROBANTE.{0,200}?([\d/]{10,20})",
        _mask_cae,
        text,
        flags=re.DOTALL,
    )
    clean = re.sub(
        r"(?i)C\.?A\.?E\.?.{0,50}?([\d/]{10,20})",
        _mask_cae,
        clean,
    )

    # Pass 1 — joined XXXXX-XXXXXXXX token
    m = P.INVOICE_JOINED.search(clean)
    if m:
        pv = m.group(1).zfill(5)
        return OcrField(value=f"{pv}-{m.group(2)}", confidence=0.93)

    # Pass 2 — spaced pair XXXXX  XXXXXXXX
    m = P.INVOICE_SPACED.search(clean)
    if m:
        pv = m.group(1).zfill(5)
        return OcrField(value=f"{pv}-{m.group(2)}", confidence=0.80)

    # Pass 3 — label-guided (skip if label is part of "C.A.E." reference)
    for label_m in P.INVOICE_LABELS.finditer(clean):
        # Make sure the label isn't preceded by "CAE" within 10 chars
        preceding = clean[max(0, label_m.start() - 10):label_m.start()]
        if re.search(r"C\.?A\.?E", preceding, re.IGNORECASE):
            continue
        after = clean[label_m.end():label_m.end() + 100]
        nums = re.findall(r"\d+", after)
        # POS must be at least 1 digit, comprobante number at least 4 digits
        # (rejects date fragments like "11/06/2026" → [11, 06, 2026])
        if len(nums) >= 2 and len(nums[0]) >= 1 and len(nums[1]) >= 4:
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
    Find the grand total amount.

    Strategy (in order):
      1. Last 'total' label match → amount in the next 150 chars (conf 0.90).
      2. No label found → largest amount in the last 800 chars (conf 0.70).
         On Argentine documents the grand total is always the largest number
         in the footer region and appears after all line items.

    The label may be OCR-garbled (e.g. 'TOTAL' → 'ME TOTAL', 'TOTAI') so
    we also fall back gracefully to the positional heuristic.
    """
    best_label_pos = -1
    for m in P.TOTAL_LABEL.finditer(text):
        best_label_pos = m.end()

    if best_label_pos >= 0:
        search_area = text[best_label_pos: best_label_pos + 150]
        conf_boost  = 0.90
    else:
        # Fallback: scan the last 800 chars — grand total is always in footer
        search_area = text[-800:]
        conf_boost  = 0.70

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
    raw_text = _run_ocr(img)

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
