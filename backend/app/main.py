from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routes import build_health, router
from app.config import get_settings
from app.db.migrations import run_migrations
from app.db.session import engine, session_scope
from app.services.events import log_event
from app.services.scanner import ScannerService
from app.services.scheduler import ScannerScheduler
from app.services.settings_service import SettingsService
from app.utils.logging import configure_logging
from app.utils.time import utc_now


settings = get_settings()
configure_logging(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations(engine)
    settings_service = SettingsService(settings)
    with session_scope() as session:
        settings_service.initialize(session)
        interrupted_at = utc_now()
        result = session.execute(
            text(
                "UPDATE scans SET status = 'DEGRADED', errors_count = errors_count + 1, "
                "finished_at_utc = :finished_at, summary_es = :summary_es, summary_en = :summary_en "
                "WHERE status = 'RUNNING'"
            ),
            {
                "finished_at": interrupted_at.replace(tzinfo=None),
                "summary_es": "Scan interrumpido por reinicio del proceso.",
                "summary_en": "Scan interrupted by process restart.",
            },
        )
        if result.rowcount:
            log_event(
                session,
                message_es=f"Se cerraron {result.rowcount} scans interrumpidos",
                message_en=f"Closed {result.rowcount} interrupted scans",
                category="SYSTEM",
            )
        log_event(
            session,
            message_es="WeatherEdgeflow iniciado",
            message_en="WeatherEdgeflow started",
            category="SYSTEM",
        )
    scanner = ScannerService(settings, settings_service)
    scheduler = ScannerScheduler(scanner, settings_service)
    app.state.settings_service = settings_service
    app.state.scanner = scanner
    app.state.scheduler = scheduler
    scheduler.start()
    asyncio.create_task(scanner.run_once())
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.get("/health")
async def health_root() -> dict:
    request_scope = type("RequestShim", (), {"app": app})
    return await build_health(request_scope)  # type: ignore[arg-type]


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    index = frontend_dist / "index.html"
    requested = frontend_dist / full_path
    if frontend_dist.exists() and requested.is_file():
        return FileResponse(requested)
    if index.exists():
        return FileResponse(index)
    return JSONResponse(
        {
            "app": settings.app_name,
            "message": "Frontend has not been built yet. Run npm install && npm run build in frontend.",
        }
    )
