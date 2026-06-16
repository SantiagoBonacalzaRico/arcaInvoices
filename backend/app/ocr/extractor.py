from __future__ import annotations
import io
import re
import subprocess
import uuid
from datetime import date, timedelta
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

# OCR look-alike character substitutions for digit-only contexts.
# Two tables because 'B' is ambiguous: serif B can be misread as 8 or 7.
# g→9, G→6, M→0 cover other common substitutions on thermal-print fonts.
_DIGIT_MAP_PRIMARY = str.maketrans("OolISsZzBbGgM", "0011552286690")
_DIGIT_MAP_ALT     = str.maketrans("OolISsZzBbGgM", "0011552278690")


def _normalize_ocr_digits(s: str, alt: bool = False) -> str:
    """Replace common OCR look-alike letters with digit equivalents."""
    return s.translate(_DIGIT_MAP_ALT if alt else _DIGIT_MAP_PRIMARY)


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
    Three-pass OCR:
      Pass 1 — PSM 4 on full image: body text, TOTAL, product lines.
      Pass 2 — PSM 6 on bottom 25%: dense footer (CAE, comprobante ref).
      Pass 3 — PSM 6 on top 20% upscaled 2×: header with CUIT, NRO.COMP,
               transaction date+time (small text — needs upscaling).
    All results concatenated; field extractors scan the combined text.
    """
    gray = _to_gray(img)
    h = gray.shape[0]

    full_text   = _tesseract(gray, "4")
    footer_gray = gray[int(h * 0.75):, :]
    footer_text = _tesseract(footer_gray, "6")

    # Header: upscale 2× with Lanczos to make small header text readable
    header_region = img[:int(img.shape[0] * 0.20), :]
    header_up = cv2.resize(
        header_region,
        (header_region.shape[1] * 2, header_region.shape[0] * 2),
        interpolation=cv2.INTER_LANCZOS4,
    )
    header_gray = cv2.cvtColor(header_up, cv2.COLOR_BGR2GRAY)
    header_text = _tesseract(header_gray, "6")

    # Header first: field extractors scan from the top; total search
    # uses the last N chars so footer must remain at the end.
    return header_text + "\n" + full_text + "\n" + footer_text


def _run_ocr_clahe(img: np.ndarray) -> str:
    """
    Single CLAHE-enhanced PSM-6 pass at higher resolution (≤2400 px).
    Local contrast equalization rescues wrinkled / low-contrast / angled
    thermal receipts that the plain pass reads as noise.  Kept separate from
    _run_ocr so it can be consulted as a *fallback* per field, without
    disturbing the positional total-extraction logic of the main text.
    """
    full_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    longest   = max(full_gray.shape)
    if longest > 2400:
        scale = 2400 / longest
        full_gray = cv2.resize(
            full_gray, (int(full_gray.shape[1] * scale), int(full_gray.shape[0] * scale)),
            interpolation=cv2.INTER_AREA,
        )
    clahe_gray = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(full_gray)
    return _tesseract(clahe_gray, "6")


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
    Four-pass CUIT extraction:
      0. Labelled with OCR normalization: handles letter-for-digit misreads
         (e.g. 'O' → '0', 'B' → '8' or '7', 'l' → '1').  Two substitution
         tables tried (primary B→8, alternate B→7) so checksum picks the right one.
      1. Labelled: 'CUIT: XX-XXXXXXXX-X' (clean digits only)
      2. Dashed:   anywhere in text matching XX-XXXXXXXX-X
      3. Plain:    any 11-digit run that passes the CUIT checksum

    All candidates are checksum-validated.
    """
    # Pass 0 — labelled with OCR normalization.
    # Captures up to 18 non-newline chars after the CUIT label (enough for
    # "XX-XXXXXXXX-X" with noise), then tries both substitution tables and
    # slides through all 11-char windows so a misread in any single position
    # can still yield a valid checksum.  Sliding window only fires when the
    # full CUIT label is found (not just "CM:") to avoid spurious matches.
    _label_cuit = re.compile(
        r"C\.?U\.?I\.?T\.?\s*(?:Emisor|Nro\.?|N[°º]\.?)?\s*:?\s*([^\n|=]{0,18})",
        re.IGNORECASE,
    )
    _VALID_CUIT_TYPES = {"20", "23", "24", "27", "30", "33", "34"}
    for lm in _label_cuit.finditer(text):
        segment = lm.group(1)
        for alt in (False, True):
            digits = re.sub(r"\D", "", _normalize_ocr_digits(segment, alt=alt))
            for start in range(max(1, len(digits) - 10)):
                window = digits[start: start + 11]
                if (len(window) == 11
                        and window[:2] in _VALID_CUIT_TYPES
                        and _valid_cuit_digits(window)):
                    return OcrField(value=P.normalize_cuit(window), confidence=0.85)

    # Pass 1 — labelled (clean digits — keeps existing fast path for well-OCR'd docs)
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
    Date extraction priority:
      1. Date+time pattern DD/MM/YYYY HH:MM[:SS] — transaction timestamp on tickets
      2. Date after a 'Fecha' label
      3. Any date NOT preceded by a Vto./vencimiento context (CAE expiry)
    """
    def _try_parse(d: str, mo: str, yr: str) -> Optional[date]:
        try:
            parsed = date(int(yr), int(mo), int(d))
            # Invoices are never dated in the future — a future date means the
            # year was misread (e.g. 2-digit "26" → "28").  Reject it (1-day
            # grace covers timezone skew on same-day scans).
            if parsed.year >= 2000 and parsed <= date.today() + timedelta(days=1):
                return parsed
        except ValueError:
            pass
        return None

    def _is_vto(text: str, match_start: int) -> bool:
        """Return True if the date follows a Vto./vencimiento label within 20 chars."""
        preceding = text[max(0, match_start - 20):match_start]
        return bool(P.DATE_VTO_CONTEXT.search(preceding))

    # Pass 1 — date WITH time component (strongest signal: this is the transaction date)
    for m in P.DATE_WITH_TIME.finditer(text):
        if _is_vto(text, m.start()):
            continue
        parsed = _try_parse(m.group(1), m.group(2), m.group(3))
        if parsed:
            return OcrField(value=str(parsed), confidence=0.97)

    # Pass 2 — labelled date
    label_m = P.DATE_LABEL.search(text)
    if label_m:
        after = text[label_m.end():label_m.end() + 30]
        for pat in (P.DATE_DMY_SLASH, P.DATE_DMY_DASH, P.DATE_DMY_DOT):
            m = pat.search(after)
            if m:
                parsed = _try_parse(m.group(1), m.group(2), m.group(3))
                if parsed:
                    return OcrField(value=str(parsed), confidence=0.95)
        # 2-digit year (dd-mm-yy) — only here, right after a "Fecha" label, so a
        # tax rate or quantity elsewhere can't be mistaken for a date.  "26" → 2026.
        for pat in (P.DATE_DMY_SLASH_YY, P.DATE_DMY_DASH_YY, P.DATE_DMY_DOT_YY):
            m = pat.search(after)
            if m:
                parsed = _try_parse(m.group(1), m.group(2), "20" + m.group(3))
                if parsed:
                    return OcrField(value=str(parsed), confidence=0.88)
                # Future year ⇒ the year digit was misread (e.g. "26"→"28").  The
                # day/month are usually right, so fall back to the current year as
                # a lower-confidence best guess (flagged for the user to verify).
                guess = _try_parse(m.group(1), m.group(2), str(date.today().year))
                if guess:
                    return OcrField(value=str(guess), confidence=0.60)

    # Pass 3 — any date, skipping Vto. contexts
    for pat in (P.DATE_DMY_SLASH, P.DATE_DMY_DASH, P.DATE_DMY_DOT):
        for m in pat.finditer(text):
            if _is_vto(text, m.start()):
                continue
            parsed = _try_parse(m.group(1), m.group(2), m.group(3))
            if parsed:
                return OcrField(value=str(parsed), confidence=0.85)

    return OcrField(value=None, confidence=0.0)


def _split_invoice_digits(raw: str) -> tuple[str, str]:
    """
    Split a concatenated digit string into (POS, number) for the ARCA format.
    12 digits → POS is 4 (leading zero dropped by OCR), NUM is 8.
    13 digits → POS is 5, NUM is 8.
    Other lengths → take last 8 as NUM, remainder as POS (zero-padded to 5).
    """
    n = len(raw)
    if n == 12:
        pv  = raw[:4].zfill(5)
        num = raw[4:12]
    elif n >= 13:
        pv  = raw[:5]
        num = raw[5:13]
    else:
        pv  = raw[:max(0, n - 8)].zfill(5)
        num = raw[max(0, n - 8):].zfill(8)
    return pv[:5], num[:8]


def _extract_invoice_number(text: str) -> OcrField:
    """
    Official ARCA format (RG 1492/2003 + Oct-2018 extension):
      Punto de venta:  4 digits (legacy) or 5 digits (current)
      Nro comprobante: 8 digits
      Printed as:      XXXXX-XXXXXXXX

    CAE numbers (14 digits, labelled C.A.E. / CAE) are explicitly skipped.
    Each pass runs on both the original text and a digit-normalized copy so
    OCR letter substitutions (O→0, l→1, B→8, etc.) don't prevent a match.
    """
    def _mask_cae(m: re.Match) -> str:
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

    # Normalized copy: replaces OCR look-alike letters with digits only where
    # they appear in digit runs.  Word-level patterns (labels) still run on
    # the original `clean` so INVOICE_LABELS keeps matching correctly.
    clean_norm = _normalize_ocr_digits(clean)

    # Pass 0 — split "P.V. Nro." + "Nro T." layout (Makro & fiscal-controller
    # tickets).  Both parts are explicitly labelled, so this is high-confidence
    # and runs first.  "P.V. Nro.:1776  Nro T. 00119564" → 01776-00119564.
    m = P.INVOICE_PV_NROT.search(clean_norm) or P.INVOICE_PV_NROT.search(clean)
    if m:
        pv  = m.group(1).zfill(5)[:5]
        num = m.group(2).zfill(8)[:8]
        return OcrField(value=f"{pv}-{num}", confidence=0.92)

    # Pass 1 — joined XXXXX-XXXXXXXX token
    m = P.INVOICE_JOINED.search(clean_norm) or P.INVOICE_JOINED.search(clean)
    if m:
        pv = m.group(1).zfill(5)
        return OcrField(value=f"{pv}-{m.group(2)}", confidence=0.93)

    # Pass 2 — spaced pair XXXXX  XXXXXXXX
    m = P.INVOICE_SPACED.search(clean_norm) or P.INVOICE_SPACED.search(clean)
    if m:
        pv = m.group(1).zfill(5)
        return OcrField(value=f"{pv}-{m.group(2)}", confidence=0.80)

    # Pass 3 — label-guided (skip if label is part of "C.A.E." reference)
    # If the label yields only an 8-digit number (POS unknown), defer — Pass 4 may
    # find a complete 12-digit concatenated number that gives us the full reference.
    label_fallback: Optional[OcrField] = None
    for label_m in P.INVOICE_LABELS.finditer(clean):
        preceding = clean[max(0, label_m.start() - 10):label_m.start()]
        if re.search(r"C\.?A\.?E", preceding, re.IGNORECASE):
            continue
        after_raw  = clean[label_m.end():label_m.end() + 100]
        after_norm = _normalize_ocr_digits(after_raw)
        # Digit extraction on the normalized slice catches O/l/B substitutions
        nums = re.findall(r"\d+", after_norm) or re.findall(r"\d+", after_raw)
        # POS + NUM as two separate tokens (highest confidence in label path)
        if len(nums) >= 2 and len(nums[0]) >= 1 and len(nums[1]) >= 4:
            pv  = nums[0].zfill(5)[:5]
            num = nums[1].zfill(8)[:8]
            return OcrField(value=f"{pv}-{num}", confidence=0.68)
        # Single 12-13 digit token (leading zero dropped, POS+NUM concatenated)
        if nums and len(nums[0]) >= 12:
            pv, num = _split_invoice_digits(nums[0])
            return OcrField(value=f"{pv}-{num}", confidence=0.62)
        # Single 8-digit token — POS unknown; save as fallback, keep scanning
        if nums and len(nums[0]) >= 8 and label_fallback is None:
            pv, num = _split_invoice_digits(nums[0])
            label_fallback = OcrField(value=f"{pv}-{num}", confidence=0.45)

    # Pass 4 — concatenated 12-13 digit run near comprobante context (garbled label).
    # Covers "NRO." → "ARO," or other label garbling where Pass 3 found nothing complete.
    for source in (clean_norm, clean):
        for m in re.finditer(r"\b(\d{12,13})\b", source):
            ctx = source[max(0, m.start() - 60): m.end() + 60]
            if not re.search(r"comp|nro|aro|tique|ticket|factura|cajero|tienda|caja",
                             ctx, re.IGNORECASE):
                continue
            pv, num = _split_invoice_digits(m.group(1))
            return OcrField(value=f"{pv}-{num}", confidence=0.60)

    if label_fallback:
        return label_fallback

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
    # OCR often splits the cents off with a stray space ("113370. 21" / "113370 ,21"),
    # which hides the amount from the regex.  Collapse those before searching so a
    # labelled total isn't demoted to the positional fallback.
    text = re.sub(r"(\d)\s*([.,])\s*(\d{2})(?!\d)", r"\1\2\3", text)

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


def _ocr_confirms_amount(total: str, raw_text: str) -> bool:
    """
    Return True if `total` (e.g. "90194.09") appears among the amounts OCR read
    off the receipt.  Used to validate the ÷100 cents-encoding correction that
    barcode._parse_arca_qr applies to bare-integer ARCA `importe` values.

    We scan every amount OCR found (rather than the single best total guess)
    because the printed TOTAL line is often garbled while the same figure also
    appears cleanly elsewhere (e.g. a payment-method line).  Comparison is on
    digits only, so "90194,09" / "90.194,09" / "90194.09" all match.
    """
    target_digits = re.sub(r"\D", "", total)
    if not target_digits:
        return False
    for raw in P.AMOUNT.findall(raw_text):
        if re.sub(r"\D", "", P.normalize_amount(raw)) == target_digits:
            return True
    return False


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

    # ── Barcode / QR scan (runs first, fully local, no network) ──────────────
    from .barcode import scan as barcode_scan
    bc = barcode_scan(img)

    raw_text = _run_ocr(img)

    # ── Non-ARCA QR: auto-fetch and extract invoice fields from the URL ───────
    qr_fields: dict[str, OcrField] = {}
    bc_qr_url = bc.other_qr_url if bc else None
    if bc_qr_url:
        from .qr_extractor import fetch_and_extract as _fetch_qr
        qr_fields = _fetch_qr(bc_qr_url)

    # ── Field extraction: learning store > ARCA barcode > QR fetch > OCR ─────
    bc_date    = bc.invoice_date   if bc else None
    bc_inv     = bc.invoice_number if bc else None
    bc_cuit    = bc.cuit           if bc else None
    bc_total   = bc.total_amount   if bc else None
    # ARCA QR gives all fields at 1.0; CODE128 gives date+number at 0.92
    bc_conf    = 1.0 if (bc and bc.source == "arca_qr") else 0.92

    # barcode._parse_arca_qr re-scales bare-integer `importe` values ÷100 to
    # undo the cents-encoding bug (e.g. 9019409 → 90194.09).  That inference is
    # ambiguous from the QR alone, so only trust it at full confidence when OCR
    # independently shows the same amount; otherwise flag the total for review
    # (confidence below threshold) so the user verifies the scale.
    bc_total_conf = bc_conf
    if bc and getattr(bc, "total_inferred", False) and bc_total:
        if not _ocr_confirms_amount(bc_total, raw_text):
            bc_total_conf = 0.5

    # CLAHE fallback text is computed lazily (one extra Tesseract pass) only the
    # first time a field comes back below threshold, so clean / QR receipts never
    # pay for it.  None = not yet computed; "" = computed and empty.
    clahe_cache: dict[str, Optional[str]] = {"text": None}

    def _clahe_text() -> str:
        if clahe_cache["text"] is None:
            clahe_cache["text"] = _run_ocr_clahe(img)
        return clahe_cache["text"]

    def _field(name: str, ocr_fn, bc_value: Optional[str],
               bc_conf: float) -> OcrField:
        if name in known:
            return OcrField(value=known[name], confidence=1.0)
        if bc_value:
            return OcrField(value=bc_value, confidence=bc_conf)
        ocr_result = ocr_fn(raw_text)
        # Fallback: when the plain pass is below threshold, try the CLAHE pass
        # and keep it only if it's strictly better.  Non-destructive — fields
        # the main pass already reads well are never reconsidered.
        if ocr_result.confidence < CONFIDENCE_THRESHOLD:
            alt = ocr_fn(_clahe_text())
            if alt.confidence > ocr_result.confidence:
                ocr_result = alt
        # Prefer QR-fetch result when it has higher confidence than plain OCR
        qr_result = qr_fields.get(name)
        if qr_result and qr_result.confidence > ocr_result.confidence:
            return qr_result
        return ocr_result

    cuit_field  = _field("cuit",           _extract_cuit,            bc_cuit,  bc_conf)
    date_field  = _field("invoice_date",   _extract_date,            bc_date,  bc_conf)
    inv_field   = _field("invoice_number", _extract_invoice_number,  bc_inv,   bc_conf)
    total_field = _field("total_amount",   _extract_total,           bc_total, bc_total_conf)

    unrecognized = [
        name for name, field in [
            ("cuit",           cuit_field),
            ("invoice_date",   date_field),
            ("invoice_number", inv_field),
            ("total_amount",   total_field),
        ]
        if field.confidence < CONFIDENCE_THRESHOLD
    ]

    # Determine barcode source: qr_fetch counts only if it actually improved a field
    bc_source = bc.source if bc else None
    if qr_fields and bc_source != "arca_qr":
        bc_source = "qr_fetch"

    return OcrResult(
        cuit=cuit_field,
        invoice_date=date_field,
        invoice_number=inv_field,
        total_amount=total_field,
        raw_text=raw_text,
        image_hash=image_hash,
        unrecognized_fields=unrecognized,
        barcode_source=bc_source,
        qr_url=bc_qr_url,
    )


# ── Multi-image entry point ───────────────────────────────────────────────────

def _merge_results(results: list[OcrResult]) -> OcrResult:
    """Merge OCR results from multiple images: best confidence per field wins."""
    # ARCA QR has perfect confidence — return it immediately
    for r in results:
        if r.barcode_source == "arca_qr":
            return r

    best = results[0]
    for r in results[1:]:
        for attr in ("cuit", "invoice_date", "invoice_number", "total_amount"):
            if getattr(r, attr).confidence > getattr(best, attr).confidence:
                best = best.model_copy(update={attr: getattr(r, attr)})

    merged_unrecognized = [
        name for name, f in [
            ("cuit",           best.cuit),
            ("invoice_date",   best.invoice_date),
            ("invoice_number", best.invoice_number),
            ("total_amount",   best.total_amount),
        ]
        if f.confidence < CONFIDENCE_THRESHOLD
    ]
    return best.model_copy(update={
        "raw_text": "\n\n".join(r.raw_text for r in results),
        "unrecognized_fields": merged_unrecognized,
        "barcode_source": next((r.barcode_source for r in results if r.barcode_source), None),
        "qr_url": next((r.qr_url for r in results if r.qr_url), None),
    })


def extract_multi(images_bytes: list[bytes], db: Optional[Session] = None) -> OcrResult:
    """Run OCR on each image independently and merge results field by field."""
    results = [extract(b, db=db) for b in images_bytes]
    if len(results) == 1:
        return results[0]
    return _merge_results(results)
