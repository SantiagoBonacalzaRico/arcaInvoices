from __future__ import annotations
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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


settings = Settings()
