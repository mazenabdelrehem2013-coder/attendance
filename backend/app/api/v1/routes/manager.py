"""Manager dashboard: the team's attendance for a day, and a CSV export.

Managers get only their own team; HR and admins get everyone (same scoping rule as
everywhere else - see services/scope.py). Read-only: nothing here changes data.
"""

import csv
import io
import uuid
from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import actor_with_roles, require_roles
from app.core.errors import AppError
from app.db.session import get_db
from app.models import Organization, User
from app.models.enums import Role
from app.schemas.team import TeamAttendance
from app.services.audit import Actor, audit
from app.services.team_attendance import ALL_STATUSES, TeamFilters, org_today, team_day

router = APIRouter(prefix="/manager", tags=["manager"])
hr_router = APIRouter(prefix="/hr", tags=["hr"])
staff = require_roles(Role.MANAGER, Role.HR)

STATUS_FILTERS = (*ALL_STATUSES, "CHECKED_IN", "MISSING_CHECKOUT", "SUSPICIOUS")


def _filters(
    q: str | None = Query(None, max_length=100, description="Name or employee ID"),
    employee_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    status: list[str] | None = Query(None, description=f"Any of: {', '.join(STATUS_FILTERS)}"),
) -> TeamFilters:
    if status:
        unknown = [s for s in status if s not in STATUS_FILTERS]
        if unknown:
            raise AppError(422, "VALIDATION_ERROR", f"Unknown status: {', '.join(unknown)}")
    return TeamFilters(q, employee_id, department_id, location_id, status)


@router.get("/attendance", response_model=TeamAttendance, summary="Team attendance for one day")
@hr_router.get("/attendance", response_model=TeamAttendance, summary="Company attendance for one day (HR)")
def team_attendance(
    day: date | None = Query(None, alias="date", description="Default: today"),
    filters: TeamFilters = Depends(_filters),
    user: User = Depends(staff),
    db: Session = Depends(get_db),
):
    return team_day(db, user, day or org_today(db, user), filters)


def _csv_cell(value) -> str:
    """Values starting with = + - @ would run as formulas in Excel ("CSV injection")."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/attendance/export.csv", summary="Download the team attendance as CSV (opens in Excel)")
def export_csv(
    day: date | None = Query(None, alias="date"),
    filters: TeamFilters = Depends(_filters),
    actor: Actor = Depends(actor_with_roles(Role.MANAGER, Role.HR)),
    db: Session = Depends(get_db),
):
    day = day or org_today(db, actor.user)
    data = team_day(db, actor.user, day, filters)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Employee", "Employee ID", "Department", "Location", "Check-in", "Check-out",
                     "Worked (h:mm)", "Status", "Departure", "Verification"])
    tz = ZoneInfo(db.get(Organization, actor.user.organization_id).default_timezone)

    def fmt(t):
        return t.astimezone(tz).strftime("%H:%M") if t else ""

    for r in data.rows:
        writer.writerow([_csv_cell(v) for v in (
            r.full_name, r.employee_code, r.department, r.location, fmt(r.check_in), fmt(r.check_out),
            f"{r.worked_minutes // 60}:{r.worked_minutes % 60:02d}", r.status, r.departure_status,
            r.verification_status,
        )])
    audit(db, actor, "REPORT_EXPORTED", "team_attendance", day.isoformat(),
          new_value={"format": "CSV", "rows": len(data.rows), "filters": {
              k: str(v) for k, v in vars(filters).items() if v}})
    db.commit()
    # UTF-8 with BOM so Excel shows names with accents correctly.
    return Response(
        content="﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="attendance-{day.isoformat()}.csv"'},
    )
