from __future__ import annotations
import platform
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSettings, User
from ..auth.security import get_current_user
from ..schemas import CertUpload, CsrGenerated, SettingsOut, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])

AFIP_SETUP_STEPS = [
    "Log into AFIP/ARCA and go to 'Administrador de Relaciones de Clave Fiscal'",
    "Adherir Servicio → ARCA → WebServices → 'SiRADIG – Trabajador'",
    "Generate key pair in this app (Settings → AFIP Certificate)",
    "Download the .csr file",
    "In AFIP portal: 'Administrador de Certificados Digitales' → 'Nueva solicitud' → upload .csr → download cert.crt",
    "Upload cert.crt in this app",
    "Verify WSAA connectivity",
]


def _get_or_create_settings(db: Session, user_id: int) -> AppSettings:
    s = db.query(AppSettings).filter(AppSettings.user_id == user_id).first()
    if not s:
        s = AppSettings(user_id=user_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _get_or_create_settings(db, user.id)


@router.put("", response_model=SettingsOut)
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from ..scheduler import update_schedule

    s = _get_or_create_settings(db, user.id)
    changed_schedule = False
    for field, value in payload.model_dump(exclude_none=True).items():
        if field in ("sync_day_of_month", "notification_days_before"):
            changed_schedule = True
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    if changed_schedule:
        update_schedule()
    return s


@router.post("/pick-folder")
def pick_folder(user: User = Depends(get_current_user)):
    """
    Open a native OS folder-picker dialog and return the selected path.
    Works because the server runs locally on the user's machine.
    """
    system = platform.system()
    selected = None

    if system == "Darwin":
        # macOS — use AppleScript (no extra dependencies)
        result = subprocess.run(
            ["osascript", "-e",
             'POSIX path of (choose folder with prompt "Seleccioná la carpeta para las facturas")'],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            selected = result.stdout.strip().rstrip("/")

    elif system == "Windows":
        # Windows — use PowerShell FolderBrowserDialog
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
            "$d.Description='Seleccioná la carpeta para las facturas';"
            "if($d.ShowDialog() -eq 'OK'){$d.SelectedPath}"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            selected = result.stdout.strip()

    else:
        # Linux — try zenity first, fall back to tkinter
        try:
            result = subprocess.run(
                ["zenity", "--file-selection", "--directory",
                 "--title=Seleccioná la carpeta para las facturas"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                selected = result.stdout.strip()
        except FileNotFoundError:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.wm_attributes("-topmost", True)
                selected = filedialog.askdirectory(
                    title="Seleccioná la carpeta para las facturas"
                )
                root.destroy()
            except Exception:
                pass

    if not selected:
        raise HTTPException(status_code=204, detail="No folder selected")

    return {"path": selected}


@router.get("/afip-setup-guide")
def afip_setup_guide(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = _get_or_create_settings(db, user.id)
    return {
        "current_step": s.afip_setup_step,
        "total_steps": len(AFIP_SETUP_STEPS),
        "steps": [
            {"index": i, "description": desc, "done": i < s.afip_setup_step}
            for i, desc in enumerate(AFIP_SETUP_STEPS)
        ],
        "note": (
            "SiRADIG WSDL URL required: read ManualSiRADIG.pdf v1.19 from "
            "https://www.afip.gob.ar/572web/documentos/ManualSiRADIG.pdf "
            "and set AFIP_SIRADIG_HOMO_WSDL / AFIP_SIRADIG_PROD_WSDL in your .env"
        ),
    }


@router.post("/afip/generate-csr", response_model=CsrGenerated)
def generate_csr(
    force: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Step 3: Generate (or reuse) the RSA key pair + CSR for the configured CUIT.
    Reuses an existing private key so an already-registered certificate keeps
    matching; pass force=true to generate a brand-new key pair.
    """
    from ..afip.wsaa import generate_key_and_csr
    from ..config import settings as cfg

    s = _get_or_create_settings(db, user.id)
    if not s.afip_cuit:
        raise HTTPException(status_code=400, detail="Set AFIP CUIT before generating a certificate.")
    key_file, csr_file = generate_key_and_csr(s.afip_cuit, str(cfg.cert_dir), force=force)
    s.afip_key_path = str(key_file)
    s.afip_setup_step = max(s.afip_setup_step, 3)
    db.commit()
    return CsrGenerated(
        csr_pem=csr_file.read_text(),
        message=(
            "CSR generated. Download it, then submit it to AFIP's "
            "'Administrador de Certificados Digitales' to obtain your cert.crt."
        ),
    )


@router.get("/afip/download-csr")
def download_csr(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from fastapi.responses import FileResponse
    from ..config import settings as cfg

    csr_path = Path(cfg.cert_dir) / "request.csr"
    if not csr_path.exists():
        raise HTTPException(status_code=404, detail="CSR not found. Generate it first.")
    return FileResponse(
        path=str(csr_path),
        media_type="application/x-pem-file",
        filename="request.csr",
    )


@router.post("/afip/upload-cert", response_model=SettingsOut)
async def upload_certificate(
    payload: CertUpload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Step 6: Upload the signed certificate (.crt) from AFIP."""
    from ..afip.wsaa import save_certificate
    from ..config import settings as cfg

    try:
        cert_path = save_certificate(payload.cert_pem, str(cfg.cert_dir))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid certificate: {exc}")

    s = _get_or_create_settings(db, user.id)
    s.afip_cert_path = str(cert_path)
    s.afip_setup_step = max(s.afip_setup_step, 6)
    db.commit()
    db.refresh(s)
    return s


@router.post("/afip/verify-connection")
def verify_afip_connection(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Step 7: Test WSAA authentication with the configured certificate."""
    from ..afip.siradig import SiRADIGClient, ConfigurationError

    s = _get_or_create_settings(db, user.id)
    try:
        client = SiRADIGClient(s)
        ok = client.test_connection()
        if ok:
            s.afip_setup_step = max(s.afip_setup_step, 7)
            db.commit()
        return {"status": "ok" if ok else "failed"}
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"WSAA error: {exc}")


@router.post("/test-notification")
async def test_notification(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..notifications import notify

    s = _get_or_create_settings(db, user.id)
    results = await notify(
        s,
        subject="Test — Factura SiRADIG",
        body="Esta es una notificación de prueba del sistema Factura SiRADIG.",
    )
    if not results:
        raise HTTPException(status_code=400, detail="No notification channels configured.")
    return results
