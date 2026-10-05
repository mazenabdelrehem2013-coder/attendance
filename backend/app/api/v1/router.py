"""All version-1 endpoints are mounted under /api/v1."""

from fastapi import APIRouter

from app.api.v1.routes import attendance, auth, employees, health, hr, manager, org, qr, reports, schedules, security

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(employees.router)
api_router.include_router(org.router)
api_router.include_router(attendance.router)
api_router.include_router(qr.router)
api_router.include_router(manager.router)
api_router.include_router(manager.hr_router)
api_router.include_router(hr.router)
api_router.include_router(reports.router)
api_router.include_router(schedules.router)
api_router.include_router(security.router)
