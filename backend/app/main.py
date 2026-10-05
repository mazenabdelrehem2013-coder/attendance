r"""FastAPI application entry point.

Run locally (from the backend folder):
    .venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware


def _serve_dashboard(app: FastAPI, folder: str) -> None:
    """The built React dashboard: files under /assets, and index.html for every other page
    (the dashboard does its own page routing). /api/... is never answered with the dashboard."""
    from pathlib import Path

    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    root = Path(folder).resolve()
    index = root / "index.html"
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def dashboard(path: str):
        if path == "api" or path.startswith("api/"):
            return JSONResponse({"error": {"code": "NOT_FOUND", "message": "Not found."}}, status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and root in candidate.parents:  # favicon etc., never outside root
            return FileResponse(candidate)
        return FileResponse(index)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    started = settings.run_scheduler_in_api and settings.app_env != "test"
    if started:
        from app.db.session import _api_session_factory
        from app.jobs import scheduler

        scheduler.start_in_background(_api_session_factory())
    yield
    if started:
        scheduler.stop_background()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        lifespan=lifespan,
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )
    app.add_middleware(RequestContextMiddleware)

    register_error_handlers(app)
    app.include_router(api_router)
    if settings.static_dir:
        _serve_dashboard(app, settings.static_dir)

    log = logging.getLogger("app")
    log.info("API started", extra={"environment": settings.app_env, "version": settings.app_version})
    if settings.is_production and settings.play_integrity_mode != "google":
        log.critical("SECURITY: Play Integrity is OFF in production (PLAY_INTEGRITY_MODE=google expected)")
    return app


app = create_app()
