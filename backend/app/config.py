from __future__ import annotations
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the repo-root .env so config is loaded consistently no matter
# the working directory the server is launched from (e.g. uvicorn run from
# backend/). In Docker this path won't exist and settings fall back to OS env
# vars, which is exactly what docker-compose provides.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paths
    data_dir: Path = Path("data")
    invoice_dir: Path = Path("data/invoices")
    cert_dir: Path = Path("data/certs")
    db_url: str = "sqlite:///data/app.db"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]

    # AFIP (populated from DB settings row; these are defaults only)
    afip_cuit: str = ""
    afip_cert_path: str = ""
    afip_key_path: str = ""
    # Service name used in WSAA TRA — confirmed in ManualSiRADIG.pdf v1.19
    # Set to empty string until user reads the PDF and configures it
    afip_siradig_service: str = "siradig"
    afip_wsaa_homo_url: str = (
        "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
    )
    afip_wsaa_prod_url: str = (
        "https://wsaa.afip.gov.ar/ws/services/LoginCms"
    )
    # SiRADIG WSDL URLs — fill in after reading ManualSiRADIG.pdf v1.19
    afip_siradig_homo_wsdl: str = ""
    afip_siradig_prod_wsdl: str = ""
    afip_production: bool = False

    # Security
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"

    # ── Authentication / sessions ────────────────────────────────────────────
    # JWT is carried in an HTTP-only cookie. jwt_secret defaults to secret_key.
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 14  # 14 days
    cookie_name: str = "arca_session"
    # MUST be False over plain http (localhost) or the browser drops the cookie.
    # Set COOKIE_SECURE=true in the cloud (https).
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    # Public base URL used to build links in emails (verification, etc.)
    app_base_url: str = "http://localhost:8000"

    # ── Seeded owner/admin (bootstraps the first account; no self-registration) ─
    # Existing local data is backfilled onto this user so it stays visible.
    admin_email: str = "admin@localhost"
    admin_username: str = "admin"
    admin_password: str = "admin"  # CHANGE in production via env

    # ── Google OAuth ─────────────────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    # Redirect base; callback is <base>/api/auth/google/callback
    oauth_redirect_base: str = "http://localhost:8000"

    # ── System SMTP (for auth/verification emails — distinct from per-user
    #    notification SMTP stored in AppSettings) ───────────────────────────────
    system_smtp_host: str = ""
    system_smtp_port: int = 587
    system_smtp_user: str = ""
    system_smtp_password: str = ""
    system_smtp_from: str = ""

    @property
    def effective_jwt_secret(self) -> str:
        return self.jwt_secret or self.secret_key


settings = Settings()
