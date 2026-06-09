"""
SiRADIG – Trabajador SOAP client.

⚠️  WSDL URL & service name
────────────────────────────
The exact WSDL URLs and the WSAA service identifier string for
"SiRADIG – Trabajador" are specified in the official manual:

  ManualSiRADIG.pdf  v1.19  (March 2026)
  https://www.afip.gob.ar/572web/documentos/ManualSiRADIG.pdf

Before using this module in production, you must:
  1. Download and read the PDF above.
  2. Set AFIP_SIRADIG_HOMO_WSDL and AFIP_SIRADIG_PROD_WSDL in your .env
     (or update config.py) with the exact WSDL URLs from the manual.
  3. Confirm the WSAA service name (currently set to "siradig" in config.py —
     verify against the manual and update AFIP_SIRADIG_SERVICE if needed).

Until these values are configured, sync calls will raise ConfigurationError.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models import AppSettings, Invoice, SyncLog
from .wsaa import get_token_sign


class ConfigurationError(Exception):
    pass


class SiRADIGClient:
    def __init__(self, db_settings: AppSettings):
        self._s = db_settings
        self._production = db_settings.afip_production

    def _require_config(self) -> None:
        wsdl = (
            settings.afip_siradig_prod_wsdl
            if self._production
            else settings.afip_siradig_homo_wsdl
        )
        if not wsdl:
            raise ConfigurationError(
                "SiRADIG WSDL URL is not configured. "
                "Read ManualSiRADIG.pdf v1.19 from "
                "https://www.afip.gob.ar/572web/documentos/ManualSiRADIG.pdf "
                "and set AFIP_SIRADIG_HOMO_WSDL / AFIP_SIRADIG_PROD_WSDL in your .env file."
            )
        if not self._s.afip_cuit:
            raise ConfigurationError("AFIP CUIT is not configured.")
        if not self._s.afip_cert_path or not self._s.afip_key_path:
            raise ConfigurationError(
                "AFIP certificate/key not configured. "
                "Complete the AFIP setup wizard in Settings."
            )

    def _get_zeep_client(self):
        try:
            from zeep import Client
            from zeep.transports import Transport
        except ImportError as e:
            raise ImportError("zeep is required for AFIP SOAP calls. Run: pip install zeep") from e

        wsdl = (
            settings.afip_siradig_prod_wsdl
            if self._production
            else settings.afip_siradig_homo_wsdl
        )
        return Client(wsdl=wsdl)

    def _auth_header(self) -> dict:
        ts = get_token_sign(
            service=settings.afip_siradig_service,
            key_path=self._s.afip_key_path,
            cert_path=self._s.afip_cert_path,
            production=self._production,
        )
        return {
            "token": ts.token,
            "sign": ts.sign,
            "cuitRepresentada": self._s.afip_cuit,
        }

    def submit_invoice(self, invoice: Invoice) -> bool:
        """
        Submit a single deductible expense to SiRADIG.

        The exact SOAP operation name and request structure must be confirmed
        from ManualSiRADIG.pdf v1.19. This is a placeholder implementation
        that will be updated once the WSDL URL and operation schema are known.

        Returns True on success.
        """
        self._require_config()
        client = self._get_zeep_client()
        auth = self._auth_header()

        # ── Placeholder: update operation name and fields from the manual ──
        # The typical AFIP SOAP auth header is passed as a "Auth" complex type.
        # Expected call pattern (verify against actual WSDL):
        #
        #   result = client.service.informarGasto(
        #       auth=auth,
        #       gasto={
        #           "cuitEmisor": invoice.cuit,
        #           "fecha": str(invoice.invoice_date),
        #           "nroComprobante": invoice.invoice_number,
        #           "importe": str(invoice.total_amount),
        #           "concepto": invoice.category or "OTROS",
        #       }
        #   )
        #   return result.resultado == "A"  # "A" = aceptado
        #
        raise NotImplementedError(
            "SiRADIG SOAP operation details pending. "
            "See the module docstring and read ManualSiRADIG.pdf v1.19."
        )

    def test_connection(self) -> bool:
        """Verify WSAA authentication works (does not call SiRADIG business ops)."""
        self._require_config()
        ts = get_token_sign(
            service=settings.afip_siradig_service,
            key_path=self._s.afip_key_path,
            cert_path=self._s.afip_cert_path,
            production=self._production,
        )
        return bool(ts.token and ts.sign)


def run_sync(db: Session) -> SyncLog:
    from datetime import datetime

    from ..models import Invoice as Inv, SyncLog as SL

    db_settings = db.query(AppSettings).filter(AppSettings.id == 1).first()
    log = SL(started_at=datetime.utcnow(), invoices_synced=0, status="running")
    db.add(log)
    db.commit()

    try:
        client = SiRADIGClient(db_settings)
        pending = (
            db.query(Inv)
            .filter(Inv.sync_status == "pending")
            .order_by(Inv.invoice_date)
            .all()
        )
        synced = 0
        errors = []
        for inv in pending:
            try:
                client.submit_invoice(inv)
                inv.sync_status = "synced"
                inv.synced_at = datetime.utcnow()
                synced += 1
            except NotImplementedError:
                # SiRADIG SOAP not yet fully implemented
                inv.sync_status = "error"
                errors.append(f"invoice {inv.id}: SiRADIG operation not implemented yet")
            except Exception as exc:
                inv.sync_status = "error"
                errors.append(f"invoice {inv.id}: {exc}")
        db.commit()
        log.completed_at = datetime.utcnow()
        log.invoices_synced = synced
        log.status = "success" if not errors else ("partial" if synced else "failed")
        log.error_message = "\n".join(errors) if errors else None
    except Exception as exc:
        log.completed_at = __import__("datetime").datetime.utcnow()
        log.status = "failed"
        log.error_message = str(exc)

    db.commit()
    return log
