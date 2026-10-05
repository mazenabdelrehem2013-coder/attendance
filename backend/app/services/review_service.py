"""HR review of FLAGGED attendance (decision 11.6: flagged attempts don't count until approved).

APPROVE a flagged check-in   -> the session counts (arrival time = the original server time)
REJECT  a flagged check-in   -> the session never counts (status REJECTED)
APPROVE a flagged check-out  -> the session's hours count
REJECT  a flagged check-out  -> the arrival counts, the hours don't (MISSING_CHECKOUT)

Attendance events themselves are never changed (they are write-once evidence); the decision
is a separate attendance_event_reviews row, and the daily summary is recalculated.
"""

import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import AppError
from app.models import (
    Attendance,
    AttendanceEvent,
    AttendanceEventReview,
    AttendanceSession,
    AttendanceVerification,
    DeviceRegistration,
    Employee,
    Location,
    Organization,
    SecurityEvent,
    User,
)
from app.models.enums import (
    AttendanceAction,
    EventResult,
    ReviewDecision,
    SessionStatus,
    SignalResult,
)
from app.schemas.review import ReviewDetail, ReviewFilters, ReviewItem, ReviewPage
from app.services.attendance.service import recompute
from app.services.attendance.verification import SIGNALS
from app.services.audit import Actor, audit
from app.services.scope import employee_scope

Reviewer = aliased(User)


def _org_range(db: Session, user: User, filters: ReviewFilters) -> tuple[datetime | None, datetime | None]:
    tz = ZoneInfo(db.get(Organization, user.organization_id).default_timezone)
    start = datetime.combine(filters.date_from, time.min, tz) if filters.date_from else None
    end = datetime.combine(filters.date_to + timedelta(days=1), time.min, tz) if filters.date_to else None
    return start, end


def _failed(v: AttendanceVerification | None) -> list[str]:
    if v is None:
        return []
    return [s for s in SIGNALS if getattr(v, s) in (SignalResult.FAIL, SignalResult.WARN)]


def _base_query(db: Session, user: User):
    return (
        select(AttendanceEvent, Employee, Location, AttendanceVerification, AttendanceEventReview, Reviewer)
        .join(Employee, Employee.id == AttendanceEvent.employee_id)
        .outerjoin(Location, Location.id == AttendanceEvent.location_id)
        .outerjoin(AttendanceVerification, AttendanceVerification.event_id == AttendanceEvent.id)
        .outerjoin(AttendanceEventReview, AttendanceEventReview.event_id == AttendanceEvent.id)
        .outerjoin(Reviewer, Reviewer.id == AttendanceEventReview.reviewed_by)
        .where(employee_scope(db, user))
    )


def _item(event, emp, loc, ver, review, reviewer) -> dict:
    return dict(
        event_id=event.id,
        employee_id=emp.id,
        employee_code=emp.employee_code,
        employee_name=emp.full_name,
        event_type=event.event_type,
        server_time=event.server_received_at,
        result=event.result,
        reason_code=event.reason_code,
        location=loc.name if loc else None,
        distance_m=float(event.distance_m) if event.distance_m is not None else None,
        accuracy_m=float(event.accuracy_m) if event.accuracy_m is not None else None,
        risk_score=ver.risk_score if ver else None,
        failed_checks=_failed(ver),
        review_decision=review.decision if review else None,
        reviewed_by=reviewer.email if reviewer else None,
        reviewed_at=review.created_at if review else None,
        review_note=review.note if review else None,
    )


def list_items(db: Session, user: User, filters: ReviewFilters, limit: int, offset: int) -> ReviewPage:
    query = _base_query(db, user)
    if filters.state == "PENDING":
        query = query.where(AttendanceEvent.result == EventResult.FLAGGED, AttendanceEventReview.id.is_(None))
    elif filters.state == "REVIEWED":
        query = query.where(AttendanceEventReview.id.is_not(None))
    else:
        query = query.where(AttendanceEvent.result == EventResult.REJECTED)
    start, end = _org_range(db, user, filters)
    if start:
        query = query.where(AttendanceEvent.server_received_at >= start)
    if end:
        query = query.where(AttendanceEvent.server_received_at < end)
    if filters.employee_id:
        query = query.where(AttendanceEvent.employee_id == filters.employee_id)
    if filters.location_id:
        query = query.where(AttendanceEvent.location_id == filters.location_id)
    if filters.reason:
        query = query.where(AttendanceEvent.reason_code == filters.reason)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    order = (AttendanceEvent.server_received_at.asc() if filters.state == "PENDING"
             else AttendanceEvent.server_received_at.desc())
    rows = db.execute(query.order_by(order).offset(offset).limit(limit)).all()
    return ReviewPage(items=[ReviewItem(**_item(*r)) for r in rows], total=total)


def _load(db: Session, user: User, event_id: uuid.UUID):
    row = db.execute(_base_query(db, user).where(AttendanceEvent.id == event_id)).first()
    if row is None:
        raise AppError(404, "NOT_FOUND", "Attendance event not found.")
    return row


def detail(db: Session, user: User, event_id: uuid.UUID) -> ReviewDetail:
    event, emp, loc, ver, review, reviewer = _load(db, user, event_id)
    device = db.get(DeviceRegistration, event.device_registration_id) if event.device_registration_id else None
    security = db.scalars(
        select(SecurityEvent).where(SecurityEvent.attendance_event_id == event.id).order_by(SecurityEvent.created_at)
    ).all()
    return ReviewDetail(
        **_item(event, emp, loc, ver, review, reviewer),
        latitude=float(event.latitude) if event.latitude is not None else None,
        longitude=float(event.longitude) if event.longitude is not None else None,
        fix_age_ms=event.fix_age_ms,
        device_reported_at=event.device_reported_at,
        app_version=event.app_version,
        device_model=device.device_model if device else None,
        device_status=device.status.value if device else None,
        checks={s: getattr(ver, s).value for s in SIGNALS} if ver else {},
        details=ver.details if ver else {},
        policy=ver.policy_snapshot if ver else {},
        security_events=[
            {"type": s.event_type, "severity": s.severity.value, "details": s.details, "at": s.created_at.isoformat()}
            for s in security
        ],
    )


def _session_for(db: Session, event: AttendanceEvent) -> AttendanceSession | None:
    return db.scalar(
        select(AttendanceSession)
        .where((AttendanceSession.check_in_event_id == event.id) | (AttendanceSession.check_out_event_id == event.id))
        .with_for_update()
    )


def _still_pending(db: Session, session: AttendanceSession) -> bool:
    """True if any FLAGGED event of this session has not been reviewed yet."""
    ids = [i for i in (session.check_in_event_id, session.check_out_event_id) if i]
    return bool(db.scalar(
        select(func.count())
        .select_from(AttendanceEvent)
        .outerjoin(AttendanceEventReview, AttendanceEventReview.event_id == AttendanceEvent.id)
        .where(
            AttendanceEvent.id.in_(ids),
            AttendanceEvent.result == EventResult.FLAGGED,
            AttendanceEventReview.id.is_(None),
        )
    ))


def review(db: Session, actor: Actor, event_id: uuid.UUID, decision: ReviewDecision, note: str | None) -> ReviewDetail:
    event, emp, _loc, _ver, existing, _rev = _load(db, actor.user, event_id)
    if emp.user_id == actor.user.id:
        raise AppError(403, "FORBIDDEN", "You can't review your own attendance.")
    if event.result != EventResult.FLAGGED:
        raise AppError(409, "NOT_REVIEWABLE", "Only flagged attendance needs a review.")
    if existing is not None:
        raise AppError(409, "ALREADY_REVIEWED", "This attendance has already been reviewed.")

    db.add(AttendanceEventReview(event_id=event.id, decision=decision, reviewed_by=actor.user.id,
                                 note=(note or "").strip() or None))
    db.flush()

    session = _session_for(db, event)
    if session is not None:
        if decision == ReviewDecision.REJECTED:
            if event.event_type == AttendanceAction.CHECK_IN:
                session.status = SessionStatus.REJECTED
            elif session.status == SessionStatus.CLOSED:
                session.status = SessionStatus.MISSING_CHECKOUT
                session.worked_minutes = 0
        session.pending_review = session.status != SessionStatus.REJECTED and _still_pending(db, session)
        db.flush()
        attendance = db.get(Attendance, session.attendance_id)
        recompute(db, attendance)

    audit(db, actor, "ATTENDANCE_EVENT_REVIEWED", "attendance_event", event.id,
          new_value={"decision": decision.value, "note": note, "employee": emp.employee_code,
                     "event_type": event.event_type.value, "reason": event.reason_code})
    db.commit()
    return detail(db, actor.user, event_id)


def counts_for_day(db: Session, user: User, start: datetime, end: datetime) -> tuple[int, int]:
    """(flagged attempts, rejected attempts) in the user's scope between start and end."""
    rows = db.execute(
        select(AttendanceEvent.result, func.count())
        .join(Employee, Employee.id == AttendanceEvent.employee_id)
        .where(employee_scope(db, user),
               and_(AttendanceEvent.server_received_at >= start, AttendanceEvent.server_received_at < end))
        .group_by(AttendanceEvent.result)
    ).all()
    by = {r: n for r, n in rows}
    return by.get(EventResult.FLAGGED, 0), by.get(EventResult.REJECTED, 0)
