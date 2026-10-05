"""Health checks used by Cloud Run, the load balancer and uptime monitoring. No login needed."""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])
log = logging.getLogger(__name__)


@router.get("", response_model=HealthResponse, summary="Is the API process running?")
def liveness() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", version=settings.app_version, environment=settings.app_env)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    summary="Can the API reach the database?",
)
def readiness(db: Session = Depends(get_db)):
    try:
        schema_version = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    except Exception:
        log.exception("Readiness check: database unavailable")
        body = ReadinessResponse(status="unavailable", database="unavailable", schema_version=None)
        return JSONResponse(body.model_dump(), status_code=503)
    return ReadinessResponse(status="ok", database="ok", schema_version=schema_version)
