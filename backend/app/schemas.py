from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    invite_code: str = Field(..., min_length=1)
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    # email or username
    identifier: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    is_admin: bool
    is_verified: bool

    model_config = {"from_attributes": True}


class AuthOut(UserOut):
    # Same user fields the web reads, plus a bearer token for native apps
    # (web ignores this and keeps using the HTTP-only cookie).
    access_token: Optional[str] = None


class InviteCreateRequest(BaseModel):
    email: Optional[EmailStr] = None
    expires_days: int = Field(7, ge=1, le=365)


class InviteOut(BaseModel):
    code: str
    email: Optional[str] = None
    expires_at: Optional[datetime] = None
    url: str


# ── Invoice ──────────────────────────────────────────────────────────────────

class InvoiceBase(BaseModel):
    cuit: str = Field(..., pattern=r"^\d{2}-\d{8}-\d$")
    invoice_date: date
    invoice_number: str = Field(..., pattern=r"^\d{4,5}-\d{8}$")
    total_amount: Decimal = Field(..., gt=0)
    category: Optional[str] = None
    image_path: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    raw_ocr_text: Optional[str] = None


class InvoiceUpdate(BaseModel):
    cuit: Optional[str] = Field(None, pattern=r"^\d{2}-\d{8}-\d$")
    invoice_date: Optional[date] = None
    invoice_number: Optional[str] = Field(None, pattern=r"^\d{4,5}-\d{8}$")
    total_amount: Optional[Decimal] = Field(None, gt=0)
    category: Optional[str] = None


class InvoiceOut(InvoiceBase):
    id: int
    sync_status: str
    synced_at: Optional[datetime] = None
    created_at: datetime
    razon_social: Optional[str] = None  # emisor name, from cuit_registry cache

    model_config = {"from_attributes": True}


class SyncStatusUpdate(BaseModel):
    sync_status: Literal["synced", "pending"]


# ── OCR ───────────────────────────────────────────────────────────────────────

class OcrField(BaseModel):
    value: Optional[str]
    confidence: float = Field(ge=0.0, le=1.0)


class OcrResult(BaseModel):
    cuit: OcrField
    invoice_date: OcrField
    invoice_number: OcrField
    total_amount: OcrField
    raw_text: str
    image_hash: str
    unrecognized_fields: list[str]
    barcode_source: Optional[str] = None  # "arca_qr" | "code128" | "other_qr" | None
    qr_url: Optional[str] = None           # non-ARCA QR URL found in image (redirect offer)


class OcrCorrection(BaseModel):
    invoice_id: Optional[int] = None
    field_name: str
    raw_snippet: Optional[str] = None
    correct_value: str
    image_hash: Optional[str] = None


# ── Sync ──────────────────────────────────────────────────────────────────────

class SyncLogOut(BaseModel):
    id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: Optional[str] = None
    invoices_synced: int
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class SyncStatusOut(BaseModel):
    last_sync: Optional[SyncLogOut] = None
    pending_count: int
    next_sync_date: Optional[date] = None


# ── Settings ─────────────────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    invoice_dir: Optional[str] = None
    sync_day_of_month: Optional[int] = Field(None, ge=1, le=28)
    notification_days_before: Optional[int] = Field(None, ge=1, le=27)
    min_invoice_threshold: Optional[int] = Field(None, ge=0)
    notify_email: Optional[bool] = None
    notify_sms: Optional[bool] = None
    email_address: Optional[str] = None
    phone_number: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    afip_cuit: Optional[str] = None
    afip_production: Optional[bool] = None
    cuitalizer_api_key: Optional[str] = None


class SettingsOut(BaseModel):
    invoice_dir: str
    sync_day_of_month: int
    notification_days_before: int
    min_invoice_threshold: int
    notify_email: bool
    notify_sms: bool
    email_address: Optional[str] = None
    phone_number: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    afip_cuit: Optional[str] = None
    afip_cert_path: Optional[str] = None
    afip_production: bool
    afip_setup_step: int
    cuitalizer_api_key: Optional[str] = None

    model_config = {"from_attributes": True}


# ── AFIP cert wizard ──────────────────────────────────────────────────────────

class CsrGenerated(BaseModel):
    csr_pem: str
    message: str


class CertUpload(BaseModel):
    cert_pem: str
