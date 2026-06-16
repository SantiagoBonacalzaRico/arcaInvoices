from __future__ import annotations
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import Base, engine
from .routers import invoices, sync, settings as settings_router, export, auth

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

# Required by Authlib to hold the OAuth state between /google/login and /callback.
app.add_middleware(SessionMiddleware, secret_key=settings.effective_jwt_secret)

app.include_router(auth.router)
app.include_router(invoices.router)
app.include_router(sync.router)
app.include_router(settings_router.router)
app.include_router(export.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve frontend build in production with SPA history-mode fallback so deep
# links (e.g. the /verify?token=… email link, /login, /invoices) work on a
# fresh page load instead of 404-ing.
_frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    _assets_dir = _frontend_dist / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Never swallow unmatched API routes — surface a real 404.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = _frontend_dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_frontend_dist / "index.html"))
