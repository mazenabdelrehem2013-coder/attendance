"""HR overview, charts, security events and the security-policy settings."""

import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    AttendanceEvent,
    AttendanceEventReview,
    AttendancePolicy,
    Employee,
    Location,
    Organization,
    SecurityEvent,
    User,
)
from app.models.enums import EventResult
from app.schemas.hr import (
    GroupCount,
    HrOverview,
    PolicyOut,
    PolicySet,
    PolicyUpdate,
    SecurityEventOut,
    TrendPoint,
)
from app.schemas.team import TeamRow
from app.services.attendance.policy import EffectivePolicy
from app.services.audit import Actor, audit, changed_fields
from app.services.review_service import counts_for_day
from app.services.scope import employee_scope
from app.services.team_attendance import TeamFilters, team_day

MAX_TREND_DAYS = 93
POLICY_FIELDS = list(EffectivePolicy.__dataclass_fields__)


def _groups(rows: list[TeamRow], key) -> list[GroupCount]:
    groups: dict[str, list[TeamRow]] = defaultdict(list)
    for r in rows:
        groups[key(r) or "—"].append(r)
    return sorted(
        (
            GroupCount(
                name=name,
                employees=len(rs),
                present=sum(r.status in ("PRESENT", "LATE") for r in rs),
                late=sum(r.status == "LATE" for r in rs),
                absent=sum(r.status == "ABSENT" for r in rs),
                pending_review=sum(r.status == "PENDING_REVIEW" for r in rs),
                on_leave=sum(r.status == "ON_LEAVE" for r in rs),
            )
            for name, rs in groups.items()
        ),
        key=lambda g: g.name,
    )


def _day_bounds(db: Session, user: User, day: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(db.get(Organization, user.organization_id).default_timezone)
    start = datetime.combine(day, time.min, tz)
    return start, start + timedelta(days=1)


def overview(db: Session, user: User, day: date) -> HrOverview:
    team = team_day(db, user, day, TeamFilters())
    flagged, rejected = counts_for_day(db, user, *_day_bounds(db, user, day))
    pending_total = db.scalar(
        select(func.count())
        .select_from(AttendanceEvent)
        .join(Employee, Employee.id == AttendanceEvent.employee_id)
        .outerjoin(AttendanceEventReview, AttendanceEventReview.event_id == AttendanceEvent.id)
        .where(employee_scope(db, user), AttendanceEvent.result == EventResult.FLAGGED,
               AttendanceEventReview.id.is_(None))
    )
    return HrOverview(
        date=day,
        summary=team.summary,
        suspicious_attempts=flagged,
        rejected_attempts=rejected,
        pending_reviews_total=pending_total,
        by_location=_groups(team.rows, lambda r: r.location),
        by_department=_groups(team.rows, lambda r: r.department),
    )


def trend(db: Session, user: User, start: date, end: date) -> list[TrendPoint]:
    if end < start:
        raise AppError(422, "VALIDATION_ERROR", "'to' must be on or after 'from'.")
    if (end - start).days >= MAX_TREND_DAYS:
        raise AppError(422, "VALIDATION_ERROR", f"Choose at most {MAX_TREND_DAYS} days.")
    points = []
    day = start
    while day <= end:
        s = team_day(db, user, day, TeamFilters()).summary
        pending = s.suspicious
        denominator = s.present + s.absent
        points.append(TrendPoint(
            date=day, present=s.present, late=s.late, absent=s.absent, pending_review=pending,
            on_leave=s.on_leave, attendance_rate=round(s.present / denominator, 4) if denominator else None,
        ))
        day += timedelta(days=1)
    return points


def security_events(
    db: Session, user: User, start: date | None, end: date | None, event_type: str | None,
    employee_id: uuid.UUID | None, limit: int, offset: int,
) -> tuple[list[SecurityEventOut], int]:
    query = (
        select(SecurityEvent, Employee)
        .outerjoin(Employee, Employee.id == SecurityEvent.employee_id)
        .where(SecurityEvent.organization_id == user.organization_id)
    )
    if start:
        query = query.where(SecurityEvent.created_at >= _day_bounds(db, user, start)[0])
    if end:
        query = query.where(SecurityEvent.created_at < _day_bounds(db, user, end)[1])
    if event_type:
        query = query.where(SecurityEvent.event_type == event_type)
    if employee_id:
        query = query.where(SecurityEvent.employee_id == employee_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(SecurityEvent.created_at.desc()).offset(offset).limit(limit)).all()
    return [
        SecurityEventOut(
            id=s.id, created_at=s.created_at, event_type=s.event_type, severity=s.severity,
            employee_code=e.employee_code if e else None, employee_name=e.full_name if e else None,
            attendance_event_id=s.attendance_event_id, details=s.details,
        )
        for s, e in rows
    ], total


# --- Security policies ----------------------------------------------------------------------


def _policy_out(row: AttendancePolicy | None, location: Location | None) -> PolicyOut:
    values = (
        {f: getattr(row, f) for f in POLICY_FIELDS} if row is not None
        else {f: getattr(EffectivePolicy(), f) for f in POLICY_FIELDS}
    )
    return PolicyOut(location_id=location.id if location else None,
                     location_name=location.name if location else None, **values)


def policies(db: Session, org_id: uuid.UUID) -> PolicySet:
    rows = db.execute(
        select(AttendancePolicy, Location)
        .outerjoin(Location, Location.id == AttendancePolicy.location_id)
        .where(AttendancePolicy.organization_id == org_id)
    ).all()
    default = next((p for p, loc in rows if p.location_id is None), None)
    overrides = sorted(((p, loc) for p, loc in rows if p.location_id is not None), key=lambda x: x[1].name)
    return PolicySet(default=_policy_out(default, None), locations=[_policy_out(p, loc) for p, loc in overrides])


def _snapshot(row: AttendancePolicy) -> dict:
    return {f: (v.value if hasattr(v, "value") else v) for f in POLICY_FIELDS for v in [getattr(row, f)]}


def update_policy(db: Session, actor: Actor, location_id: uuid.UUID | None, data: PolicyUpdate) -> PolicyOut:
    org = actor.user.organization_id
    location = None
    if location_id is not None:
        location = db.get(Location, location_id)
        if location is None or location.organization_id != org:
            raise AppError(404, "NOT_FOUND", "Location not found.")
    row = db.scalar(
        select(AttendancePolicy).where(
            AttendancePolicy.organization_id == org,
            AttendancePolicy.location_id.is_(None) if location_id is None
            else AttendancePolicy.location_id == location_id,
        )
    )
    if row is None:
        # A new location override starts as a copy of the company default.
        base = db.scalar(select(AttendancePolicy).where(
            AttendancePolicy.organization_id == org, AttendancePolicy.location_id.is_(None)))
        start = {f: getattr(base, f) for f in POLICY_FIELDS} if base else {
            f: getattr(EffectivePolicy(), f) for f in POLICY_FIELDS}
        row = AttendancePolicy(organization_id=org, location_id=location_id, **start)
        db.add(row)
        db.flush()
        before = {}
    else:
        before = _snapshot(row)
    for field in data.model_fields_set:
        value = getattr(data, field)
        if value is None:
            raise AppError(422, "VALIDATION_ERROR", f"'{field}' cannot be empty.")
        setattr(row, field, value)
    row.updated_by = actor.user.id
    db.flush()
    old, new = changed_fields(before, _snapshot(row))
    audit(db, actor, "SECURITY_POLICY_CHANGED", "attendance_policy",
          location_id or "default", old or None, new or _snapshot(row))
    db.commit()
    return _policy_out(row, location)


def delete_location_policy(db: Session, actor: Actor, location_id: uuid.UUID) -> None:
    row = db.scalar(select(AttendancePolicy).where(
        AttendancePolicy.organization_id == actor.user.organization_id,
        AttendancePolicy.location_id == location_id))
    if row is None:
        raise AppError(404, "NOT_FOUND", "This location has no own rules.")
    audit(db, actor, "SECURITY_POLICY_REMOVED", "attendance_policy", location_id, _snapshot(row), None)
    db.delete(row)
    db.commit()
