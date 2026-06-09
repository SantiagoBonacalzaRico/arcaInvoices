from __future__ import annotations
import re

# CUIT: "20-12345678-9" or "20123456789" (11 digits)
CUIT_DASHED = re.compile(r"\b(\d{2})-(\d{8})-(\d)\b")
CUIT_PLAIN = re.compile(r"\b(\d{11})\b")

# Date formats common in Argentine invoices
DATE_DMY_SLASH = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
DATE_DMY_DASH = re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b")
DATE_DMY_DOT = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")

# Invoice number: "0001-00012345" or "0001 00012345"
INVOICE_JOINED = re.compile(r"\b(\d{4})[–\-](\d{8})\b")
INVOICE_SPACED = re.compile(r"\b(\d{4})\s+(\d{8})\b")

# Labels that appear on the line before the invoice number
INVOICE_LABELS = re.compile(
    r"(?:comprobante\s+(?:nro|n[uú]mero)|n[uú]mero\s+(?:de\s+)?comprobante"
    r"|factura|n[°º])",
    re.IGNORECASE,
)

# Monetary total — look for label then amount
TOTAL_LABEL = re.compile(
    r"(?:total\s+(?:a\s+pagar|general|factura)?|importe\s+total"
    r"|monto\s+total|total)",
    re.IGNORECASE,
)
AMOUNT = re.compile(r"[\$\s]*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2}))")


def normalize_cuit(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11:
        return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"
    return raw


def normalize_amount(raw: str) -> str:
    """Convert '1.234,56' or '1,234.56' to '1234.56'."""
    cleaned = raw.strip().lstrip("$").strip()
    # Detect Argentine format (last separator is comma)
    if re.search(r",\d{2}$", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    return cleaned
