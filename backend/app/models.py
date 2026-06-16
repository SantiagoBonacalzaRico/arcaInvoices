from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Date, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint,
)
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(256), nullable=False, unique=True, index=True)
    username = Column(String(80), nullable=False, unique=True, index=True)
    # Null for Google-only accounts (no local password set)
    password_hash = Column(String(256))
    # Google "sub" claim — stable per-account id; null for password-only accounts
    google_sub = Column(String(64), unique=True, index=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class InviteCode(Base):
    __tablename__ = "invite_codes"

    code = Column(String(64), primary_key=True)
    # Optional binding: if set, only this email may redeem the code
    email = Column(String(256))
    created_by = Column(Integer, ForeignKey("users.id"))
    used_by = Column(Integer, ForeignKey("users.id"))
    expires_at = Column(DateTime)
    used_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EmailVerification(Base):
    __tablename__ = "email_verifications"

    token = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    cuit = Column(String(13), nullable=False)
    invoice_date = Column(Date, nullable=False)
    invoice_number = Column(String(14), nullable=False)  # "0001-00012345"
    total_amount = Column(Numeric(12, 2), nullable=False)
    category = Column(String(80))
    image_path = Column(String(512))
    sync_status = Column(String(16), nullable=False, default="pending")
    synced_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    raw_ocr_text = Column(Text)

    __table_args__ = (
        Index("idx_invoices_date", "invoice_date"),
        Index("idx_invoices_cuit", "cuit"),
        Index("idx_invoices_category", "category"),
        Index("idx_invoices_status_date", "sync_status", "invoice_date"),
        Index("idx_invoices_user", "user_id"),
    )


class OcrCorrection(Base):
    __tablename__ = "ocr_corrections"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    field_name = Column(String(32), nullable=False)
    raw_snippet = Column(Text)
    correct_value = Column(Text, nullable=False)
    image_hash = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)
    status = Column(String(16))  # success | partial | failed
    invoices_synced = Column(Integer, default=0)
    error_message = Column(Text)


class CuitRegistry(Base):
    """Per-user cache of CUIT → razón social lookups."""
    __tablename__ = "cuit_registry"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    cuit = Column(String(13), nullable=False)
    razon_social = Column(String(256), nullable=False)
    source = Column(String(16), default="manual")  # manual | cuitalizer | padron
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "cuit", name="uq_cuit_registry_user_cuit"),
    )


class AppSettings(Base):
    """Per-user config row (one per user)."""
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, default=1)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)
    invoice_dir = Column(String(512), nullable=False, default="data/invoices")
    sync_day_of_month = Column(Integer, nullable=False, default=20)
    notification_days_before = Column(Integer, nullable=False, default=5)
    min_invoice_threshold = Column(Integer, nullable=False, default=3)
    notify_email = Column(Boolean, nullable=False, default=True)
    notify_sms = Column(Boolean, nullable=False, default=False)
    email_address = Column(String(256))
    phone_number = Column(String(32))
    smtp_host = Column(String(256), default="smtp.gmail.com")
    smtp_port = Column(Integer, default=587)
    smtp_user = Column(String(256))
    smtp_password = Column(String(256))  # stored encrypted
    afip_cuit = Column(String(13))
    afip_cert_path = Column(String(512))
    afip_key_path = Column(String(512))  # encrypted key path
    afip_production = Column(Boolean, nullable=False, default=False)
    # Wizard completion flags
    afip_setup_step = Column(Integer, default=0)  # 0-7 per checklist
    cuitalizer_api_key = Column(String(128))
