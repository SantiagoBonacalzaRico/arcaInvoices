"""
Unit tests for OCR field extraction — no images needed.
Tests the regex pattern logic directly.
"""
import pytest
from app.ocr.patterns import (
    CUIT_DASHED, CUIT_PLAIN, DATE_DMY_SLASH, INVOICE_JOINED,
    INVOICE_SPACED, TOTAL_LABEL, AMOUNT,
    normalize_cuit, normalize_amount,
)
from app.ocr.extractor import (
    _extract_cuit, _extract_date, _extract_invoice_number, _extract_total,
    _valid_cuit_digits, CONFIDENCE_THRESHOLD,
)


# ── CUIT ─────────────────────────────────────────────────────────────────────

VALID_CUIT = "33-69345023-9"   # AFIP's own CUIT — verifiable
VALID_CUIT_PLAIN = "33693450239"


def test_cuit_dashed():
    f = _extract_cuit(f"CUIT del emisor: {VALID_CUIT}")
    assert f.value == VALID_CUIT
    assert f.confidence >= CONFIDENCE_THRESHOLD


def test_cuit_plain():
    f = _extract_cuit(VALID_CUIT_PLAIN)
    assert f.value == VALID_CUIT
    assert f.confidence >= CONFIDENCE_THRESHOLD


def test_cuit_invalid_returns_low_confidence():
    f = _extract_cuit("99-00000000-0")
    # Either no match or low confidence (checksum fails)
    assert f.value is None or f.confidence < CONFIDENCE_THRESHOLD


# ── Date ─────────────────────────────────────────────────────────────────────

def test_date_slash():
    f = _extract_date("Fecha: 15/03/2025")
    assert f.value == "2025-03-15"
    assert f.confidence >= CONFIDENCE_THRESHOLD


def test_date_dash():
    f = _extract_date("emitida el 01-12-2024")
    assert f.value == "2024-12-01"


def test_date_dot():
    f = _extract_date("Fecha 07.07.2023")
    assert f.value == "2023-07-07"


def test_date_invalid_returns_none():
    f = _extract_date("sin fecha aqui")
    assert f.value is None
    assert f.confidence == 0.0


# ── Invoice number ───────────────────────────────────────────────────────────

def test_invoice_joined():
    f = _extract_invoice_number("Factura N° 0001-00012345")
    assert f.value == "0001-00012345"
    assert f.confidence >= 0.9


def test_invoice_spaced():
    f = _extract_invoice_number("Comprobante 0002  00000099")
    assert f.value == "0002-00000099"
    assert f.confidence >= CONFIDENCE_THRESHOLD


def test_invoice_label_guided():
    text = "Comprobante Nro\n0003\n00000777"
    f = _extract_invoice_number(text)
    assert f.value is not None
    assert "0003" in f.value


def test_invoice_not_found():
    f = _extract_invoice_number("sin numero de comprobante")
    assert f.value is None
    assert f.confidence == 0.0


# ── Total ─────────────────────────────────────────────────────────────────────

def test_total_labeled():
    f = _extract_total("Subtotal: $900,00\nTotal a Pagar: $1.080,00")
    assert f.value == "1080.00"
    assert f.confidence >= CONFIDENCE_THRESHOLD


def test_total_without_label():
    f = _extract_total("algún texto 2500.50")
    assert f.value is not None


# ── Normalize helpers ─────────────────────────────────────────────────────────

def test_normalize_cuit():
    assert normalize_cuit("30710992854") == "30-71099285-4"


def test_normalize_amount_ar():
    assert normalize_amount("1.234,56") == "1234.56"


def test_normalize_amount_us():
    assert normalize_amount("1,234.56") == "1234.56"
