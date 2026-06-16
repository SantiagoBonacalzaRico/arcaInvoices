"""
WSAA — Web Service de Autenticación y Autorización de AFIP/ARCA.

Flow:
  1. Build TRA (Ticket de Requerimiento de Acceso) XML
  2. Sign TRA with RSA private key → CMS/PKCS#7 (S/MIME detached)
  3. POST to WSAA LoginCms endpoint with base64-encoded CMS
  4. Parse response → Token + Sign (valid 12 h)
  5. Cache in memory; auto-refresh when near expiry

Certificate notes
-----------------
Individual taxpayers can obtain a certificate by:
  1. Logging into https://auth.afip.gob.ar with CUIT + Clave Fiscal (level 2+)
  2. Going to "Administrador de Relaciones de Clave Fiscal" → "Adherir Servicio"
     and selecting ARCA → WebServices → "SiRADIG – Trabajador"
  3. Opening this app's Settings → AFIP Certificate → "Generate key pair"
     to create private.key + request.csr
  4. In the AFIP portal, going to "Administrador de Certificados Digitales"
     → "Nueva solicitud", uploading the .csr, and downloading cert.crt
  5. Uploading cert.crt back in this app to complete the setup
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
import httpx

from ..config import settings

_UTC = timezone.utc


class TokenSign:
    """In-memory cache for a WSAA access ticket."""

    def __init__(self, token: str, sign: str, expires_at: datetime):
        self.token = token
        self.sign = sign
        self.expires_at = expires_at

    @property
    def is_valid(self) -> bool:
        return datetime.now(_UTC) < self.expires_at - timedelta(minutes=5)


_cache: dict[str, TokenSign] = {}  # keyed by service name


def _build_tra(service: str) -> bytes:
    # Timestamps MUST carry the timezone offset.  Without it, AFIP's server
    # (UTC-3) reads naive UTC values as local time and rejects generationTime
    # as "in the future".  isoformat() on a tz-aware datetime appends "+00:00".
    now = datetime.now(_UTC).replace(microsecond=0)
    gen = (now - timedelta(minutes=10)).isoformat()
    exp = (now + timedelta(minutes=10)).isoformat()
    unique_id = str(int(now.timestamp()))
    tra = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<loginTicketRequest version="1.0">'
        f"<header>"
        f"<uniqueId>{unique_id}</uniqueId>"
        f"<generationTime>{gen}</generationTime>"
        f"<expirationTime>{exp}</expirationTime>"
        f"</header>"
        f"<service>{service}</service>"
        f"</loginTicketRequest>"
    )
    return tra.encode()


def _sign_tra(tra_bytes: bytes, key_path: str, cert_path: str) -> str:
    """Return base64-encoded CMS/PKCS#7 signed message."""
    from cryptography.hazmat.primitives.serialization import pkcs7

    with open(key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)
    with open(cert_path, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read())

    # WSAA receives only this CMS blob (the loginCms `in0` argument), so the TRA
    # must be EMBEDDED in the SignedData — a detached signature can't be verified
    # on the AFIP side.  `Binary` keeps the exact TRA bytes (no S/MIME text
    # canonicalization), which is what AFIP's verifier expects.
    builder = pkcs7.PKCS7SignatureBuilder().set_data(tra_bytes).add_signer(
        cert, private_key, hashes.SHA256()
    )
    cms = builder.sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])
    return base64.b64encode(cms).decode()


def _parse_soap_fault(xml_text: str) -> Optional[str]:
    """Return the SOAP <faultstring> message if the response is a fault, else None."""
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None
    fs = root.find(".//{*}faultstring")
    if fs is not None and (fs.text or "").strip():
        return fs.text.strip()
    return None


def _call_wsaa(cms_b64: str, production: bool) -> tuple[str, str, datetime]:
    """Call WSAA LoginCms and return (token, sign, expires_at)."""
    url = settings.afip_wsaa_prod_url if production else settings.afip_wsaa_homo_url
    envelope = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:wsaa="http://wsaa.afip.gov.ar/ws/services/LoginCms">'
        "<soapenv:Header/>"
        "<soapenv:Body>"
        "<wsaa:loginCms>"
        f"<wsaa:in0>{cms_b64}</wsaa:in0>"
        "</wsaa:loginCms>"
        "</soapenv:Body>"
        "</soapenv:Envelope>"
    )
    resp = httpx.post(
        url,
        content=envelope.encode(),
        headers={"Content-Type": "text/xml; charset=UTF-8", "SOAPAction": "loginCms"},
        timeout=30,
    )
    # WSAA returns the real reason inside a SOAP <faultstring> even on HTTP 500,
    # so parse the fault before raising on status — otherwise the useful message
    # ("certificado expirado", "ya posee un TA válido", etc.) is lost.
    fault = _parse_soap_fault(resp.text)
    if fault:
        raise RuntimeError(f"WSAA rechazó la autenticación: {fault}")
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    ns = {"tns": "http://wsaa.afip.gov.ar/ws/services/LoginCms"}
    ta_xml = root.find(".//{*}loginCmsReturn").text  # type: ignore[union-attr]
    ta_root = ET.fromstring(ta_xml)
    token = ta_root.findtext(".//{*}token") or ta_root.findtext(".//token") or ""
    sign = ta_root.findtext(".//{*}sign") or ta_root.findtext(".//sign") or ""
    exp_str = (
        ta_root.findtext(".//{*}expirationTime")
        or ta_root.findtext(".//expirationTime")
        or ""
    )
    expires_at = datetime.fromisoformat(exp_str.replace("Z", "+00:00")) if exp_str else (
        datetime.now(_UTC) + timedelta(hours=12)
    )
    return token, sign, expires_at


def get_token_sign(
    service: str,
    key_path: str,
    cert_path: str,
    production: bool = False,
) -> TokenSign:
    """Return a valid TokenSign, fetching a new one from WSAA if needed."""
    cache_key = f"{service}:{production}"
    cached = _cache.get(cache_key)
    if cached and cached.is_valid:
        return cached

    tra = _build_tra(service)
    cms_b64 = _sign_tra(tra, key_path, cert_path)
    token, sign, expires_at = _call_wsaa(cms_b64, production)
    ts = TokenSign(token, sign, expires_at)
    _cache[cache_key] = ts
    return ts


# ── Certificate generation helpers ───────────────────────────────────────────

def generate_key_and_csr(cuit: str, cert_dir: str, force: bool = False) -> tuple[Path, Path]:
    """
    Generate (or reuse) an RSA private key and build a CSR for the given CUIT.
    Returns (key_path, csr_path).

    If a private key already exists it is REUSED (not overwritten) unless
    force=True.  Overwriting a key after its CSR has been registered with AFIP
    is what breaks the key↔certificate pairing, so regeneration is opt-in.
    """
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

    cert_path = Path(cert_dir)
    cert_path.mkdir(parents=True, exist_ok=True)
    key_file = cert_path / "private.key"
    csr_file = cert_path / "request.csr"

    if key_file.exists() and not force:
        # Reuse the existing key so a previously-registered cert keeps matching.
        key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    else:
        key = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with open(key_file, "wb") as f:
            f.write(
                key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        key_file.chmod(0o600)

    # Build CSR
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, f"CUIT {cuit}"),
                x509.NameAttribute(NameOID.SERIAL_NUMBER, cuit),
                x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
            ])
        )
        .sign(key, hashes.SHA256())
    )
    with open(csr_file, "wb") as f:
        f.write(csr.public_bytes(serialization.Encoding.PEM))

    return key_file, csr_file


def save_certificate(cert_pem: str, cert_dir: str) -> Path:
    cert_path = Path(cert_dir) / "cert.crt"
    # Validate it's a real PEM cert before saving
    x509.load_pem_x509_certificate(cert_pem.encode())
    cert_path.write_text(cert_pem)
    return cert_path
