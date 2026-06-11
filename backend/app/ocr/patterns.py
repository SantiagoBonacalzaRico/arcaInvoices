from __future__ import annotations
import re

# ── CUIT ─────────────────────────────────────────────────────────────────────
# Dashed form:  20-12345678-9
CUIT_DASHED = re.compile(r"\b(\d{2})[.\-–](\d{8})[.\-–](\d)\b")
# Plain 11 digits (no separators) — validated by checksum in extractor
CUIT_PLAIN = re.compile(r"\b(\d{11})\b")
# Labelled form: "CUIT:", "C.U.I.T.:", "Cuit Emisor:", "CUIT: 30-70870563-9"
CUIT_LABEL = re.compile(
    r"C\.?U\.?I\.?T\.?\s*(?:Emisor|Nro\.?|N[°º]\.?)?\s*:?\s*"
    r"(\d{2}[\.\-–]?\d{8}[\.\-–]?\d|\d{11})",
    re.IGNORECASE,
)

# ── Date ─────────────────────────────────────────────────────────────────────
# DD/MM/YYYY  DD-MM-YYYY  DD.MM.YYYY — most common on Argentine comprobantes
DATE_DMY_SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
DATE_DMY_DASH  = re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b")
DATE_DMY_DOT   = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
# Date+time: DD/MM/YYYY HH:MM or DD/MM/YYYY HH:MM:SS (transaction date on tickets)
DATE_WITH_TIME = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\s+\d{1,2}:\d{2}")
# Contexts that indicate a CAE expiry — NOT the transaction date
# V/Y confusion is common in OCR (Vto. → Yto.)
DATE_VTO_CONTEXT = re.compile(r"[VvYy]to\.?|[Vv]enc(?:imiento)?\.?", re.IGNORECASE)
# Date labels that appear before the date value
DATE_LABEL = re.compile(
    r"(?:Fecha\s*(?:de\s*(?:Emisi[oó]n|Comprobante))?|Date)\s*[:\s]+",
    re.IGNORECASE,
)

# ── Invoice / Comprobante number ──────────────────────────────────────────────
# Official ARCA format (RG 1492/2003 + 2018 extension):
#   Punto de venta: 4 digits (original) or 5 digits (from Oct 2018) → \d{4,5}
#   Número de comprobante: 8 digits                                  → \d{8}
#   Printed as: XXXXX-XXXXXXXX  or  XXXX-XXXXXXXX
INVOICE_JOINED = re.compile(r"\b(\d{4,5})[–\-](\d{8})\b")
INVOICE_SPACED = re.compile(r"\b(\d{4,5})\s{1,3}(\d{8})\b")

# Labels that precede the comprobante number on facturas and tickets
INVOICE_LABELS = re.compile(
    r"(?:nro\.?\s*comp(?:robante)?|"   # NRO.COMP: or NRO.COMPROBANTE: — most specific first
    r"n[°º]\.?\s*comp(?:robante)?|"
    r"comprobante\s*(?:nro|n[uú]mero|n[°º])?|"
    r"n[uú]mero\s*(?:de\s*)?comprobante|"
    r"factura\s*(?:nro|n[°º])?|"
    r"tique\s*(?:nro|n[°º])?|"
    r"ticket\s*(?:nro|n[°º])?|"
    r"recibo\s*(?:nro|n[°º])?|"
    r"n[°º]\.?\s*(?:comp)?)",
    re.IGNORECASE,
)

# ── Monetary amounts ──────────────────────────────────────────────────────────
# Argentine format: 1.234,56  (period = thousands, comma = decimal)
# International:   1,234.56   (comma = thousands, period = decimal)
# Simple:          1234.56 / 1234,56
AMOUNT = re.compile(r"\$?\s*(\d{1,3}(?:[.,]\d{3})*[.,]\d{2}|\d+[.,]\d{2})")

# Total labels — extended to cover ticket formats too
TOTAL_LABEL = re.compile(
    r"(?:total\s*(?:a\s*pagar|general|comprobante|factura)?|"
    r"importe\s*total|monto\s*total|"
    r"transferencia|"          # tickets: "TRANSFERENCIA $119.859,02"
    r"efectivo|"               # tickets: "EFECTIVO $xx.xxx,xx"
    r"total)",
    re.IGNORECASE,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_cuit(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11:
        return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"
    return raw


def normalize_amount(raw: str) -> str:
    """Convert '1.234,56' or '1,234.56' or '1234,56' to '1234.56'."""
    cleaned = raw.strip().lstrip("$").strip()
    if not cleaned:
        return ""
    # Argentine format: last separator is comma followed by exactly 2 digits
    if re.search(r",\d{2}$", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    return cleaned
