"""
Invoice capture tests: duplicate detection on the (CUIT, comprobante) compound
key, scoped per user.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

ADMIN = {"identifier": "admin@example.com", "password": "adminpass123"}
INVOICE = {
    "cuit": "30-71044875-3",
    "invoice_date": "2025-04-10",
    "invoice_number": "0003-00004567",
    "total_amount": "8200.50",
    "category": "Otros",
}


@pytest.fixture(scope="module")
def base():
    # Entering the context manager runs the lifespan (create_all + migrations).
    with TestClient(app) as c:
        yield c


def _admin_client(base):
    c = TestClient(app)
    r = c.post("/api/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return c


def test_duplicate_invoice_is_rejected(base):
    c = _admin_client(base)

    first = c.post("/api/invoices", json=INVOICE)
    assert first.status_code == 201, first.text

    # Same CUIT + comprobante → rejected, even with different date/amount.
    dup = c.post("/api/invoices", json={
        **INVOICE, "invoice_date": "2025-05-01", "total_amount": "9999.99",
    })
    assert dup.status_code == 409, dup.text
    assert "ya fue cargada" in dup.json()["detail"]

    # The list still holds exactly one copy.
    rows = [i for i in c.get("/api/invoices").json()
            if i["invoice_number"] == INVOICE["invoice_number"]]
    assert len(rows) == 1


def test_same_number_different_cuit_is_allowed(base):
    c = _admin_client(base)

    a = c.post("/api/invoices", json={**INVOICE, "cuit": "20-12345678-6",
                                      "invoice_number": "0007-00000001"})
    assert a.status_code == 201, a.text

    # Same comprobante number but a different emisor (CUIT) is a distinct
    # invoice and must be accepted.
    b = c.post("/api/invoices", json={**INVOICE, "cuit": "27-87654321-4",
                                      "invoice_number": "0007-00000001"})
    assert b.status_code == 201, b.text
