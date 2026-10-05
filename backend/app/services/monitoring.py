"""Security monitoring: alert rules over the security events, the alerts they raise, and the
numbers for the security dashboard.

The scheduler evaluates every rule each minute. A rule produces a finding per subject (an
account, an IP address, an employee...). While an alert for that rule + subject is open or
acknowledged it is updated, not duplicated; after HR resolves it, a NEW alert appears only if
new events happen after the resolution.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core import clock
from app.core.errors import AppError
from app.models import Employee, Organization, SecurityAlert, SecurityEvent, User
from app.models.enums import AlertStatus, NotificationEvent, Severity
from app.schemas.security import (
    AlertAction,
    AlertOut,
    AlertPage,
    CountItem,
    DayCount,
    RuleInfo,
    SecurityOverview,
)
from app.services.audit import Actor, audit
from app.services.audit_viewer import last_check
from app.services.notifications import add as add_alert
from app.services.notifications import rules as alert_rules

log = logging.getLogger("app.security.monitoring")


@dataclass(frozen=True)
class Rule:
    label: str
    severity: Severity
    description: str
    window: timedelta
    threshold: int


RULES: dict[str, Rule] = {
    "ACCOUNT_LOCKED": Rule(
        "Account locked", Severity.HIGH,
        "An account was locked after 5 wrong passwords in a row (someone may be guessing it).",
        timedelta(hours=24), 1),
    "LOGIN_ATTACK_IP": Rule(
        "Many failed logins from one address", Severity.HIGH,
        "20 or more failed logins from one internet address within 15 minutes, on any accounts.",
        timedelta(minutes=15), 20),
    "TOKEN_REUSE": Rule(
        "Possible stolen session", Severity.HIGH,
        "A login session token was used twice. The session was ended for safety; the person must log in again.",
        timedelta(hours=24), 1),
    "PHONE_SHARED": Rule(
        "Phone used by two employees", Severity.HIGH,
        "An employee tried to register a phone that already belongs to another employee.",
        timedelta(hours=24), 1),
    "REPEATED_SPOOFING": Rule(
        "Repeated fake location or tampering", Severity.HIGH,
        "3 or more serious check-in problems (fake GPS app, modified app or phone, bad signature, "
        "copied request) by one employee within 24 hours.",
        timedelta(hours=24), 3),
    "SUSPICIOUS_SPIKE": Rule(
        "Unusual number of suspicious check-ins", Severity.MEDIUM,
        "15 or more check-in security events across the company within one hour.",
        timedelta(hours=1), 15),
    "AUDIT_TAMPERING": Rule(
        "Audit log tampering", Severity.CRITICAL,
        "The nightly check found that audit log entries were changed or deleted outside the system.",
        timedelta(days=1), 1),
}

SERIOUS_ATTENDANCE_EVENTS = ("MOCK_LOCATION", "INTEGRITY_FAIL", "BAD_SIGNATURE", "REPLAY")


@dataclass
class Finding:
    rule: str
    subject_key: str
    title: str
    count: int
    first_at: datetime
    last_at: datetime
    details: dict = field(default_factory=dict)
    employee_id: uuid.UUID | None = None


def rule_list() -> list[RuleInfo]:
    return [RuleInfo(rule=k, label=r.label, severity=r.severity, description=r.description) for k, r in RULES.items()]


# --- Evaluating rules -------------------------------------------------------------------------


def _grouped(db: Session, org_id: uuid.UUID, since: datetime, types, key, *, include_orgless=False, extra=None):
    """(key value, count, first, last) per subject for security events of `types` since `since`."""
    in_org = SecurityEvent.organization_id == org_id
    if include_orgless:
        in_org = or_(in_org, SecurityEvent.organization_id.is_(None))
    query = (select(key, func.count(), func.min(SecurityEvent.created_at), func.max(SecurityEvent.created_at))
             .where(in_org, SecurityEvent.created_at >= since, SecurityEvent.event_type.in_(types), key.is_not(None))
             .group_by(key))
    if extra is not None:
        query = query.where(extra)
    return db.execute(query).all()


def evaluate(db: Session, org_id: uuid.UUID, now: datetime) -> list[Finding]:
    found: list[Finding] = []

    def since(rule: str) -> datetime:
        return now - RULES[rule].window

    users = lambda ids: {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}  # noqa: E731
    emps = lambda ids: {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_(ids)))} if ids else {}  # noqa: E731

    locked = _grouped(db, org_id, since("ACCOUNT_LOCKED"), ["LOGIN_FAILED"], SecurityEvent.user_id,
                      extra=SecurityEvent.details["locked"].astext == "true")
    by_id = users([r[0] for r in locked])
    for user_id, n, first, last in locked:
        u = by_id[user_id]
        found.append(Finding("ACCOUNT_LOCKED", f"user:{user_id}", f"Account locked: {u.email}", n, first, last,
                             {"email": u.email}))

    ips = _grouped(db, org_id, since("LOGIN_ATTACK_IP"), ["LOGIN_FAILED"], SecurityEvent.ip_address,
                   include_orgless=True)
    for ip, n, first, last in ips:
        if n >= RULES["LOGIN_ATTACK_IP"].threshold:
            found.append(Finding("LOGIN_ATTACK_IP", f"ip:{ip}", f"{n} failed logins from {ip} in 15 minutes",
                                 n, first, last, {"ip_address": str(ip)}))

    reused = _grouped(db, org_id, since("TOKEN_REUSE"), ["REFRESH_TOKEN_REUSE"], SecurityEvent.user_id)
    by_id = users([r[0] for r in reused])
    for user_id, n, first, last in reused:
        u = by_id[user_id]
        found.append(Finding("TOKEN_REUSE", f"user:{user_id}", f"Possible stolen session: {u.email}", n, first, last,
                             {"email": u.email}))

    shared = _grouped(db, org_id, since("PHONE_SHARED"), ["DEVICE_SHARED"], SecurityEvent.employee_id)
    by_id = emps([r[0] for r in shared])
    for emp_id, n, first, last in shared:
        e = by_id[emp_id]
        found.append(Finding("PHONE_SHARED", f"employee:{emp_id}",
                             f"{e.full_name} tried to use another employee's phone", n, first, last,
                             {"employee": e.full_name, "employee_code": e.employee_code}, e.id))

    spoof = _grouped(db, org_id, since("REPEATED_SPOOFING"), SERIOUS_ATTENDANCE_EVENTS, SecurityEvent.employee_id)
    by_id = emps([r[0] for r in spoof if r[1] >= RULES["REPEATED_SPOOFING"].threshold])
    for emp_id, n, first, last in spoof:
        if n >= RULES["REPEATED_SPOOFING"].threshold:
            e = by_id[emp_id]
            types = list(db.scalars(select(SecurityEvent.event_type).distinct().where(
                SecurityEvent.employee_id == emp_id, SecurityEvent.created_at >= since("REPEATED_SPOOFING"),
                SecurityEvent.event_type.in_(SERIOUS_ATTENDANCE_EVENTS))))
            found.append(Finding("REPEATED_SPOOFING", f"employee:{emp_id}",
                                 f"{e.full_name}: {n} serious check-in problems in 24 hours", n, first, last,
                                 {"employee": e.full_name, "employee_code": e.employee_code, "types": sorted(types)},
                                 e.id))

    spike = db.execute(
        select(func.count(), func.min(SecurityEvent.created_at), func.max(SecurityEvent.created_at))
        .where(SecurityEvent.organization_id == org_id, SecurityEvent.employee_id.is_not(None),
               SecurityEvent.created_at >= since("SUSPICIOUS_SPIKE"))
    ).one()
    if spike[0] >= RULES["SUSPICIOUS_SPIKE"].threshold:
        found.append(Finding("SUSPICIOUS_SPIKE", "company", f"{spike[0]} check-in security events in the last hour",
                             spike[0], spike[1], spike[2]))
    return found


def raise_alert(db: Session, org_id: uuid.UUID, f: Finding) -> SecurityAlert | None:
    """Create or update the alert for a finding. Returns the alert if it is NEW."""
    rule = RULES[f.rule]
    active = db.scalar(select(SecurityAlert).where(
        SecurityAlert.organization_id == org_id, SecurityAlert.rule == f.rule,
        SecurityAlert.subject_key == f.subject_key, SecurityAlert.status != AlertStatus.RESOLVED))
    if active is not None:
        if f.last_at > active.last_seen_at:
            active.last_seen_at, active.count, active.title = f.last_at, f.count, f.title
            active.details = {**active.details, **f.details}
        return None
    resolved_at = db.scalar(select(func.max(SecurityAlert.handled_at)).where(
        SecurityAlert.organization_id == org_id, SecurityAlert.rule == f.rule,
        SecurityAlert.subject_key == f.subject_key, SecurityAlert.status == AlertStatus.RESOLVED))
    if resolved_at is not None and f.last_at <= resolved_at:
        return None  # already handled; nothing new since
    alert = SecurityAlert(organization_id=org_id, rule=f.rule, subject_key=f.subject_key, severity=rule.severity,
                          title=f.title[:300], details=f.details, employee_id=f.employee_id, count=f.count,
                          first_seen_at=f.first_at, last_seen_at=f.last_at)
    db.add(alert)
    db.flush()
    notify_rule = alert_rules(db, org_id)[NotificationEvent.SECURITY_ALERT]
    if notify_rule.enabled:
        roles = [r for r in notify_rule.roles if r in ("HR", "ADMIN")]
        for user in db.scalars(select(User).where(User.organization_id == org_id, User.is_active,
                                                  User.role.in_(roles))):
            add_alert(db, user, NotificationEvent.SECURITY_ALERT, f"Security alert: {f.title}"[:200],
                      rule.description, link="/security", dedupe_key=f"security-alert:{alert.id}")
    # Structured log line: Cloud Monitoring alerts on these in production (Phase 18).
    log.warning("SECURITY_ALERT", extra={"security_alert": True, "rule": f.rule, "severity": rule.severity.value,
                                         "organization_id": str(org_id), "alert_id": str(alert.id)})
    return alert


def run_rules(session_factory: sessionmaker, now: datetime | None = None) -> int:
    """Evaluate every rule for every company. Returns the number of NEW alerts."""
    now = now or clock.now()
    with session_factory() as db:
        orgs = list(db.scalars(select(Organization.id).where(Organization.is_active)))
    new = 0
    for org_id in orgs:
        with session_factory() as db:
            try:
                new += sum(raise_alert(db, org_id, f) is not None for f in evaluate(db, org_id, now))
                db.commit()
            except Exception:
                db.rollback()
                log.exception("Security rules failed", extra={"organization_id": str(org_id)})
    return new


# --- Alerts for HR ----------------------------------------------------------------------------


def _alert_out(a: SecurityAlert, emp: Employee | None, handler: User | None) -> AlertOut:
    return AlertOut(
        id=a.id, rule=a.rule, rule_label=RULES[a.rule].label if a.rule in RULES else a.rule, severity=a.severity,
        title=a.title, details=a.details, employee_id=a.employee_id, employee_name=emp.full_name if emp else None,
        count=a.count, first_seen_at=a.first_seen_at, last_seen_at=a.last_seen_at, status=a.status,
        handled_by=handler.email if handler else None, handled_at=a.handled_at, note=a.note,
    )


def _alert_query(user: User):
    return (select(SecurityAlert, Employee, User)
            .outerjoin(Employee, Employee.id == SecurityAlert.employee_id)
            .outerjoin(User, User.id == SecurityAlert.handled_by)
            .where(SecurityAlert.organization_id == user.organization_id))


_SEVERITY_ORDER = case({"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}, value=SecurityAlert.severity)


def list_alerts(db: Session, user: User, status: str, limit: int, offset: int) -> AlertPage:
    query = _alert_query(user)
    if status == "active":
        query = query.where(SecurityAlert.status != AlertStatus.RESOLVED)
    elif status != "all":
        query = query.where(SecurityAlert.status == AlertStatus(status))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(_SEVERITY_ORDER, SecurityAlert.last_seen_at.desc()).limit(limit).offset(offset)).all()
    return AlertPage(items=[_alert_out(a, e, u) for a, e, u in rows], total=total)


def handle_alert(db: Session, actor: Actor, alert_id: uuid.UUID, body: AlertAction) -> AlertOut:
    alert = db.scalar(select(SecurityAlert).where(SecurityAlert.id == alert_id,
                                                  SecurityAlert.organization_id == actor.user.organization_id)
                      .with_for_update())
    if alert is None:
        raise AppError(404, "NOT_FOUND", "Alert not found.")
    if alert.status == AlertStatus.RESOLVED:
        raise AppError(409, "ALREADY_RESOLVED", "This alert is already resolved.")
    if body.status == "RESOLVED" and not (body.note or "").strip():
        raise AppError(422, "NOTE_REQUIRED", "Write what was found or done before resolving the alert.")
    old = {"status": alert.status.value, "note": alert.note}
    alert.status, alert.handled_by, alert.handled_at = AlertStatus(body.status), actor.user.id, clock.now()
    alert.note = (body.note or "").strip() or alert.note
    audit(db, actor, "SECURITY_ALERT_UPDATED", "security_alert", alert.id, old_value=old,
          new_value={"status": alert.status.value, "note": alert.note, "rule": alert.rule})
    db.commit()
    emp = db.get(Employee, alert.employee_id) if alert.employee_id else None
    return _alert_out(alert, emp, actor.user)


# --- Dashboard numbers ------------------------------------------------------------------------


def overview(db: Session, user: User, start: date, end: date) -> SecurityOverview:
    if end < start or (end - start).days > 92:
        raise AppError(422, "VALIDATION_ERROR", "Choose a period of at most 93 days.")
    tz_name = db.get(Organization, user.organization_id).default_timezone
    tz = ZoneInfo(tz_name)
    lo = datetime.combine(start, datetime.min.time(), tz)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tz)
    in_range = and_(SecurityEvent.organization_id == user.organization_id,
                    SecurityEvent.created_at >= lo, SecurityEvent.created_at < hi)

    by_severity = {s.value: 0 for s in Severity}
    for sev, n in db.execute(select(SecurityEvent.severity, func.count()).where(in_range).group_by(SecurityEvent.severity)):
        by_severity[sev.value] = n
    by_type = [CountItem(key=t, count=n) for t, n in db.execute(
        select(SecurityEvent.event_type, func.count()).where(in_range)
        .group_by(SecurityEvent.event_type).order_by(func.count().desc()))]

    local_day = func.date(func.timezone(tz_name, SecurityEvent.created_at))
    days = {start + timedelta(days=i): DayCount(date=start + timedelta(days=i)) for i in range((end - start).days + 1)}
    for day, sev, n in db.execute(select(local_day, SecurityEvent.severity, func.count()).where(in_range)
                                  .group_by(local_day, SecurityEvent.severity)):
        if day in days:
            setattr(days[day], sev.value.lower(), n)

    top_employees = [CountItem(key=code, label=name, count=n) for code, name, n in db.execute(
        select(Employee.employee_code, Employee.full_name, func.count())
        .select_from(SecurityEvent).join(Employee, Employee.id == SecurityEvent.employee_id)
        .where(in_range, SecurityEvent.severity.in_([Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]))
        .group_by(Employee.employee_code, Employee.full_name).order_by(func.count().desc()).limit(5))]

    logins = and_(SecurityEvent.event_type == "LOGIN_FAILED", SecurityEvent.created_at >= lo, SecurityEvent.created_at < hi,
                  or_(SecurityEvent.organization_id == user.organization_id, SecurityEvent.organization_id.is_(None)))
    failed = db.scalar(select(func.count()).where(logins)) or 0
    locked = db.scalar(select(func.count()).where(logins, SecurityEvent.details["locked"].astext == "true")) or 0
    top_ips = [CountItem(key=str(ip), count=n) for ip, n in db.execute(
        select(SecurityEvent.ip_address, func.count()).where(logins, SecurityEvent.ip_address.is_not(None))
        .group_by(SecurityEvent.ip_address).order_by(func.count().desc()).limit(5))]

    open_alerts = {s.value: 0 for s in Severity}
    for sev, n in db.execute(select(SecurityAlert.severity, func.count()).where(
            SecurityAlert.organization_id == user.organization_id, SecurityAlert.status != AlertStatus.RESOLVED)
            .group_by(SecurityAlert.severity)):
        open_alerts[sev.value] = n

    return SecurityOverview(
        date_from=start, date_to=end, total_events=sum(by_severity.values()), by_severity=by_severity, by_type=by_type,
        per_day=list(days.values()), top_employees=top_employees, failed_logins=failed, locked_accounts=locked,
        top_ips=top_ips, open_alerts=open_alerts, chain=last_check(db),
    )
