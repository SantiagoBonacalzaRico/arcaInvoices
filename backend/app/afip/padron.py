"""
CUIT → Razón Social lookup with two sources + local SQLite cache.

Priority:
  1. Local cache (cuit_registry table) — always checked first
  2. Cuitalizer REST API  — if api_key configured (simple, no cert needed)
  3. ws_sr_padron_a13     — if WSAA cert configured (official AFIP, free)
  4. Empty string         — falls back gracefully; user can fill manually

WSDL endpoints (ws_sr_padron_a13):
  Homologation: https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA13?WSDL
  Production:   https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA13?WSDL
WSAA service name: ws_sr_padron_a13
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..models import AppSettings, CuitRegistry

logger = logging.getLogger(__name__)

_PADRON_HOMO_WSDL = (
    "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA13?WSDL"
)
_PADRON_PROD_WSDL = (
    "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA13?WSDL"
)
_CUITALIZER_URL = "https://api.cuitalizer.com.ar/api/v1/contribuyente/consultar"


def _normalize_cuit(cuit: str) -> str:
    """Strip dashes and spaces → 11-digit string."""
    return cuit.replace("-", "").replace(" ", "")


def _from_cache(cuit: str, user_id: int, db: Session) -> Optional[str]:
    row = (
        db.query(CuitRegistry)
        .filter(CuitRegistry.cuit == cuit, CuitRegistry.user_id == user_id)
        .first()
    )
    return row.razon_social if row else None


def _save_cache(cuit: str, razon_social: str, source: str, user_id: int, db: Session) -> None:
    row = (
        db.query(CuitRegistry)
        .filter(CuitRegistry.cuit == cuit, CuitRegistry.user_id == user_id)
        .first()
    )
    if row:
        row.razon_social = razon_social
        row.source = source
        row.updated_at = datetime.utcnow()
    else:
        db.add(CuitRegistry(
            cuit=cuit, razon_social=razon_social, source=source, user_id=user_id
        ))
    db.commit()


def _user_settings(user_id: int, db: Session) -> Optional[AppSettings]:
    return db.query(AppSettings).filter(AppSettings.user_id == user_id).first()


def _from_cuitalizer(cuit_plain: str, api_key: str) -> Optional[str]:
    try:
        resp = httpx.post(
            _CUITALIZER_URL,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json={"cuit": cuit_plain},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("success"):
            return data["data"].get("razonSocial") or data["data"].get("razon_social")
    except Exception as exc:
        logger.warning("Cuitalizer lookup failed for %s: %s", cuit_plain, exc)
    return None


def _padron_a13_call(
    cuit_plain: str, key_path: str, cert_path: str, cuit_representada: str, production: bool
) -> Optional[str]:
    """
    Call ws_sr_padron_a13 getPersona and return the razón social (or None if the
    persona record carries no name).  Raises on auth / network / WSDL errors so
    callers that want diagnostics can see why a lookup failed.
    """
    from zeep import Client
    from .wsaa import get_token_sign

    wsdl = _PADRON_PROD_WSDL if production else _PADRON_HOMO_WSDL
    ts = get_token_sign(
        service="ws_sr_padron_a13",
        key_path=key_path,
        cert_path=cert_path,
        production=production,
    )
    client = Client(wsdl=wsdl)
    result = client.service.getPersona(
        token=ts.token,
        sign=ts.sign,
        cuitRepresentada=int(cuit_representada.replace("-", "")),
        idPersona=int(cuit_plain),
    )
    # A13 response: personaReturn.persona.{razonSocial | apellido + nombre}
    persona = getattr(result, "persona", None)
    if not persona:
        return None
    razon = getattr(persona, "razonSocial", None)
    if razon:
        return razon.strip()
    # Persona física: "Apellido, Nombre"
    apellido = (getattr(persona, "apellido", "") or "").strip()
    nombre   = (getattr(persona, "nombre", "") or "").strip()
    full = f"{apellido}, {nombre}".strip(", ").strip()
    return full or None


def _from_padron_a13(
    cuit_plain: str, key_path: str, cert_path: str, cuit_representada: str, production: bool
) -> Optional[str]:
    """Graceful wrapper around _padron_a13_call — swallows errors, returns None."""
    try:
        return _padron_a13_call(cuit_plain, key_path, cert_path, cuit_representada, production)
    except Exception as exc:
        logger.warning("ws_sr_padron_a13 lookup failed for %s: %s", cuit_plain, exc)
        return None


def lookup(cuit: str, db: Session, user_id: int) -> str:
    """
    Return razón social for a CUIT (scoped to *user_id*).
    Tries cache → Cuitalizer → ws_sr_padron_a13 → empty string.
    cuit may be in dashed (20-12345678-9) or plain (20123456789) format.
    """
    cuit_plain = _normalize_cuit(cuit)
    # Normalize to dashed for storage
    cuit_dashed = f"{cuit_plain[:2]}-{cuit_plain[2:10]}-{cuit_plain[10]}"

    # 1. Cache
    cached = _from_cache(cuit_dashed, user_id, db)
    if cached:
        return cached

    s = _user_settings(user_id, db)

    # 2. Cuitalizer
    if s and s.cuitalizer_api_key:
        razon = _from_cuitalizer(cuit_plain, s.cuitalizer_api_key)
        if razon:
            _save_cache(cuit_dashed, razon, "cuitalizer", user_id, db)
            return razon

    # 3. ws_sr_padron_a13 (requires WSAA cert)
    if s and s.afip_cuit and s.afip_key_path and s.afip_cert_path:
        razon = _from_padron_a13(
            cuit_plain,
            s.afip_key_path,
            s.afip_cert_path,
            s.afip_cuit,
            s.afip_production,
        )
        if razon:
            _save_cache(cuit_dashed, razon, "padron", user_id, db)
            return razon

    return ""


def cached_razon_social(cuit: str, db: Session, user_id: int) -> Optional[str]:
    """
    Cache-only lookup — NEVER makes a network call.  Used by hot paths like the
    invoice list, which must stay fast and must not block on WSAA/ARCA.
    """
    cuit_plain  = _normalize_cuit(cuit)
    cuit_dashed = f"{cuit_plain[:2]}-{cuit_plain[2:10]}-{cuit_plain[10]}"
    return _from_cache(cuit_dashed, user_id, db)


def set_manual(cuit: str, razon_social: str, db: Session, user_id: int) -> None:
    """Allow the user to manually set/override a razón social."""
    cuit_plain = _normalize_cuit(cuit)
    cuit_dashed = f"{cuit_plain[:2]}-{cuit_plain[2:10]}-{cuit_plain[10]}"
    _save_cache(cuit_dashed, razon_social, "manual", user_id, db)


def diagnose(cuit: str, db: Session, user_id: int) -> dict:
    """
    Like lookup(), but returns a structured result with the real error message
    when the ARCA call fails.  Used by the setup/test endpoint so the user can
    see *why* a lookup isn't working (missing cert, service not authorized,
    WSAA error, etc.) instead of a silent blank.
    """
    cuit_plain  = _normalize_cuit(cuit)
    cuit_dashed = f"{cuit_plain[:2]}-{cuit_plain[2:10]}-{cuit_plain[10]}"

    cached = _from_cache(cuit_dashed, user_id, db)
    if cached:
        return {"ok": True, "razon_social": cached, "source": "cache"}

    s = _user_settings(user_id, db)
    if not s:
        return {"ok": False, "source": None,
                "error": "No hay configuración. Completá el alta de AFIP en Ajustes."}

    if s.cuitalizer_api_key:
        razon = _from_cuitalizer(cuit_plain, s.cuitalizer_api_key)
        if razon:
            _save_cache(cuit_dashed, razon, "cuitalizer", user_id, db)
            return {"ok": True, "razon_social": razon, "source": "cuitalizer"}

    if s.afip_cuit and s.afip_key_path and s.afip_cert_path:
        try:
            razon = _padron_a13_call(
                cuit_plain, s.afip_key_path, s.afip_cert_path,
                s.afip_cuit, s.afip_production,
            )
        except Exception as exc:
            return {"ok": False, "source": "padron",
                    "error": f"{type(exc).__name__}: {exc}"}
        if razon:
            _save_cache(cuit_dashed, razon, "padron", user_id, db)
            return {"ok": True, "razon_social": razon, "source": "padron"}
        return {"ok": False, "source": "padron",
                "error": "ARCA respondió sin razón social para este CUIT."}

    return {"ok": False, "source": None,
            "error": ("No hay certificado de ARCA ni API key de Cuitalizer configurados. "
                      "Completá el alta del certificado AFIP en Ajustes, "
                      "y autorizá el servicio 'ws_sr_padron_a13' para tu CUIT.")}
