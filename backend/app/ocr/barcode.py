"""
Barcode and QR code scanner for Argentine fiscal documents.

Two code types handled:
─────────────────────────────────────────────────────────────────────────────
1. CODE128 (linear barcode)
   Standard format used by Argentine fiscal ticket printers:
     [YYYYMMDD][PPPP][NNNNNNNN]
     ───────── ──── ────────────
     date(8)   POS  comprobante
               (4)  number (8)
   Total: 20 digits.  Date gives us the transaction date; POS+number gives
   the comprobante in standard XXXXX-XXXXXXXX format.

2. ARCA QR code (2D QR)
   Mandated by RG 4291/2018 for all electronic invoices.  The QR encodes
   the URL:
     https://www.afip.gob.ar/fe/qr/?p=<BASE64_JSON>
   where the base64 decodes to:
     {
       "ver":       1,
       "fecha":     "YYYY-MM-DD",
       "cuit":      30708705639,
       "ptoVta":    662,
       "tipoCmp":   11,
       "nroCmp":    6100111,
       "importe":   119859.02,
       "moneda":    "PES",
       "ctz":       1,
       "tipoDocRec":99,
       "nroDocRec": 0
     }
   This gives us ALL four fields with 100% confidence.

Decoder pipeline (in order until a result is returned):
  1. zxingcpp  — more tolerant of perspective and blur than pyzbar
  2. pyzbar    — fast fallback, good on clean prints
  Both are tried on every preprocessing variant before moving to the next.

Preprocessing variants tried per candidate region:
  a. Greyscale as-is
  b. CLAHE-enhanced greyscale
  c. Unsharp-mask + Otsu binarization  (helps with faded / low-contrast QRs)
  d. Adaptive threshold                (helps with uneven lighting)
  All variants are also tried at 2× upscale for small QR regions.

No network requests are made — all decoding is done locally from the image pixels.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import date
from decimal import Decimal
from typing import Generator, Optional
from dataclasses import dataclass

import cv2
import numpy as np

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    _PYZBAR = True
except ImportError:
    _PYZBAR = False

try:
    import zxingcpp as _zx
    _ZXING = True
except ImportError:
    _ZXING = False


_ARCA_QR_HOSTS = {"www.afip.gob.ar", "serviciosweb.afip.gob.ar", "www.arca.gob.ar"}


@dataclass
class BarcodeResult:
    cuit:             Optional[str]    = None
    invoice_date:     Optional[str]    = None   # "YYYY-MM-DD"
    invoice_number:   Optional[str]    = None   # "XXXXX-XXXXXXXX"
    total_amount:     Optional[str]    = None   # "119859.02"
    source:           str              = ""     # "arca_qr" | "code128" | "other_qr" | ""
    raw_value:        str              = ""
    other_qr_url:     Optional[str]    = None   # non-ARCA QR URL found in image
    total_inferred:   bool             = False  # True if importe was re-scaled ÷100 (cents-encoding)


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_arca_qr(url: str) -> Optional[BarcodeResult]:
    """Parse an ARCA/AFIP QR URL and extract all invoice fields."""
    m = re.search(r"[?&]p=([A-Za-z0-9+/=_-]+)", url)
    if not m:
        return None
    try:
        raw = m.group(1).replace("-", "+").replace("_", "/")
        pad = len(raw) % 4
        if pad:
            raw += "=" * (4 - pad)
        payload = json.loads(base64.b64decode(raw).decode())
    except Exception:
        return None

    cuit_raw  = str(payload.get("cuit", ""))
    pto_vta   = int(payload.get("ptoVta", 0))
    nro_cmp   = int(payload.get("nroCmp", 0))
    importe   = payload.get("importe")
    fecha     = payload.get("fecha", "")

    if not cuit_raw or not pto_vta or not nro_cmp:
        return None

    cuit_fmt = (f"{cuit_raw[:2]}-{cuit_raw[2:10]}-{cuit_raw[10]}"
                if len(cuit_raw) == 11 else cuit_raw)
    inv_num  = f"{str(pto_vta).zfill(5)}-{str(nro_cmp).zfill(8)}"

    # ARCA spec defines `importe` as decimal(13,2).  Compliant generators encode
    # it with the decimal point (JSON float, e.g. 90194.09).  Some POS systems
    # (Makro, Carrefour…) instead emit a bare integer with the point dropped
    # (e.g. 9019409 for $90,194.09).  A bare integer whose last two digits are
    # not "00" is therefore almost certainly cents-encoded → re-scale ÷100.
    # Round integers (…00) are left as pesos: dividing them is more likely to
    # corrupt a genuine whole-peso total than to fix one.
    total_str: Optional[str] = None
    total_inferred = False
    if importe is not None:
        if isinstance(importe, int) and not isinstance(importe, bool) and importe % 100 != 0:
            total_str = f"{Decimal(importe) / 100:.2f}"
            total_inferred = True
        else:
            total_str = f"{Decimal(str(importe)):.2f}"

    return BarcodeResult(
        cuit           = cuit_fmt,
        invoice_date   = fecha,
        invoice_number = inv_num,
        total_amount   = total_str,
        source         = "arca_qr",
        raw_value      = url,
        total_inferred = total_inferred,
    )


def _parse_code128(data: str) -> Optional[BarcodeResult]:
    """Extract date and comprobante from a CODE128 fiscal receipt barcode."""
    digits = re.sub(r"\D", "", data)
    if len(digits) < 20:
        return None

    yr, mo, dd = int(digits[0:4]), int(digits[4:6]), int(digits[6:8])
    try:
        parsed_date = date(yr, mo, dd)
        if not (2000 <= yr <= 2099):
            return None
    except ValueError:
        return None

    pos = digits[8:12]
    num = digits[12:20]
    return BarcodeResult(
        invoice_date   = str(parsed_date),
        invoice_number = f"{pos.zfill(5)}-{num.zfill(8)}",
        source         = "code128",
        raw_value      = data,
    )


# ── Low-level decode ──────────────────────────────────────────────────────────

def _decode_raw(gray: np.ndarray) -> list[tuple[str, str]]:
    """
    Run zxingcpp then pyzbar on *gray* (single-channel uint8).
    Returns list of (type_str, text) for every symbol found.
    """
    results: list[tuple[str, str]] = []

    if _ZXING:
        for bz in (_zx.Binarizer.LocalAverage, _zx.Binarizer.GlobalHistogram):
            found = _zx.read_barcodes(
                gray,
                try_rotate=True,
                try_invert=True,
                try_downscale=True,
                binarizer=bz,
            )
            for r in found:
                if r.text:
                    results.append((r.format.name, r.text))
            if results:
                return results

    if _PYZBAR:
        from PIL import Image as _PIL
        codes = pyzbar_decode(_PIL.fromarray(gray))
        for c in codes:
            try:
                text = c.data.decode("utf-8", errors="replace")
            except Exception:
                continue
            results.append((c.type, text))

    return results


# ── Preprocessing variants ────────────────────────────────────────────────────

def _preprocess_variants(gray: np.ndarray) -> Generator[np.ndarray, None, None]:
    """
    Yield a sequence of increasingly aggressive preprocessed versions of *gray*.
    Stops after the first variant that yields a decode (caller handles that).
    """
    yield gray                                        # 1. raw greyscale

    # 2. CLAHE — corrects uneven lighting across the image
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    yield clahe.apply(gray)

    # 3. Unsharp mask + Otsu — sharpens blurry prints
    blur = cv2.GaussianBlur(gray, (0, 0), 2.0)
    usm  = cv2.addWeighted(gray, 2.5, blur, -1.5, 0)
    _, bw = cv2.threshold(usm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield bw

    # 4. Adaptive threshold — handles gradients / shadows on receipt paper
    clahe_g = clahe.apply(gray)
    yield cv2.adaptiveThreshold(
        clahe_g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 10
    )


def _scan_gray(gray: np.ndarray) -> list[tuple[str, str]]:
    """Try all preprocessing variants on *gray*; return first non-empty decode."""
    for prep in _preprocess_variants(gray):
        hits = _decode_raw(prep)
        if hits:
            return hits
        # Also try 2× upscale of each variant (helps small QR codes)
        up = cv2.resize(prep, (prep.shape[1] * 2, prep.shape[0] * 2),
                        interpolation=cv2.INTER_LANCZOS4)
        hits = _decode_raw(up)
        if hits:
            return hits
    return []


# ── Region candidates ─────────────────────────────────────────────────────────

def _region_candidates(img: np.ndarray) -> Generator[np.ndarray, None, None]:
    """
    Yield candidate BGR regions in order of likelihood.
    Scanning the full image first then quadrants catches QR codes that straddle
    the centre; scanning individual quadrants at 2× gives better resolution on
    small codes buried in a corner.
    """
    h, w = img.shape[:2]
    yield img                                             # full image
    yield img[h // 2:, :]                                # bottom half
    yield img[:h // 2, :]                                # top half
    yield img[:, w // 2:]                                # right half
    yield img[:, :w // 2]                                # left half
    # Quadrants
    yield img[h // 2:, w // 2:]                          # bottom-right
    yield img[h // 2:, :w // 2]                          # bottom-left
    yield img[:h // 2, w // 2:]                          # top-right
    yield img[:h // 2, :w // 2]                          # top-left


# ── Main entry point ──────────────────────────────────────────────────────────

def scan(img: np.ndarray) -> Optional[BarcodeResult]:
    """
    Scan all barcodes/QR codes in the image.
    Preference: ARCA QR (all fields) > CODE128 (date + comprobante) > other QR URL.
    Returns the richest result found, or None.
    """
    if not _PYZBAR and not _ZXING:
        return None

    best: Optional[BarcodeResult] = None
    other_qr: Optional[str] = None

    def _process_hits(hits: list[tuple[str, str]]) -> Optional[BarcodeResult]:
        """Process a list of (type, text) hits; return immediately on ARCA QR."""
        nonlocal best, other_qr
        local_best: Optional[BarcodeResult] = None

        for sym_type, text in hits:
            is_qr = "QR" in sym_type.upper()

            # ARCA QR — highest priority, return immediately
            if is_qr and any(h in text for h in _ARCA_QR_HOSTS):
                result = _parse_arca_qr(text)
                if result:
                    return result

            # Non-ARCA QR with HTTP URL — capture for redirect offer
            if is_qr and other_qr is None and text.startswith(("http://", "https://")):
                other_qr = text

            # CODE128 fiscal barcode
            if "CODE128" in sym_type.upper() or "CODE_128" in sym_type.upper():
                result = _parse_code128(text)
                if result and local_best is None:
                    local_best = result

        if local_best and best is None:
            best = local_best
        return None

    # Try each region candidate (full image, halves, quadrants)
    for region in _region_candidates(img):
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        hits = _scan_gray(gray)
        if hits:
            result = _process_hits(hits)
            if result:  # ARCA QR found
                return result

    # Return best CODE128 result (with other_qr attached if found)
    if best:
        best.other_qr_url = other_qr
        return best

    if other_qr:
        return BarcodeResult(source="other_qr", raw_value=other_qr, other_qr_url=other_qr)

    return None
