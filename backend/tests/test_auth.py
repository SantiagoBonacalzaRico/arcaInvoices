"""
Auth + multi-tenancy acceptance tests: invite-only registration, email
verification gate, password login, and per-user data isolation.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import EmailVerification

ADMIN = {"identifier": "admin@example.com", "password": "adminpass123"}
SAMPLE_INVOICE = {
    "cuit": "33-69345023-9",
    "invoice_date": "2025-03-15",
    "invoice_number": "0001-00000123",
    "total_amount": "5000.00",
    "category": "Gastos Médicos y Paramédicos",
}


@pytest.fixture(scope="module")
def base():
    # Entering the context manager runs the lifespan: create_all + migrations
    # (which seeds the admin) + scheduler.
    with TestClient(app) as c:
        yield c


def _client():
    """A fresh client with its own cookie jar (tables already created)."""
    return TestClient(app)


def _login(client, creds):
    r = client.post("/api/auth/login", json=creds)
    assert r.status_code == 200, r.text
    return r


def _verify_token_for(user_email):
    db = SessionLocal()
    try:
        from app.models import User
        user = db.query(User).filter(User.email == user_email).first()
        rec = (
            db.query(EmailVerification)
            .filter(EmailVerification.user_id == user.id)
            .first()
        )
        return rec.token
    finally:
        db.close()


def test_unauthenticated_is_rejected(base):
    assert _client().get("/api/invoices").status_code == 401


def test_admin_login_and_me(base):
    c = _client()
    _login(c, ADMIN)
    me = c.get("/api/auth/me").json()
    assert me["is_admin"] is True
    assert me["is_verified"] is True


def test_invite_only_registration_and_isolation(base):
    admin = _client()
    _login(admin, ADMIN)

    # Registration without a valid invite is rejected.
    bad = admin.post("/api/auth/register", json={
        "invite_code": "nope", "email": "u2@example.com",
        "username": "user2", "password": "user2pass123",
    })
    assert bad.status_code == 400

    # Admin mints an invite.
    inv = admin.post("/api/auth/invites", json={"email": "u2@example.com"})
    assert inv.status_code == 201, inv.text
    code = inv.json()["code"]

    # Register user2 with the invite → created but unverified.
    reg = _client().post("/api/auth/register", json={
        "invite_code": code, "email": "u2@example.com",
        "username": "user2", "password": "user2pass123",
    })
    assert reg.status_code == 201, reg.text

    # Unverified user cannot log in.
    u2 = _client()
    assert u2.post("/api/auth/login", json={
        "identifier": "user2", "password": "user2pass123"
    }).status_code == 403

    # Verify e-mail, then login succeeds.
    token = _verify_token_for("u2@example.com")
    assert _client().get(f"/api/auth/verify?token={token}").status_code == 200
    _login(u2, {"identifier": "user2", "password": "user2pass123"})

    # The invite cannot be reused.
    assert _client().post("/api/auth/register", json={
        "invite_code": code, "email": "u3@example.com",
        "username": "user3", "password": "user3pass123",
    }).status_code == 400

    # Isolation: admin creates an invoice; user2 must not see it.
    admin_inv = admin.post("/api/invoices", json=SAMPLE_INVOICE)
    assert admin_inv.status_code == 201, admin_inv.text
    assert len(u2.get("/api/invoices").json()) == 0

    # user2 creates their own invoice; admin must not see it.
    u2_inv = u2.post("/api/invoices", json={**SAMPLE_INVOICE, "invoice_number": "0001-00000999"})
    assert u2_inv.status_code == 201, u2_inv.text
    admin_list = admin.get("/api/invoices").json()
    assert all(i["invoice_number"] != "0001-00000999" for i in admin_list)
    assert len(u2.get("/api/invoices").json()) == 1


def test_non_admin_cannot_mint_invites(base):
    u2 = _client()
    _login(u2, {"identifier": "user2", "password": "user2pass123"})
    assert u2.post("/api/auth/invites", json={}).status_code == 403
