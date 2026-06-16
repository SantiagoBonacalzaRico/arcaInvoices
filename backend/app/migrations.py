"""
Lightweight, dialect-aware migration runner (SQLite + PostgreSQL).

Runs at startup via main.py lifespan, AFTER SQLAlchemy's create_all (which
creates any wholly-missing tables but never alters existing ones). This handles:
  * legacy column additions to app_settings
  * the auth/multi-tenancy upgrade: seed an owner user and attach all pre-existing
    rows (invoices, settings, cuit cache, …) to it via a new user_id column
  * rebuilding cuit_registry to a per-user schema (SQLite in-place upgrade)

It is idempotent: on a fresh database every table already has its final shape,
so the only effect is seeding the owner/admin account.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .config import settings

logger = logging.getLogger(__name__)


def _cols(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def _ensure_owner(conn) -> int:
    """Return the seeded owner/admin user id, creating it if absent."""
    row = conn.execute(
        text("SELECT id FROM users WHERE email = :e"),
        {"e": settings.admin_email},
    ).fetchone()
    if row:
        return row[0]

    from .auth.security import hash_password

    conn.execute(
        text(
            "INSERT INTO users "
            "(email, username, password_hash, is_verified, is_active, is_admin, created_at) "
            "VALUES (:email, :username, :ph, :verified, :active, :admin, :created)"
        ),
        {
            "email": settings.admin_email,
            "username": settings.admin_username,
            "ph": hash_password(settings.admin_password),
            "verified": True,
            "active": True,
            "admin": True,
            "created": datetime.utcnow(),
        },
    )
    owner_id = conn.execute(
        text("SELECT id FROM users WHERE email = :e"),
        {"e": settings.admin_email},
    ).fetchone()[0]
    logger.info("Seeded owner/admin user '%s' (id=%s)", settings.admin_email, owner_id)
    return owner_id


def _add_user_id_and_backfill(conn, insp, table: str, owner_id: int, index_sql: str) -> None:
    if "user_id" in _cols(insp, table):
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"))
    conn.execute(
        text(f"UPDATE {table} SET user_id = :o WHERE user_id IS NULL"),
        {"o": owner_id},
    )
    conn.execute(text(index_sql))
    logger.info("Migration: added %s.user_id and backfilled to owner", table)


def _rebuild_cuit_registry(conn, owner_id: int) -> None:
    """SQLite in-place rebuild from (cuit PK) → (id PK, per-user unique)."""
    conn.execute(text(
        "CREATE TABLE cuit_registry_new ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " user_id INTEGER NOT NULL,"
        " cuit VARCHAR(13) NOT NULL,"
        " razon_social VARCHAR(256) NOT NULL,"
        " source VARCHAR(16) DEFAULT 'manual',"
        " updated_at TIMESTAMP NOT NULL,"
        " UNIQUE(user_id, cuit))"
    ))
    conn.execute(
        text(
            "INSERT INTO cuit_registry_new (user_id, cuit, razon_social, source, updated_at) "
            "SELECT :o, cuit, razon_social, COALESCE(source, 'manual'), "
            "COALESCE(updated_at, :now) FROM cuit_registry"
        ),
        {"o": owner_id, "now": datetime.utcnow()},
    )
    conn.execute(text("DROP TABLE cuit_registry"))
    conn.execute(text("ALTER TABLE cuit_registry_new RENAME TO cuit_registry"))
    conn.execute(text("CREATE INDEX ix_cuit_registry_user_id ON cuit_registry (user_id)"))
    logger.info("Migration: rebuilt cuit_registry as per-user table")


def run(engine: Engine) -> None:
    is_sqlite = engine.dialect.name == "sqlite"

    with engine.begin() as conn:
        insp = inspect(conn)

        # ── Legacy app_settings column additions (pre-auth DBs) ───────────────
        if insp.has_table("app_settings"):
            settings_cols = _cols(insp, "app_settings")
            if "cuitalizer_api_key" not in settings_cols:
                conn.execute(text(
                    "ALTER TABLE app_settings ADD COLUMN cuitalizer_api_key VARCHAR(128)"
                ))
            if "afip_setup_step" not in settings_cols:
                conn.execute(text(
                    "ALTER TABLE app_settings ADD COLUMN afip_setup_step INTEGER DEFAULT 0"
                ))

        # ── Auth / multi-tenancy upgrade ──────────────────────────────────────
        # users table is created by create_all; seed the owner so existing data
        # has someone to belong to.
        owner_id = _ensure_owner(conn)
        insp = inspect(conn)  # refresh after potential DDL

        _add_user_id_and_backfill(
            conn, insp, "invoices", owner_id,
            "CREATE INDEX IF NOT EXISTS idx_invoices_user ON invoices (user_id)",
        )
        _add_user_id_and_backfill(
            conn, insp, "ocr_corrections", owner_id,
            "CREATE INDEX IF NOT EXISTS ix_ocr_corrections_user_id ON ocr_corrections (user_id)",
        )
        _add_user_id_and_backfill(
            conn, insp, "sync_logs", owner_id,
            "CREATE INDEX IF NOT EXISTS ix_sync_logs_user_id ON sync_logs (user_id)",
        )

        # app_settings: add user_id, attach the existing single row to the owner
        if "user_id" not in _cols(insp, "app_settings"):
            conn.execute(text("ALTER TABLE app_settings ADD COLUMN user_id INTEGER"))
            conn.execute(
                text("UPDATE app_settings SET user_id = :o WHERE user_id IS NULL"),
                {"o": owner_id},
            )
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_app_settings_user_id "
                "ON app_settings (user_id)"
            ))
            logger.info("Migration: added app_settings.user_id, attached existing row to owner")

        # cuit_registry: rebuild to per-user schema (only the old SQLite shape)
        if insp.has_table("cuit_registry") and "user_id" not in _cols(insp, "cuit_registry"):
            if is_sqlite:
                _rebuild_cuit_registry(conn, owner_id)
            else:
                # Non-SQLite legacy upgrade path (not expected for fresh cloud DBs)
                conn.execute(text("ALTER TABLE cuit_registry ADD COLUMN user_id INTEGER"))
                conn.execute(
                    text("UPDATE cuit_registry SET user_id = :o WHERE user_id IS NULL"),
                    {"o": owner_id},
                )
