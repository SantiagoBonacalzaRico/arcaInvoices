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

No network requests are made — all decoding is done locally from the
image pixels.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import date
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass, field as dc_field

import cv2
import numpy as np

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    _PYZBAR = True
except ImportError:
    _PYZBAR = False


_ARCA_QR_HOSTS = {"www.afip.gob.ar", "serviciosweb.afip.gob.ar", "www.arca.gob.ar"}


@dataclass
class BarcodeResult:
    cuit:             Optional[str]    = None
    invoice_date:     Optional[str]    = None   # "YYYY-MM-DD"
    invoice_number:   Optional[str]    = None   # "XXXXX-XXXXXXXX"
    total_amount:     Optional[str]    = None   # "119859.02"
    source:           str              = ""     # "arca_qr" | "code128" | ""
    raw_value:        str              = ""


def _parse_arca_qr(url: str) -> Optional[BarcodeResult]:
    """
    Parse an ARCA/AFIP QR URL and extract all invoice fields from its
    base64-encoded JSON payload.
    """
    m = re.search(r"[?&]p=([A-Za-z0-9+/=_-]+)", url)
    if not m:
        return None
    try:
        # URL-safe or standard base64
        raw = m.group(1).replace("-", "+").replace("_", "/")
        # Add padding if needed
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
    fecha     = payload.get("fecha", "")   # "YYYY-MM-DD"

    if not cuit_raw or not pto_vta or not nro_cmp:
        return None

    cuit_fmt = f"{cuit_raw[:2]}-{cuit_raw[2:10]}-{cuit_raw[10]}" if len(cuit_raw) == 11 else cuit_raw
    inv_num  = f"{str(pto_vta).zfill(5)}-{str(nro_cmp).zfill(8)}"

    return BarcodeResult(
        cuit           = cuit_fmt,
        invoice_date   = fecha,
        invoice_number = inv_num,
        total_amount   = f"{Decimal(str(importe)):.2f}" if importe is not None else None,
        source         = "arca_qr",
        raw_value      = url,
    )


def _parse_code128(data: str) -> Optional[BarcodeResult]:
    """
    Extract date and comprobante from a CODE128 fiscal receipt barcode.
    Expected format: YYYYMMDD (8 digits) + POS (4 digits) + NUMBER (8 digits).
    """
    digits = re.sub(r"\D", "", data)
    if len(digits) < 20:
        return None

    # First 8 digits: YYYYMMDD
    yr, mo, dd = int(digits[0:4]), int(digits[4:6]), int(digits[6:8])
    try:
        parsed_date = date(yr, mo, dd)
        if not (2000 <= yr <= 2099):
            return None
    except ValueError:
        return None

    # Digits 9-12: POS (4 digits); digits 13-20: number (8 digits)
    pos = digits[8:12]
    num = digits[12:20]
    inv_num = f"{pos.zfill(5)}-{num.zfill(8)}"

    return BarcodeResult(
        invoice_date   = str(parsed_date),
        invoice_number = inv_num,
        source         = "code128",
        raw_value      = data,
    )


def scan(img: np.ndarray) -> Optional[BarcodeResult]:
    """
    Scan all barcodes/QR codes in the image.
    Preference: ARCA QR (all fields) > CODE128 (date + comprobante).
    Returns the richest result found, or None.
    """
    if not _PYZBAR:
        return None

    from pyzbar.pyzbar import decode as pyzbar_decode, ZBarSymbol

    from PIL import Image as _PILImage
    pil_img = _PILImage.fromarray(img)

    # Try colour image first, then greyscale (helps with some prints)
    for attempt in [pil_img, pil_img.convert("L")]:
        codes = pyzbar_decode(attempt)
        best: Optional[BarcodeResult] = None

        for code in codes:
            try:
                text = code.data.decode("utf-8", errors="replace")
            except Exception:
                continue

            # ARCA/AFIP QR
            if code.type == "QRCODE" and any(h in text for h in _ARCA_QR_HOSTS):
                result = _parse_arca_qr(text)
                if result:
                    return result   # Best possible — return immediately

            # CODE128 fiscal barcode
            if code.type == "CODE128":
                result = _parse_code128(text)
                if result and (best is None):
                    best = result

        if best:
            return best

    return None
