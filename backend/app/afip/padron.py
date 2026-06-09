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


def _from_cache(cuit: str, db: Session) -> Optional[str]:
    row = db.query(CuitRegistry).filter(CuitRegistry.cuit == cuit).first()
    return row.razon_social if row else None


def _save_cache(cuit: str, razon_social: str, source: str, db: Session) -> None:
    row = db.query(CuitRegistry).filter(CuitRegistry.cuit == cuit).first()
    if row:
        row.razon_social = razon_social
        row.source = source
        row.updated_at = datetime.utcnow()
    else:
        db.add(CuitRegistry(cuit=cuit, razon_social=razon_social, source=source))
    db.commit()


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


def _from_padron_a13(
    cuit_plain: str, key_path: str, cert_path: str, cuit_representada: str, production: bool
) -> Optional[str]:
    try:
        from zeep import Client
        from ..wsaa import get_token_sign

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
        # Response has datosGenerales.denominacion (empresas) or nombre+apellido (personas)
        datos = getattr(result, "datosGenerales", None)
        if datos:
            nombre = getattr(datos, "denominacion", None)
            if nombre:
                return nombre.strip()
            # Persona física: apellido, nombre
            apellido = getattr(datos, "apellido", "")
            nombre_pf = getattr(datos, "nombre", "")
            if apellido:
                return f"{apellido}, {nombre_pf}".strip(", ")
    except Exception as exc:
        logger.warning("ws_sr_padron_a13 lookup failed for %s: %s", cuit_plain, exc)
    return None


def lookup(cuit: str, db: Session) -> str:
    """
    Return razón social for a CUIT.
    Tries cache → Cuitalizer → ws_sr_padron_a13 → empty string.
    cuit may be in dashed (20-12345678-9) or plain (20123456789) format.
    """
    cuit_plain = _normalize_cuit(cuit)
    # Normalize to dashed for storage
    cuit_dashed = f"{cuit_plain[:2]}-{cuit_plain[2:10]}-{cuit_plain[10]}"

    # 1. Cache
    cached = _from_cache(cuit_dashed, db)
    if cached:
        return cached

    s: Optional[AppSettings] = db.query(AppSettings).filter(AppSettings.id == 1).first()

    # 2. Cuitalizer
    if s and s.cuitalizer_api_key:
        razon = _from_cuitalizer(cuit_plain, s.cuitalizer_api_key)
        if razon:
            _save_cache(cuit_dashed, razon, "cuitalizer", db)
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
            _save_cache(cuit_dashed, razon, "padron", db)
            return razon

    return ""


def set_manual(cuit: str, razon_social: str, db: Session) -> None:
    """Allow the user to manually set/override a razón social."""
    cuit_plain = _normalize_cuit(cuit)
    cuit_dashed = f"{cuit_plain[:2]}-{cuit_plain[2:10]}-{cuit_plain[10]}"
    _save_cache(cuit_dashed, razon_social, "manual", db)
