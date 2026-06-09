"""
Export and aggregated-view endpoints.

GET  /api/export/summary       → JSON grouped by CUIT + razón social
GET  /api/export/csv           → CSV download (open in Excel / Google Sheets)
GET  /api/cuit/{cuit}          → look up razón social for a single CUIT
POST /api/cuit/{cuit}          → manually set razón social
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Invoice

router = APIRouter(tags=["export"])

DEDUCTION_CATEGORIES = [
    "Cuotas Médico-Asistenciales",
    "Primas de Seguro (muerte)",
    "Donaciones",
    "Intereses Préstamo Hipotecario",
    "Gastos de Sepelio",
    "Gastos Médicos y Paramédicos",
    "Personal Doméstico",
    "Aporte a Soc. de Garantía Recíproca",
    "Alquiler de Inmuebles (40%)",
    "Alquiler de Inmuebles (10%)",
    "Alquiler - Locador (propietario)",
    "Primas de Ahorro / Seguros Mixtos",
    "Planes de Seguro de Retiro Privados",
    "Fondos Comunes de Inversión (retiro)",
    "Gastos de Educación",
    "Indumentaria / Equipamiento laboral",
    "Otras Deducciones",
]


def _fmt_amount(amount) -> str:
    """Format Decimal/float as '201000.00' — no thousands separator."""
    return f"{Decimal(str(amount)):.2f}"


def _get_razon_social(cuit: str, db: Session) -> str:
    from ..afip.padron import lookup
    return lookup(cuit, db)


# ── CUIT registry ──────────────────────────────────────────────────────────────

@router.get("/api/cuit/{cuit}")
def get_razon_social(cuit: str, db: Session = Depends(get_db)):
    """Look up razón social for a CUIT (cache → Cuitalizer → padron)."""
    razon = _get_razon_social(cuit, db)
    return {"cuit": cuit, "razon_social": razon, "found": bool(razon)}


@router.post("/api/cuit/{cuit}")
def set_razon_social(cuit: str, razon_social: str, db: Session = Depends(get_db)):
    """Manually set or override the razón social for a CUIT."""
    from ..afip.padron import set_manual
    set_manual(cuit, razon_social, db)
    return {"cuit": cuit, "razon_social": razon_social}


# ── Summary view ──────────────────────────────────────────────────────────────

@router.get("/api/export/summary")
def export_summary(
    fiscal_year: Optional[int] = Query(None, description="Filter by year, e.g. 2025"),
    sync_status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Returns invoices aggregated by CUIT + razón social, with each
    invoice line ready to transcribe into SiRADIG.

    Structure:
    [
      {
        "cuit": "30-71099285-4",
        "razon_social": "Clínica ABC SRL",
        "total": "15000.00",
        "invoices": [
          {
            "invoice_number": "0001-00000123",
            "date": "2025-03-15",
            "amount": "5000.00",
            "category": "Gastos Médicos y Paramédicos"
          },
          ...
        ]
      },
      ...
    ]
    """
    q = db.query(Invoice)
    if fiscal_year:
        q = q.filter(Invoice.invoice_date >= f"{fiscal_year}-01-01",
                     Invoice.invoice_date <= f"{fiscal_year}-12-31")
    if sync_status:
        q = q.filter(Invoice.sync_status == sync_status)

    invoices = q.order_by(Invoice.cuit, Invoice.invoice_date).all()

    # Group by CUIT
    groups: dict[str, dict] = {}
    for inv in invoices:
        if inv.cuit not in groups:
            groups[inv.cuit] = {
                "cuit": inv.cuit,
                "razon_social": _get_razon_social(inv.cuit, db),
                "total": Decimal("0"),
                "invoices": [],
            }
        groups[inv.cuit]["total"] += Decimal(str(inv.total_amount))
        groups[inv.cuit]["invoices"].append({
            "invoice_number": inv.invoice_number,
            "date": str(inv.invoice_date),
            "amount": _fmt_amount(inv.total_amount),
            "category": inv.category or "",
            "sync_status": inv.sync_status,
            "id": inv.id,
        })

    result = []
    for g in groups.values():
        result.append({
            **g,
            "total": _fmt_amount(g["total"]),
        })

    return result


# ── CSV export ────────────────────────────────────────────────────────────────

@router.get("/api/export/csv")
def export_csv(
    fiscal_year: Optional[int] = Query(None),
    sync_status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Download a CSV file with one row per invoice, columns:
    CUIT | Razón Social | Nro Comprobante | Fecha | Importe | Categoría | Estado

    Compatible with Excel and Google Sheets (semicolon separator,
    UTF-8 BOM so Excel opens it correctly without import wizard).
    """
    q = db.query(Invoice)
    if fiscal_year:
        q = q.filter(Invoice.invoice_date >= f"{fiscal_year}-01-01",
                     Invoice.invoice_date <= f"{fiscal_year}-12-31")
    if sync_status:
        q = q.filter(Invoice.sync_status == sync_status)

    invoices = q.order_by(Invoice.cuit, Invoice.invoice_date).all()

    buf = io.StringIO()
    # UTF-8 BOM — makes Excel on Windows auto-detect encoding
    buf.write("﻿")
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "CUIT", "Razón Social", "Nro Comprobante",
        "Fecha", "Importe", "Categoría", "Estado",
    ])
    for inv in invoices:
        razon = _get_razon_social(inv.cuit, db)
        writer.writerow([
            inv.cuit,
            razon,
            inv.invoice_number,
            str(inv.invoice_date),
            _fmt_amount(inv.total_amount),
            inv.category or "",
            inv.sync_status,
        ])

    buf.seek(0)
    filename = f"facturas_{fiscal_year or 'todas'}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/export/categories")
def list_categories():
    """Return the list of valid SiRADIG deduction categories."""
    return DEDUCTION_CATEGORIES
