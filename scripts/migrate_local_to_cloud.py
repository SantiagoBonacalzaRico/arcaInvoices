#!/usr/bin/env python3
"""
Migrate local invoices into the cloud account, via the running app's API.

Reads the local SQLite database READ-ONLY (never modified) and, logged in as the
target user, recreates the CUIT registry (razón social) and the invoices in the
cloud. Idempotent: invoices already present (same cuit + número + fecha) are
skipped, and razón social entries are upserted.

Usage:
  API_BASE=https://your-host \
  IDENTIFIER=santiago PASSWORD=... \
  [LOCAL_DB=backend/data/app.db] \
  python scripts/migrate_local_to_cloud.py
"""
from __future__ import annotations

import os
import sqlite3
import sys

import httpx

API_BASE = os.environ.get("API_BASE", "https://56.126.116.221.sslip.io").rstrip("/")
IDENTIFIER = os.environ.get("IDENTIFIER")
PASSWORD = os.environ.get("PASSWORD")
LOCAL_DB = os.environ.get("LOCAL_DB", "backend/data/app.db")


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if not IDENTIFIER or not PASSWORD:
        die("Set IDENTIFIER and PASSWORD env vars (the cloud account to import into).")
    if not os.path.exists(LOCAL_DB):
        die(f"Local DB not found: {LOCAL_DB}")

    # Read-only connection — the local DB is never modified.
    conn = sqlite3.connect(f"file:{LOCAL_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    invoices = conn.execute(
        "SELECT cuit, invoice_date, invoice_number, total_amount, category "
        "FROM invoices ORDER BY invoice_date"
    ).fetchall()
    cuits = conn.execute("SELECT cuit, razon_social FROM cuit_registry").fetchall()
    conn.close()
    print(f"Local: {len(invoices)} invoices, {len(cuits)} razón social entries.")

    with httpx.Client(base_url=API_BASE, timeout=30.0, follow_redirects=True) as c:
        r = c.post("/api/auth/login", json={"identifier": IDENTIFIER, "password": PASSWORD})
        if r.status_code != 200:
            die(f"Login failed ({r.status_code}): {r.text}")
        me = c.get("/api/auth/me").json()
        print(f"Logged in as {me['username']} <{me['email']}> (id={me['id']}).")

        # 1) Razón social (CUIT registry) — upsert each.
        rs_ok = 0
        for row in cuits:
            rr = c.post(f"/api/cuit/{row['cuit']}", params={"razon_social": row["razon_social"]})
            if rr.status_code < 300:
                rs_ok += 1
            else:
                print(f"  ! razón social {row['cuit']} -> {rr.status_code}")
        print(f"Razón social: {rs_ok}/{len(cuits)} upserted.")

        # 2) Invoices — skip duplicates by (cuit, número, fecha).
        existing = c.get("/api/invoices", params={"limit": 500}).json()
        seen = {(i["cuit"], i["invoice_number"], str(i["invoice_date"])) for i in existing}

        created = skipped = failed = 0
        for inv in invoices:
            key = (inv["cuit"], inv["invoice_number"], str(inv["invoice_date"]))
            if key in seen:
                skipped += 1
                continue
            payload = {
                "cuit": inv["cuit"],
                "invoice_date": inv["invoice_date"],
                "invoice_number": inv["invoice_number"],
                "total_amount": f"{float(inv['total_amount']):.2f}",
                "category": inv["category"],
            }
            cr = c.post("/api/invoices", json=payload)
            if cr.status_code in (200, 201):
                created += 1
                seen.add(key)
            else:
                failed += 1
                print(f"  ! invoice {inv['invoice_number']} -> {cr.status_code}: {cr.text}")

        print(f"Invoices: {created} created, {skipped} skipped (already present), {failed} failed.")
        total = c.get("/api/invoices", params={"limit": 500}).json()
        print(f"Cloud account now has {len(total)} invoices.")


if __name__ == "__main__":
    main()
