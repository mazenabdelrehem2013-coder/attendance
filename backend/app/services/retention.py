"""Data retention: how long each kind of data is kept, and the nightly clean-up.

    RAW_LOCATION     GPS coordinates of check-ins are removed (distance, result and time stay)
    SECURITY_EVENTS  deleted
    AUDIT_LOGS       the OLDEST entries are deleted (the chain of the rest stays verifiable).
                     The chain is shared by all companies in the database, so the longest keep
                     period of any company is used and only a prefix of the chain is removed.
    NOTIFICATIONS    bell alerts deleted
    REPORT_FILES     scheduled report files deleted
    ATTENDANCE       never deleted automatically (labour law); shown for information

The clean-up must connect as the database OWNER: the API's own role cannot delete or change
these tables at all, and even the owner can only do it after explicitly switching on
app.allow_purge / app.allow_redact for that one transaction (database triggers, 0002 / 0007).
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.core import clock
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import (
    AttendanceEvent,
    AuditLog,
    Employee,
    Notification,
    Organization,
    ReportFile,
    ReportRun,
    RetentionSetting,
    SecurityEvent,
    User,
)
from app.models.enums import RetentionCategory as C
from app.schemas.security import RetentionItem, RetentionRun, RetentionUpdate
from app.services.audit import Actor, audit, write_audit

log = logging.getLogger("app.retention")

# label, description, default days, minimum days, deleted automatically?
INFO: dict[C, tuple[str, str, int, int, bool]] = {
    C.ATTENDANCE: ("Attendance records", "Check-ins, check-outs and daily records. Kept; never deleted automatically.",
                   2555, 365, False),
    C.RAW_LOCATION: ("GPS coordinates", "Exact position of each check-in. After this, only the distance to the "
                     "office and the result are kept.", 365, 30, True),
    C.SECURITY_EVENTS: ("Security events", "Failed logins, fake-GPS detections and other security events.",
                        730, 90, True),
    C.AUDIT_LOGS: ("Audit log", "Who changed what. The oldest entries are removed first.", 2555, 365, True),
    C.NOTIFICATIONS: ("Bell alerts", "Alerts shown under the bell icon.", 180, 30, True),
    C.REPORT_FILES: ("Ready report files", "Files created by scheduled reports.", 90, 30, True),
}


def days_for(db: Session, org_id, category: C) -> int:
    stored = db.scalar(select(RetentionSetting.retain_days).where(
        RetentionSetting.organization_id == org_id, RetentionSetting.data_category == category))
    return stored if stored is not None else INFO[category][2]


def report_file_days(db: Session, org_id) -> int:
    """Ready report files: the company's setting, else REPORT_FILES_KEEP_DAYS."""
    stored = db.scalar(select(RetentionSetting.retain_days).where(
        RetentionSetting.organization_id == org_id, RetentionSetting.data_category == C.REPORT_FILES))
    return stored if stored is not None else get_settings().report_files_keep_days


def settings(db: Session, user: User) -> list[RetentionItem]:
    return [
        RetentionItem(category=c, label=label, description=desc,
                      retain_days=report_file_days(db, user.organization_id) if c == C.REPORT_FILES
                      else days_for(db, user.organization_id, c),
                      min_days=minimum, automatic=auto)
        for c, (label, desc, _, minimum, auto) in INFO.items()
    ]


def update_setting(db: Session, actor: Actor, category: C, data: RetentionUpdate) -> RetentionItem:
    label, desc, _, minimum, auto = INFO[category]
    if data.retain_days < minimum:
        raise AppError(422, "VALIDATION_ERROR", f"{label} must be kept at least {minimum} days.")
    org_id = actor.user.organization_id
    row = db.scalar(select(RetentionSetting).where(
        RetentionSetting.organization_id == org_id, RetentionSetting.data_category == category))
    old = row.retain_days if row else None
    if row is None:
        row = RetentionSetting(organization_id=org_id, data_category=category, retain_days=data.retain_days)
        db.add(row)
    row.retain_days = data.retain_days
    audit(db, actor, "RETENTION_CHANGED", "retention_setting", category.value,
          old_value={"retain_days": old}, new_value={"retain_days": data.retain_days})
    db.commit()
    return RetentionItem(category=category, label=label, description=desc, retain_days=data.retain_days,
                         min_days=minimum, automatic=auto)


def _purge_org(db: Session, org_id, now: datetime) -> dict[str, int]:
    """Run inside ONE owner transaction with allow_purge / allow_redact switched on."""
    cutoff = {c: now - timedelta(days=days_for(db, org_id, c)) for c in INFO}
    cutoff[C.REPORT_FILES] = now - timedelta(days=report_file_days(db, org_id))
    employees = select(Employee.id).where(Employee.organization_id == org_id)
    users = select(User.id).where(User.organization_id == org_id)
    done: dict[str, int] = {}

    done[C.RAW_LOCATION.value] = db.execute(
        update(AttendanceEvent)
        .where(AttendanceEvent.employee_id.in_(employees), AttendanceEvent.server_received_at < cutoff[C.RAW_LOCATION],
               AttendanceEvent.latitude.is_not(None))
        .values(latitude=None, longitude=None, accuracy_m=None)
        .execution_options(synchronize_session=False)
    ).rowcount
    done[C.SECURITY_EVENTS.value] = db.execute(
        delete(SecurityEvent).where(SecurityEvent.organization_id == org_id,
                                    SecurityEvent.created_at < cutoff[C.SECURITY_EVENTS])
    ).rowcount
    done[C.NOTIFICATIONS.value] = db.execute(
        delete(Notification).where(Notification.user_id.in_(users), Notification.created_at < cutoff[C.NOTIFICATIONS])
    ).rowcount
    done[C.REPORT_FILES.value] = db.execute(
        delete(ReportFile).where(ReportFile.created_at < cutoff[C.REPORT_FILES], ReportFile.report_run_id.in_(
            select(ReportRun.id).where(ReportRun.organization_id == org_id)))
    ).rowcount
    return done


def _purge_audit(db: Session, orgs: list[Organization], now: datetime) -> int:
    """Delete the oldest audit entries - always a prefix of the chain, for all companies at once."""
    keep = max((days_for(db, o.id, C.AUDIT_LOGS) for o in orgs), default=INFO[C.AUDIT_LOGS][2])
    cutoff = now - timedelta(days=keep)
    first_kept = db.scalar(select(func.min(AuditLog.seq)).where(AuditLog.created_at >= cutoff))
    if first_kept is None:
        return 0  # every entry is old: keep them rather than empty the log
    return db.execute(delete(AuditLog).where(AuditLog.seq < first_kept)).rowcount


def purge(owner_factory: sessionmaker, now: datetime | None = None) -> dict[str, dict[str, int]]:
    """Nightly clean-up for every company. `owner_factory` must connect as the OWNER role."""
    now = now or clock.now()
    with owner_factory() as db:
        orgs = list(db.scalars(select(Organization).where(Organization.is_active)))
    with owner_factory.begin() as db:
        db.execute(text("SET LOCAL app.allow_purge = 'on'"))
        audit_removed = _purge_audit(db, orgs, now)
    results = {}
    for org in orgs:
        with owner_factory.begin() as db:
            db.execute(text("SET LOCAL app.allow_purge = 'on'"))
            db.execute(text("SET LOCAL app.allow_redact = 'on'"))
            done = {**_purge_org(db, org.id, now), C.AUDIT_LOGS.value: audit_removed}
            write_audit(db, action="RETENTION_PURGE", organization_id=org.id, actor_user_id=None,
                        actor_role="SYSTEM", object_type="retention", object_id=now.date().isoformat(),
                        new_value=done)
        results[str(org.id)] = done
        if any(done.values()):
            log.info("Retention clean-up", extra={"organization_id": str(org.id), **done})
    return results


def last_run(db: Session, user: User) -> RetentionRun | None:
    row = db.scalar(select(AuditLog).where(AuditLog.organization_id == user.organization_id,
                                           AuditLog.action == "RETENTION_PURGE").order_by(AuditLog.seq.desc()).limit(1))
    return RetentionRun(ran_at=row.created_at, results=row.new_value or {}) if row else None
