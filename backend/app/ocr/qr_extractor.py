"""
Fetch a non-ARCA QR URL and extract invoice fields from the response.
Used when barcode.py finds a generic HTTP/HTTPS QR in the image.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from ..schemas import OcrField

_PRIVATE_HOST = re.compile(
    r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)",
    re.IGNORECASE,
)


class _StripHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self._parts.append(stripped)

    def text(self) -> str:
        return " ".join(self._parts)


def fetch_and_extract(url: str) -> "dict[str, OcrField]":
    """
    Fetch *url*, strip HTML, run OCR field extractors on the plain text.

    Returns a dict of ``{field_name: OcrField}`` for every field whose
    confidence reaches the extraction threshold.  Returns ``{}`` on any
    network error, timeout, or if the URL looks like a private address.
    """
    if not url.startswith(("http://", "https://")):
        return {}

    # Basic SSRF guard — reject loopback / RFC-1918 hosts
    try:
        host = url.split("/")[2].split(":")[0]
    except IndexError:
        return {}
    if _PRIVATE_HOST.match(host):
        return {}

    try:
        resp = httpx.get(
            url,
            timeout=8.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FlatOCR/1.0)"},
        )
        content_type = resp.headers.get("content-type", "")
        if "html" in content_type:
            parser = _StripHTML()
            parser.feed(resp.text)
            text = parser.text()
        else:
            text = resp.text[:100_000]   # cap at 100 kB for non-HTML
    except Exception:
        return {}

    if not text.strip():
        return {}

    # Import here to avoid circular dependency at module load time
    from .extractor import (
        CONFIDENCE_THRESHOLD,
        _extract_cuit,
        _extract_date,
        _extract_invoice_number,
        _extract_total,
    )

    fields: dict[str, OcrField] = {}
    for name, fn in (
        ("cuit",           _extract_cuit),
        ("invoice_date",   _extract_date),
        ("invoice_number", _extract_invoice_number),
        ("total_amount",   _extract_total),
    ):
        result = fn(text)
        if result.confidence >= CONFIDENCE_THRESHOLD:
            fields[name] = result
    return fields
