"""Build a report and turn it into an Excel or PDF file. Every export is recorded
(report_runs + audit log): who exported what, with which filters, how many rows."""

import uuid
from dataclasses import dataclass
import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import clock
from app.models import Organization, ReportRun, User
from app.models.enums import ReportFormat, ReportRunStatus, ReportType, Role
from app.services import reports
from app.services.audit import Actor, audit
from app.services.exports.excel import build_excel
from app.services.exports.layout import ReportDocument, from_daily, from_list, from_period
from app.services.exports.pdf import build_pdf
from app.services.reports import ReportFilters
from app.services.team_attendance import org_today

ExportKind = Literal["daily", "weekly", "monthly", "period", "late", "absence", "suspicious"]

REPORT_TYPES = {
    "daily": ReportType.DAILY, "weekly": ReportType.WEEKLY, "monthly": ReportType.MONTHLY,
    "period": ReportType.EMPLOYEE, "late": ReportType.LATE, "absence": ReportType.ABSENCE,
    "suspicious": ReportType.SUSPICIOUS,
}

MEDIA = {
    ReportFormat.EXCEL: ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    ReportFormat.PDF: ("application/pdf", "pdf"),
}


class ExportRequest(BaseModel):
    report: ExportKind
    date: dt.date | None = Field(None, description="daily / weekly")
    month: str | None = Field(None, pattern=r"^\d{4}-\d{2}$", description="monthly, e.g. 2026-10")
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    department_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None


@dataclass
class ExportFile:
    content: bytes
    media_type: str
    filename: str


def build_document(db: Session, actor: Actor, req: ExportRequest) -> ReportDocument:
    return document_for(db, actor.user, req)


def document_for(db: Session, user: User, req: ExportRequest) -> ReportDocument:
    """The report as `user` may see it (a manager: only their team)."""
    org = db.get(Organization, user.organization_id)
    company = (org.settings or {}).get("report_company_name") or org.name
    scope = "Your team" if user.role == Role.MANAGER else "All employees"
    f = ReportFilters(req.department_id, req.location_id, req.manager_id, req.employee_id)
    today = org_today(db, user)
    end = req.date_to or today
    start = req.date_from or end.replace(day=1)

    if req.report == "daily":
        return from_daily(reports.daily(db, user, req.date or today, f), company, scope)
    if req.report == "weekly":
        s, e = reports.week_range(req.date or today)
        return from_period(reports.period(db, user, s, e, f, "Weekly attendance report"), company, scope, "weekly")
    if req.report == "monthly":
        s, e = reports.month_range(req.month or today.strftime("%Y-%m"))
        return from_period(reports.period(db, user, s, e, f, "Monthly attendance report"), company, scope, "monthly")
    if req.report == "period":
        return from_period(reports.period(db, user, start, end, f, "Attendance report"), company, scope, "period")
    builder = {"late": reports.late_list, "absence": reports.absence_list, "suspicious": reports.suspicious_list}
    return from_list(builder[req.report](db, user, start, end, f), company, scope, req.report)


def render(doc: ReportDocument, fmt: ReportFormat) -> ExportFile:
    content = build_excel(doc) if fmt == ReportFormat.EXCEL else build_pdf(doc)
    media, ext = MEDIA[fmt]
    return ExportFile(content, media, f"{doc.file_stem}.{ext}")


def export(db: Session, actor: Actor, req: ExportRequest, fmt: ReportFormat) -> ExportFile:
    doc = build_document(db, actor, req)
    doc.timezone = db.get(Organization, actor.user.organization_id).default_timezone
    file = render(doc, fmt)
    params = req.model_dump(mode="json", exclude_none=True)
    run = ReportRun(
        organization_id=actor.user.organization_id, report_type=REPORT_TYPES[req.report], format=fmt,
        requested_by=actor.user.id, parameters=params, status=ReportRunStatus.SUCCEEDED,
        row_count=len(doc.main.rows), started_at=clock.now(), completed_at=clock.now(),
    )
    db.add(run)
    db.flush()
    audit(db, actor, "REPORT_EXPORTED", "report_run", run.id,
          new_value={"format": fmt.value, "report": req.report, "rows": len(doc.main.rows), "filters": params})
    db.commit()
    return file
