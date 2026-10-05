"""Reports. Managers get their own team, HR/Admin everyone (same scoping as the dashboard).
Every report can be downloaded as Excel or PDF; downloads are recorded in the audit log."""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import actor_with_roles, require_roles
from app.db.session import get_db
from app.models import User
from app.models.enums import ReportFormat, Role
from app.schemas.reports import DailyReport, ListReport, PeriodReport
from app.schemas.schedules import ReadyReportList
from app.services import ready_reports as ready
from app.services import reports
from app.services.audit import Actor
from app.services.exports import service as exports
from app.services.exports.service import ExportRequest
from app.services.reports import ReportFilters
from app.services.team_attendance import org_today

router = APIRouter(prefix="/reports", tags=["reports"])
staff = require_roles(Role.MANAGER, Role.HR)


def _filters(
    department_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    manager_id: uuid.UUID | None = None,
    employee_id: uuid.UUID | None = None,
) -> ReportFilters:
    return ReportFilters(department_id, location_id, manager_id, employee_id)


def _range(db: Session, user: User, date_from: date | None, date_to: date | None, default_days: int):
    end = date_to or org_today(db, user)
    return date_from or end - timedelta(days=default_days - 1), end


@router.get("/daily", response_model=DailyReport)
def daily(day: date | None = Query(None, alias="date"), f: ReportFilters = Depends(_filters),
          user: User = Depends(staff), db: Session = Depends(get_db)):
    return reports.daily(db, user, day or org_today(db, user), f)


@router.get("/weekly", response_model=PeriodReport, summary="Monday-Sunday week containing the date")
def weekly(day: date | None = Query(None, alias="date"), f: ReportFilters = Depends(_filters),
           user: User = Depends(staff), db: Session = Depends(get_db)):
    start, end = reports.week_range(day or org_today(db, user))
    return reports.period(db, user, start, end, f, "Weekly attendance report")


@router.get("/monthly", response_model=PeriodReport, summary="Per-employee monthly figures")
def monthly(month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$", description="e.g. 2026-10 (default: this month)"),
            f: ReportFilters = Depends(_filters), user: User = Depends(staff), db: Session = Depends(get_db)):
    start, end = reports.month_range(month or org_today(db, user).strftime("%Y-%m"))
    return reports.period(db, user, start, end, f, "Monthly attendance report")


@router.get("/period", response_model=PeriodReport, summary="Any period (employee, location, department, manager reports via filters)")
def any_period(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
               f: ReportFilters = Depends(_filters), user: User = Depends(staff), db: Session = Depends(get_db)):
    start, end = _range(db, user, date_from, date_to, 30)
    return reports.period(db, user, start, end, f, "Attendance report")


@router.get("/late", response_model=ListReport)
def late(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
         f: ReportFilters = Depends(_filters), user: User = Depends(staff), db: Session = Depends(get_db)):
    return reports.late_list(db, user, *_range(db, user, date_from, date_to, 30), f)


@router.get("/absence", response_model=ListReport)
def absence(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
            f: ReportFilters = Depends(_filters), user: User = Depends(staff), db: Session = Depends(get_db)):
    return reports.absence_list(db, user, *_range(db, user, date_from, date_to, 30), f)


@router.get("/suspicious", response_model=ListReport)
def suspicious(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
               f: ReportFilters = Depends(_filters), user: User = Depends(staff), db: Session = Depends(get_db)):
    return reports.suspicious_list(db, user, *_range(db, user, date_from, date_to, 30), f)


def _download(file: exports.ExportFile) -> Response:
    return Response(
        content=file.content,
        media_type=file.media_type,
        headers={"Content-Disposition": f'attachment; filename="{file.filename}"'},
    )


@router.post("/export/excel", summary="Download a report as an Excel file")
def export_excel(body: ExportRequest, actor: Actor = Depends(actor_with_roles(Role.MANAGER, Role.HR)),
                 db: Session = Depends(get_db)):
    return _download(exports.export(db, actor, body, ReportFormat.EXCEL))


@router.post("/export/pdf", summary="Download a report as a PDF file")
def export_pdf(body: ExportRequest, actor: Actor = Depends(actor_with_roles(Role.MANAGER, Role.HR)),
               db: Session = Depends(get_db)):
    return _download(exports.export(db, actor, body, ReportFormat.PDF))


# --- Ready reports (created by scheduled reports) -------------------------------------------


@router.get("/ready", response_model=ReadyReportList,
            summary="Report files created by schedules (HR: company-wide, manager: own team)")
def ready_reports(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(staff),
    db: Session = Depends(get_db),
):
    return ready.list_ready(db, user, limit, offset)


@router.get("/ready/{file_id}/download", summary="Download one ready report file")
def download_ready(file_id: uuid.UUID, actor: Actor = Depends(actor_with_roles(Role.MANAGER, Role.HR)),
                   db: Session = Depends(get_db)):
    return _download(ready.download(db, actor, file_id))
