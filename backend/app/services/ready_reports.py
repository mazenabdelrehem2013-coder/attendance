"""Ready reports: files created by scheduled reports, listed and downloaded in the dashboard
and the Android app.

    HR / ADMIN -> company-wide files of their organization
    MANAGER    -> only the team files made for them
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import ReportFile, ReportRun, User
from app.models.enums import Role
from app.schemas.schedules import ReadyReport, ReadyReportList
from app.services.audit import Actor, audit
from app.services.exports.service import ExportFile
from app.services.retention import report_file_days


def _visible(user: User):
    """SQL condition: report runs this user may download."""
    in_org = ReportRun.organization_id == user.organization_id
    if user.role in (Role.HR, Role.ADMIN):
        return in_org & ReportRun.owner_user_id.is_(None)
    return in_org & (ReportRun.owner_user_id == user.id)


def list_ready(db: Session, user: User, limit: int, offset: int) -> ReadyReportList:
    query = select(ReportFile, ReportRun).join(ReportRun, ReportRun.id == ReportFile.report_run_id).where(_visible(user))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(
        query.with_only_columns(  # never load the file contents for a list
            ReportFile.id, ReportFile.filename, ReportFile.size_bytes, ReportFile.created_at,
            ReportRun.format, ReportRun.row_count, ReportRun.parameters,
        ).order_by(ReportFile.created_at.desc(), ReportFile.filename).limit(limit).offset(offset)
    ).all()
    return ReadyReportList(
        items=[ReadyReport(
            id=r.id, title=r.parameters.get("title", "Report"), period=r.parameters.get("period", ""),
            scope=r.parameters.get("scope", ""), schedule_name=r.parameters.get("schedule"), format=r.format.value,
            filename=r.filename, size_bytes=r.size_bytes, rows=r.row_count, created_at=r.created_at,
        ) for r in rows],
        total=total, keep_days=report_file_days(db, user.organization_id),
    )


def download(db: Session, actor: Actor, file_id: uuid.UUID) -> ExportFile:
    row = db.execute(
        select(ReportFile, ReportRun).join(ReportRun, ReportRun.id == ReportFile.report_run_id)
        .where(ReportFile.id == file_id, _visible(actor.user))
    ).first()
    if row is None:  # same answer whether it doesn't exist or isn't yours
        raise AppError(404, "NOT_FOUND", "Report not found (it may have been deleted after the keep period).")
    file, run = row
    audit(db, actor, "REPORT_DOWNLOADED", "report_file", file.id,
          new_value={"filename": file.filename, "report_run_id": str(run.id)})
    db.commit()
    return ExportFile(file.content, file.media_type, file.filename)
