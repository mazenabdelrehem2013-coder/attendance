"""Scheduled reports, ready to download (HR -> Scheduled reports & alerts).

A schedule says WHICH report, WHEN (daily / weekly / monthly at a local time), in which
FORMATS and for WHOM:
    HR / ADMIN -> the company-wide report
    MANAGER    -> every manager gets a report of their own team only

The files are saved in the database ("Ready reports" in the dashboard and the app) and the
people concerned get a bell alert. Nothing is emailed. Each scheduled time is created once
only, even if the scheduler runs twice or on two servers at the same time. Files are deleted
after REPORT_FILES_KEEP_DAYS (default 90).
"""

import logging
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core import clock
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Employee, Manager, Organization, ReportFile, ReportRun, ReportSetting, User
from app.models.enums import EmploymentStatus, NotificationEvent, ReportFormat, ReportRunStatus, Role
from app.schemas.schedules import RunResult, ScheduleIn, ScheduleOut
from app.services import reports
from app.services.audit import Actor, audit, write_audit
from app.services.cron import Cron
from app.services.exports.layout import ReportDocument
from app.services.notifications import add as add_alert
from app.services.notifications import rules as alert_rules
from app.services.exports.service import REPORT_TYPES, ExportRequest, document_for
from app.services.exports.service import render as render_file
from app.services.reports import ReportFilters

log = logging.getLogger("app.reports.scheduled")

# A scheduled time missed by more than this (server down) is skipped, not sent late.
MISSED_LIMIT = timedelta(hours=6)
_KIND = {v: k for k, v in REPORT_TYPES.items() if k != "period"}
_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_UI_FIELDS = ("frequency", "time", "days", "weekday", "day_of_month", "daily_period")


def to_cron(data: ScheduleIn) -> str:
    hour, minute = (int(x) for x in data.time.split(":"))
    if data.frequency == "daily":
        cron_days = ",".join(str((d + 1) % 7) for d in data.days)  # Monday=0 -> cron Monday=1
        return f"{minute} {hour} * * {cron_days}"
    if data.frequency == "weekly":
        return f"{minute} {hour} * * {(data.weekday + 1) % 7}"
    return f"{minute} {hour} {data.day_of_month} * *"


def describe(data: ScheduleIn) -> str:
    if data.frequency == "daily":
        if data.days == list(range(7)):
            days = "Every day"
        elif data.days == list(range(6)):
            days = "Monday to Saturday"
        elif data.days == list(range(5)):
            days = "Monday to Friday"
        else:
            days = ", ".join(_DAY_NAMES[d][:3] for d in data.days)
        return f"{days} at {data.time}"
    if data.frequency == "weekly":
        return f"Every {_DAY_NAMES[data.weekday]} at {data.time}"
    return f"Monthly on day {data.day_of_month} at {data.time}"


def _from_cron(expression: str) -> dict:
    """Form fields for a schedule saved with only a cron expression (e.g. by the dev seed)."""
    cron = Cron.parse(expression)
    minute, hour = min(cron.minutes), min(cron.hours)
    fields: dict = {"time": f"{hour:02d}:{minute:02d}"}
    if cron.days is not None:
        return {**fields, "frequency": "monthly", "day_of_month": min(min(cron.days), 28)}
    weekdays = sorted((d - 1) % 7 for d in cron.weekdays) if cron.weekdays is not None else list(range(7))
    if len(weekdays) == 1:
        return {**fields, "frequency": "weekly", "weekday": weekdays[0]}
    return {**fields, "frequency": "daily", "days": weekdays}


def _input(s: ReportSetting) -> ScheduleIn:
    f = {**_from_cron(s.cron_expression), **(s.filters or {})}
    return ScheduleIn(
        name=s.name, report=_KIND[s.report_type], formats=list(s.formats),
        recipient_roles=list(s.recipient_roles), is_enabled=s.is_enabled, location_id=f.get("location_id"), department_id=f.get("department_id"),
        **{k: f[k] for k in _UI_FIELDS if k in f},
    )


def to_out(s: ReportSetting) -> ScheduleOut:
    data = _input(s)
    nxt = Cron.parse(s.cron_expression).next(clock.now().astimezone(ZoneInfo(s.timezone))) if s.is_enabled else None
    return ScheduleOut(**data.model_dump(), id=s.id, description=describe(data), next_run_at=nxt,
                       last_run_at=s.last_scheduled_for, timezone=s.timezone)


def _apply(s: ReportSetting, data: ScheduleIn) -> None:
    s.name = data.name
    s.report_type = REPORT_TYPES[data.report]
    s.cron_expression = to_cron(data)
    s.formats = list(data.formats)
    s.recipient_roles = list(data.recipient_roles)
    s.extra_recipients = []
    s.is_enabled = data.is_enabled
    s.filters = {
        **data.model_dump(mode="json", include=set(_UI_FIELDS)),
        "location_id": str(data.location_id) if data.location_id else None,
        "department_id": str(data.department_id) if data.department_id else None,
    }


def _snapshot(s: ReportSetting) -> dict:
    return {"name": s.name, "report": s.report_type.value, "cron": s.cron_expression, "formats": list(s.formats),
            "recipient_roles": list(s.recipient_roles), "enabled": s.is_enabled, "filters": s.filters}


# --- CRUD -------------------------------------------------------------------------------------


def list_schedules(db: Session, user: User) -> list[ScheduleOut]:
    rows = db.scalars(select(ReportSetting).where(ReportSetting.organization_id == user.organization_id)
                      .order_by(ReportSetting.created_at))
    return [to_out(s) for s in rows]


def _get(db: Session, user: User, schedule_id: uuid.UUID, lock: bool = False) -> ReportSetting:
    query = select(ReportSetting).where(ReportSetting.id == schedule_id,
                                        ReportSetting.organization_id == user.organization_id)
    s = db.scalar(query.with_for_update() if lock else query)
    if s is None:
        raise AppError(404, "NOT_FOUND", "Scheduled report not found.")
    return s


def create(db: Session, actor: Actor, data: ScheduleIn) -> ScheduleOut:
    org = db.get(Organization, actor.user.organization_id)
    s = ReportSetting(organization_id=org.id, timezone=org.default_timezone, created_by=actor.user.id)
    _apply(s, data)
    db.add(s)
    db.flush()
    audit(db, actor, "REPORT_SCHEDULE_CREATED", "report_setting", s.id, new_value=_snapshot(s))
    db.commit()
    return to_out(s)


def update(db: Session, actor: Actor, schedule_id: uuid.UUID, data: ScheduleIn) -> ScheduleOut:
    s = _get(db, actor.user, schedule_id, lock=True)
    old = _snapshot(s)
    _apply(s, data)
    audit(db, actor, "REPORT_SCHEDULE_UPDATED", "report_setting", s.id, old_value=old, new_value=_snapshot(s))
    db.commit()
    return to_out(s)


def delete(db: Session, actor: Actor, schedule_id: uuid.UUID) -> None:
    s = _get(db, actor.user, schedule_id, lock=True)
    audit(db, actor, "REPORT_SCHEDULE_DELETED", "report_setting", s.id, old_value=_snapshot(s))
    for run in db.scalars(select(ReportRun).where(ReportRun.report_setting_id == s.id)):
        run.report_setting_id = None  # keep the history of what was sent
    db.delete(s)
    db.commit()


def run_now(db: Session, actor: Actor, schedule_id: uuid.UUID) -> RunResult:
    s = _get(db, actor.user, schedule_id, lock=True)
    count = _create(db, s, clock.now().astimezone(ZoneInfo(s.timezone)))
    audit(db, actor, "SCHEDULED_REPORT_CREATED", "report_setting", s.id, new_value={"files": count, "manual": True})
    db.commit()
    msg = f"{count} file(s) created. See Ready reports." if count else "Nobody to create it for (check 'For')."
    return RunResult(files_created=count, message=msg)


# --- Running ----------------------------------------------------------------------------------


def _org_reader(org_id: uuid.UUID) -> User:
    """A stand-in HR user for company-wide reports made by the scheduler. Never saved."""
    return User(id=uuid.UUID(int=0), organization_id=org_id, role=Role.HR, email="scheduler@system")


def _last_working_day(db: Session, reader: User, before: date) -> date:
    """Most recent day before `before` on which anyone was expected at work (skips Sundays,
    holidays, ...)."""
    for back in range(1, 8):
        day = before - timedelta(days=back)
        rows = reports.daily(db, reader, day, ReportFilters()).rows
        if any(r.status not in ("NON_WORKING_DAY", "HOLIDAY") for r in rows):
            return day
    return before - timedelta(days=1)


def _request(db: Session, s: ReportSetting, base: date) -> ExportRequest:
    data = _input(s)
    common = dict(location_id=data.location_id, department_id=data.department_id)
    last_month_end = base.replace(day=1) - timedelta(days=1)
    if data.report == "weekly":
        return ExportRequest(report="weekly", date=base - timedelta(days=7), **common)
    if data.report == "monthly":
        return ExportRequest(report="monthly", month=last_month_end.strftime("%Y-%m"), **common)
    if data.frequency == "daily":
        day = base if data.daily_period == "today" else _last_working_day(db, _org_reader(s.organization_id), base)
        if data.report == "daily":
            return ExportRequest(report="daily", date=day, **common)
        start = end = day
    elif data.frequency == "weekly":
        start, end = reports.week_range(base - timedelta(days=7))
    else:
        start, end = last_month_end.replace(day=1), last_month_end
    return ExportRequest(report=data.report, date_from=start, date_to=end, **common)


def _store_report(db: Session, s: ReportSetting, org: Organization, reader: User, req: ExportRequest,
                  owner: User | None, notify: list[User]) -> int:
    """Create the report as `reader` sees it and save one file per format.
    owner = the manager a team report belongs to (None = company-wide, for HR / Admin)."""
    doc: ReportDocument = document_for(db, reader, req)
    doc.timezone = org.default_timezone
    for fmt in s.formats:
        file = render_file(doc, ReportFormat(fmt))
        run = ReportRun(
            organization_id=org.id, report_setting_id=s.id, report_type=s.report_type, format=ReportFormat(fmt),
            requested_by=None, owner_user_id=owner.id if owner else None, status=ReportRunStatus.SUCCEEDED,
            row_count=len(doc.main.rows),
            parameters={**req.model_dump(mode="json", exclude_none=True), "title": doc.title, "period": doc.period,
                        "scope": doc.scope, "schedule": s.name},
            started_at=clock.now(), completed_at=clock.now(),
        )
        db.add(run)
        db.flush()
        db.add(ReportFile(report_run_id=run.id, filename=file.filename, media_type=file.media_type,
                          size_bytes=len(file.content), content=file.content))
    for user in notify:
        add_alert(db, user, NotificationEvent.REPORT_GENERATED, f"Report ready: {doc.title}",
                  f"{doc.period} - {doc.scope.lower()}. Open Reports to download it.", link="/reports?tab=ready")
    return len(s.formats)


def _create(db: Session, s: ReportSetting, fire: datetime) -> int:
    """Create the files of one scheduled time. Returns the number of files."""
    org = db.get(Organization, s.organization_id)
    req = _request(db, s, fire.date())
    roles = set(s.recipient_roles)
    alert = alert_rules(db, org.id)[NotificationEvent.REPORT_GENERATED]
    count = 0

    wanted = [Role(r) for r in roles if r in ("HR", "ADMIN")]
    if wanted:
        readers = list(db.scalars(select(User).where(
            User.organization_id == org.id, User.role.in_([Role(r) for r in alert.roles if r in ("HR", "ADMIN")]),
            User.role.in_(wanted), User.is_active)))
        count += _store_report(db, s, org, _org_reader(org.id), req, None, readers if alert.enabled else [])

    if "MANAGER" in roles:
        team_size = (select(func.count()).select_from(Employee)
                     .where(Employee.manager_id == Manager.id, Employee.employment_status == EmploymentStatus.ACTIVE)
                     .scalar_subquery())
        managers = db.scalars(
            select(Manager).join(User, User.id == Manager.user_id)
            .where(User.organization_id == org.id, Manager.is_active, User.is_active, team_size > 0)
            .order_by(User.email)
        )
        tell = alert.enabled and "MANAGER" in alert.roles
        for m in managers:
            count += _store_report(db, s, org, m.user, req, m.user, [m.user] if tell else [])
    return count


def purge_old_files(session_factory: sessionmaker) -> int:
    """Delete report files older than the company's keep period (Data retention -> Ready report
    files; REPORT_FILES_KEEP_DAYS if not set). The run records stay."""
    from app.services.retention import report_file_days

    deleted = 0
    with session_factory.begin() as db:
        for org_id in db.scalars(select(Organization.id)):
            cutoff = clock.now() - timedelta(days=report_file_days(db, org_id))
            deleted += db.execute(sql_delete(ReportFile).where(
                ReportFile.created_at < cutoff,
                ReportFile.report_run_id.in_(select(ReportRun.id).where(ReportRun.organization_id == org_id)),
            )).rowcount or 0
    return deleted


def run_due(session_factory: sessionmaker, now: datetime | None = None) -> int:
    """Create every scheduled report whose time has come. Returns the number of files created."""
    now = now or clock.now()
    with session_factory() as db:
        ids = list(db.scalars(select(ReportSetting.id).where(ReportSetting.is_enabled)))
    total = 0
    for setting_id in ids:
        with session_factory() as db:
            s = db.scalar(select(ReportSetting).where(ReportSetting.id == setting_id, ReportSetting.is_enabled)
                          .with_for_update(skip_locked=True))
            if s is None:
                continue
            fire = Cron.parse(s.cron_expression).previous(now.astimezone(ZoneInfo(s.timezone)))
            if fire is None or (s.last_scheduled_for and fire <= s.last_scheduled_for) or fire < s.created_at:
                continue
            s.last_scheduled_for = fire
            if now - fire > MISSED_LIMIT:
                log.warning("Scheduled report skipped (time missed)", extra={"schedule": s.name, "due": fire.isoformat()})
                db.commit()
                continue
            try:
                count = _create(db, s, fire)
                write_audit(db, action="SCHEDULED_REPORT_CREATED", organization_id=s.organization_id, actor_user_id=None,
                            actor_role="SYSTEM", object_type="report_setting", object_id=s.id,
                            new_value={"files": count, "scheduled_for": fire.isoformat()})
                db.commit()
                total += count
            except Exception as e:  # one broken schedule must not stop the others
                db.rollback()
                log.exception("Scheduled report failed", extra={"schedule_id": str(setting_id)})
                s = db.get(ReportSetting, setting_id)
                s.last_scheduled_for = fire  # don't retry every minute; HR sees the failed run
                db.add(ReportRun(organization_id=s.organization_id, report_setting_id=s.id,
                                 report_type=s.report_type, format=ReportFormat(s.formats[0]),
                                 status=ReportRunStatus.FAILED, error_message=str(e)[:1000],
                                 parameters={"scheduled_for": fire.isoformat()}, started_at=now,
                                 completed_at=clock.now()))
                db.commit()
    return total
