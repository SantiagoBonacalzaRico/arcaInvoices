"""
Regression tests for the barcode/QR scan performance fix.

Background: full-resolution phone photos (≈12 MP) — and their 2× upscales —
made the multi-region decode sweep take minutes on the small prod instance
whenever no code decoded, so the mobile app timed out ("very long time, no
result"). The fix caps the working resolution before the sweep and only
upscales genuinely small regions, while preserving QR decode.
"""
import time
import numpy as np
import pytest

from app.ocr.barcode import scan, _cap_size, _MAX_SCAN_SIDE


def test_cap_size_downscales_large_images():
    img = np.zeros((4000, 3000, 3), dtype=np.uint8)
    out = _cap_size(img)
    assert max(out.shape[:2]) == _MAX_SCAN_SIDE
    # aspect ratio preserved
    assert abs(out.shape[0] / out.shape[1] - 4000 / 3000) < 0.01


def test_cap_size_leaves_small_images_untouched():
    img = np.zeros((800, 600, 3), dtype=np.uint8)
    out = _cap_size(img)
    assert out.shape == img.shape


def test_scan_large_image_is_robust_and_bounded():
    """A non-decoding 12 MP image must not raise and must finish quickly
    (pre-fix this ran the full sweep on 8000×6000 arrays → minutes)."""
    img = np.full((4000, 3000, 3), 255, dtype=np.uint8)
    t = time.time()
    result = scan(img)
    elapsed = time.time() - t
    assert result is None
    # Generous bound: pre-fix was ~30s on a fast dev box (minutes on prod);
    # capped sweep is a few seconds. This guards against reverting the cap.
    assert elapsed < 20, f"scan too slow ({elapsed:.1f}s) — resolution cap may be gone"


def test_downscaling_preserves_arca_qr_decode():
    """The reliable QR path must still decode after the size cap. Skipped where
    the `qrcode` generator isn't installed (e.g. minimal CI)."""
    qrcode = pytest.importorskip("qrcode")
    import base64, json, cv2

    payload = {"ver": 1, "fecha": "2025-10-15", "cuit": 30708705639,
               "ptoVta": 662, "tipoCmp": 11, "nroCmp": 6100111,
               "importe": 119859.02, "moneda": "PES"}
    url = "https://www.afip.gob.ar/fe/qr/?p=" + base64.b64encode(
        json.dumps(payload).encode()).decode()
    qr = np.array(qrcode.make(url).convert("RGB"))

    # Embed a realistically-sized QR into a large "phone photo" canvas.
    canvas = np.full((4000, 3000, 3), 255, dtype=np.uint8)
    q = cv2.resize(qr, (500, 500), interpolation=cv2.INTER_AREA)
    canvas[300:800, 1200:1700] = cv2.cvtColor(q, cv2.COLOR_RGB2BGR)

    result = scan(canvas)
    assert result is not None and result.source == "arca_qr"
    assert result.invoice_number == "00662-06100111"
    assert result.cuit == "30-70870563-9"
