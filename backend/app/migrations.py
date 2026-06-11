"""
Lightweight migration runner for SQLite.

Runs at startup via main.py lifespan. Applies any missing columns or tables
that SQLAlchemy's create_all misses (it never alters existing tables).
"""
from __future__ import annotations
import logging
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    ).fetchone()
    return row is not None


def run(engine: Engine) -> None:
    with engine.begin() as conn:
        # ── app_settings additions ────────────────────────────────────────────
        if _table_exists(conn, "app_settings"):
            if not _column_exists(conn, "app_settings", "cuitalizer_api_key"):
                conn.execute(text(
                    "ALTER TABLE app_settings ADD COLUMN cuitalizer_api_key VARCHAR(128)"
                ))
                logger.info("Migration: added app_settings.cuitalizer_api_key")

            if not _column_exists(conn, "app_settings", "afip_setup_step"):
                conn.execute(text(
                    "ALTER TABLE app_settings ADD COLUMN afip_setup_step INTEGER DEFAULT 0"
                ))
                logger.info("Migration: added app_settings.afip_setup_step")

        # ── cuit_registry table ───────────────────────────────────────────────
        if not _table_exists(conn, "cuit_registry"):
            conn.execute(text("""
                CREATE TABLE cuit_registry (
                    cuit VARCHAR(13) PRIMARY KEY,
                    razon_social VARCHAR(256) NOT NULL,
                    source VARCHAR(16) DEFAULT 'manual',
                    updated_at DATETIME NOT NULL
                )
            """))
            logger.info("Migration: created cuit_registry table")

        # ── ocr_corrections table ─────────────────────────────────────────────
        if not _table_exists(conn, "ocr_corrections"):
            conn.execute(text("""
                CREATE TABLE ocr_corrections (
                    id INTEGER PRIMARY KEY,
                    invoice_id INTEGER REFERENCES invoices(id),
                    field_name VARCHAR(32) NOT NULL,
                    raw_snippet TEXT,
                    correct_value TEXT NOT NULL,
                    image_hash VARCHAR(64),
                    created_at DATETIME NOT NULL
                )
            """))
            logger.info("Migration: created ocr_corrections table")
