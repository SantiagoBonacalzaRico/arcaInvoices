from __future__ import annotations
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine
from .routers import invoices, sync, settings as settings_router, export

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    Base.metadata.create_all(bind=engine)
    # Apply any missing column/table migrations
    from .migrations import run as run_migrations
    run_migrations(engine)
    # Ensure data directories exist
    Path(settings.invoice_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.cert_dir).mkdir(parents=True, exist_ok=True)
    # Start scheduler
    from .scheduler import start_scheduler
    start_scheduler()
    yield
    # Shutdown scheduler
    from .scheduler import get_scheduler
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Factura SiRADIG",
    description="Invoice OCR + ARCA/SiRADIG sync API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(invoices.router)
app.include_router(sync.router)
app.include_router(settings_router.router)
app.include_router(export.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve frontend build in production
_frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")
