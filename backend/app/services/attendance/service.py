"""Check-in / check-out.

Flow for every attempt:
  1. The phone asks for a one-time challenge (nonce, ~90 s) right before capturing GPS.
  2. The phone sends evidence + the challenge.
  3. The server checks the device and the challenge (single use), runs the verification
     signals, applies the policy and decides ACCEPTED / FLAGGED / REJECTED.
  4. Every attempt that used a challenge is stored as an attendance_event with its
     verification - including rejected ones - so the history is complete and auditable.

The authoritative time is always the server's clock.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.models import (
    Attendance,
    AttendanceChallenge,
    AttendanceEvent,
    AttendanceSession,
    AttendanceVerification,
    Employee,
    EmployeeLocation,
    Location,
    User,
    VerificationSignal,
)
from app.models.enums import (
    AttendanceAction,
    DayStatus,
    EventResult,
    SessionStatus,
    Severity,
    SignalResult,
    SignalType,
    VerificationMode,
    VerificationStatus,
)
from app.schemas.attendance import (
    AttemptOut,
    AttendanceDay,
    AttendanceSubmission,
    ChallengeRequest,
    ChallengeResponse,
    CheckResult,
    SessionOut,
    TodayResponse,
)
from app.services.attendance.calendar import DayType, day_context, local_date
from app.services.attendance.canonical import canonical_payload, request_hash
from app.services.attendance.alerts import attempt_alerts
from app.services.attendance.integrity import integrity_signal
from app.services.attendance.messages import employee_message
from app.services.attendance.policy import EffectivePolicy, load_policy
from app.services.attendance.rules import ScheduleView, SessionView, session_minutes, summarize
from app.services.attendance.verification import (
    Decision,
    SignalOutcome,
    clock_skew_signal,
    decide,
    device_signature_signal,
    geofence_signal,
    gps_accuracy_signal,
    location_age_signal,
    mock_location_signal,
    movement_signal,
)
from app.services.audit import RequestInfo, clean_ip, write_security_event
from app.services.device_keys import verify_signature
from app.services.device_service import require_active_device
from app.services.geo import haversine_m
from app.services.qr_service import QrCheck, verify_token

MAX_HISTORY_DAYS = 93

_BASE_DAY_STATUS = {
    DayType.HOLIDAY: DayStatus.HOLIDAY,
    DayType.ON_LEAVE: DayStatus.ON_LEAVE,
    DayType.NON_WORKING_DAY: DayStatus.NON_WORKING_DAY,
    DayType.WORKING_DAY: None,
}


def _hash_nonce(nonce: str) -> str:
    return hashlib.sha256(nonce.encode()).hexdigest()


def employee_for(db: Session, user: User, lock: bool = False) -> Employee:
    query = select(Employee).where(Employee.user_id == user.id)
    employee = db.scalar(query.with_for_update() if lock else query)
    if employee is None:
        raise AppError(404, "NO_EMPLOYEE_RECORD", "There is no employee record for this account.")
    return employee


def authorized_locations(db: Session, employee: Employee, now: datetime) -> list[Location]:
    rows = db.execute(
        select(Location, EmployeeLocation)
        .join(EmployeeLocation, EmployeeLocation.location_id == Location.id)
        .where(EmployeeLocation.employee_id == employee.id, Location.is_active)
    ).all()
    result = []
    for loc, link in rows:
        today = local_date(now, loc.timezone)
        if link.valid_from <= today and (link.valid_to is None or link.valid_to >= today):
            result.append(loc)
    return result


def primary_location(db: Session, employee: Employee, now: datetime) -> Location | None:
    locations = authorized_locations(db, employee, now)
    if not locations:
        return None
    primary_id = db.scalar(
        select(EmployeeLocation.location_id).where(
            EmployeeLocation.employee_id == employee.id, EmployeeLocation.is_primary
        )
    )
    return next((l for l in locations if l.id == primary_id), locations[0])


# --- Challenge ------------------------------------------------------------------------------


def create_challenge(
    db: Session, user: User, data: ChallengeRequest, info: RequestInfo
) -> ChallengeResponse:
    employee = employee_for(db, user)
    device = require_active_device(db, employee, data.device_id)
    policy = load_policy(db, employee.organization_id, None)
    now = clock.now()
    nonce = secrets.token_urlsafe(32)
    challenge = AttendanceChallenge(
        employee_id=employee.id,
        device_registration_id=device.id,
        action=data.action,
        nonce_hash=_hash_nonce(nonce),
        issued_at=now,
        expires_at=now + timedelta(seconds=policy.challenge_ttl_s),
        ip_address=clean_ip(info.ip_address),
    )
    db.add(challenge)
    device.last_seen_at = now
    db.commit()
    return ChallengeResponse(
        challenge_id=challenge.id, nonce=nonce, expires_at=challenge.expires_at, server_time=now
    )


# --- Check-in / check-out -------------------------------------------------------------------


@dataclass
class _Attempt:
    employee: Employee
    action: AttendanceAction
    data: AttendanceSubmission
    info: RequestInfo
    now: datetime
    device_id: uuid.UUID


def submit(
    db: Session, user: User, action: AttendanceAction, data: AttendanceSubmission, info: RequestInfo
) -> CheckResult:
    # Lock this employee's row: their attempts are handled one at a time, so two simultaneous
    # check-ins can't both pass the "not checked in yet" test.
    employee = employee_for(db, user, lock=True)

    # Same request sent again (e.g. the network dropped after sending): return the original
    # result instead of creating a second record.
    previous = db.scalar(
        select(AttendanceEvent).where(
            AttendanceEvent.employee_id == employee.id,
            AttendanceEvent.client_request_id == data.client_request_id,
        )
    )
    if previous is not None:
        if previous.event_type != action:
            raise AppError(409, "DUPLICATE_REQUEST", "This request ID was already used for another action.")
        return _result(db, previous)

    device = require_active_device(db, employee, data.device_id)
    attempt = _Attempt(employee, action, data, info, clock.now(), device.id)
    device.last_seen_at = attempt.now

    # 1. Challenge: must exist, belong to this employee/phone/action, match, be unexpired and unused.
    challenge = db.scalar(
        select(AttendanceChallenge)
        .where(AttendanceChallenge.id == data.challenge_id, AttendanceChallenge.employee_id == employee.id)
        .with_for_update()
    )
    problem = _challenge_problem(challenge, attempt)
    if problem is not None:
        if problem == "REPLAY":
            write_security_event(
                db, event_type="REPLAY", severity=Severity.MEDIUM,
                organization_id=employee.organization_id, user_id=user.id, employee_id=employee.id,
                device_registration_id=device.id, ip_address=info.ip_address,
                details={"challenge_id": str(data.challenge_id)},
            )
        outcome = SignalOutcome("replay_check", SignalResult.FAIL, reason_code=problem)
        decision = decide([outcome], "")
        return _store(db, attempt, decision, EffectivePolicy(), challenge_id=None,
                      message_code="REQUEST_EXPIRED")
    challenge.consumed_at = attempt.now
    replay_ok = SignalOutcome("replay_check", SignalResult.PASS)

    # 2. Is this action possible right now?
    open_session = db.scalar(
        select(AttendanceSession)
        .where(AttendanceSession.employee_id == employee.id, AttendanceSession.status == SessionStatus.OPEN)
        .with_for_update()
    )
    if action == AttendanceAction.CHECK_IN and open_session is not None:
        return _store_simple_reject(db, attempt, challenge.id, replay_ok, "ALREADY_CHECKED_IN")
    if action == AttendanceAction.CHECK_OUT and open_session is None:
        return _store_simple_reject(db, attempt, challenge.id, replay_ok, "NOT_CHECKED_IN")

    # 3. Was the request signed by this phone's hardware key (and not changed since)?
    payload = canonical_payload(action, data)
    signed = bool(device.public_key) and verify_signature(device.public_key, payload, data.signature)
    signature_check = device_signature_signal(bool(device.public_key), signed)

    # 4. Nearest authorized location, measured by the server.
    locations = authorized_locations(db, employee, attempt.now)
    if not locations:
        return _store_simple_reject(db, attempt, challenge.id, replay_ok, "NO_ASSIGNED_LOCATION")
    distances = {
        l.id: (haversine_m(data.latitude, data.longitude, float(l.latitude), float(l.longitude)), l)
        for l in locations
    }
    # The office we're "most inside" (smallest distance beyond its own radius) - this also
    # handles offices of different sizes that are close together.
    distance, location = min(distances.values(), key=lambda pair: pair[0] - pair[1].radius_m)
    policy = load_policy(db, employee.organization_id, location.id)

    # 5. Office QR code, when this location requires one. A valid code from another of the
    #    employee's offices means they're at THAT office, so it's measured against that one.
    qr_check = SignalOutcome("qr_check", SignalResult.NOT_APPLICABLE)
    if policy.verification_mode in (VerificationMode.GPS_QR, VerificationMode.GPS_QR_PLUS):
        qr_check = _qr_signal(db, data.qr_token, attempt.now, distances, policy)
        if qr_check.result == SignalResult.PASS and qr_check.details["location_id"] != str(location.id):
            distance, location = distances[uuid.UUID(qr_check.details["location_id"])]
            policy = load_policy(db, employee.organization_id, location.id)

    # 6. All signals -> policy -> decision.
    seconds_since_challenge = (attempt.now - challenge.issued_at).total_seconds()
    outcomes = [
        replay_ok,
        signature_check,
        geofence_signal(distance, location.radius_m, data.accuracy_m, policy.on_outside_geofence),
        gps_accuracy_signal(data.accuracy_m, policy.max_accuracy_m, policy.on_poor_accuracy),
        location_age_signal(data.fix_age_ms, seconds_since_challenge, policy.max_fix_age_s,
                            policy.on_stale_location),
        mock_location_signal(data.is_mock_location, policy.on_mock_location),
        integrity_signal(data.integrity_token, request_hash(payload), attempt.now, policy.on_integrity_fail),
        clock_skew_signal((data.device_time - attempt.now).total_seconds(), policy.max_clock_skew_s,
                          policy.on_clock_skew),
        _movement_signal(db, employee, data, attempt.now, policy),
        qr_check,
    ]
    success = "CHECK_IN_OK" if action == AttendanceAction.CHECK_IN else "CHECK_OUT_OK"
    decision = decide(outcomes, success)

    return _store(db, attempt, decision, policy, challenge.id, location=location, distance=distance,
                  open_session=open_session)


def _qr_signal(db: Session, token: str | None, now: datetime, distances: dict, policy) -> SignalOutcome:
    if not token:
        return SignalOutcome("qr_check", SignalResult.FAIL, policy.on_qr_fail, "QR_MISSING")
    check = verify_token(db, token, now)
    if check.ok and check.display.location_id not in distances:
        check = QrCheck(False, "QR_OTHER_LOCATION", check.display)
    details = {"location_id": str(check.display.location_id)} if check.display else {}
    if not check.ok:
        details["problem"] = check.reason
        return SignalOutcome("qr_check", SignalResult.FAIL, policy.on_qr_fail, "QR_INVALID", details)
    details["display_id"] = str(check.display.id)
    return SignalOutcome("qr_check", SignalResult.PASS, policy.on_qr_fail, None, details)


MOVEMENT_LOOKBACK = timedelta(hours=24)


def _movement_signal(db: Session, employee: Employee, data: AttendanceSubmission, now: datetime,
                     policy) -> SignalOutcome:
    """Compare with the previous ACCEPTED event (flagged ones may themselves be fake)."""
    previous = db.scalar(
        select(AttendanceEvent)
        .where(
            AttendanceEvent.employee_id == employee.id,
            AttendanceEvent.result == EventResult.ACCEPTED,
            AttendanceEvent.latitude.is_not(None),
            AttendanceEvent.server_received_at >= now - MOVEMENT_LOOKBACK,
        )
        .order_by(AttendanceEvent.server_received_at.desc())
        .limit(1)
    )
    if previous is None:
        return movement_signal(None, 0, 0, 0, policy.max_travel_speed_kmh, policy.on_impossible_travel)
    distance = haversine_m(data.latitude, data.longitude, float(previous.latitude), float(previous.longitude))
    return movement_signal(
        distance, data.accuracy_m, float(previous.accuracy_m or 0),
        (now - previous.server_received_at).total_seconds(),
        policy.max_travel_speed_kmh, policy.on_impossible_travel,
    )


def _challenge_problem(challenge: AttendanceChallenge | None, attempt: _Attempt) -> str | None:
    if challenge is None:
        return "CHALLENGE_UNKNOWN"
    if challenge.consumed_at is not None:
        return "REPLAY"
    if (
        challenge.device_registration_id != attempt.device_id
        or challenge.action != attempt.action
        or not secrets.compare_digest(challenge.nonce_hash, _hash_nonce(attempt.data.nonce))
    ):
        return "CHALLENGE_MISMATCH"
    if challenge.expires_at <= attempt.now:
        return "CHALLENGE_EXPIRED"
    return None


def _store_simple_reject(
    db: Session, attempt: _Attempt, challenge_id: uuid.UUID, replay_ok: SignalOutcome, reason: str
) -> CheckResult:
    decision = Decision(EventResult.REJECTED, reason, reason,
                        decide([replay_ok], "").signals, {}, 0)
    return _store(db, attempt, decision, EffectivePolicy(), challenge_id)


def _store(
    db: Session,
    attempt: _Attempt,
    decision: Decision,
    policy: EffectivePolicy,
    challenge_id: uuid.UUID | None,
    *,
    location: Location | None = None,
    distance: float | None = None,
    open_session: AttendanceSession | None = None,
    message_code: str | None = None,
) -> CheckResult:
    data, now = attempt.data, attempt.now
    counts = decision.result != EventResult.REJECTED and location is not None

    # attendance_events are write-once (enforced by the database), so the day's attendance
    # record is found/created BEFORE the event is inserted, and linked at insert time.
    attendance = None
    if counts:
        if attempt.action == AttendanceAction.CHECK_IN:
            attendance = _get_or_create_day(db, attempt.employee, location, now)
        else:
            attendance = db.get(Attendance, open_session.attendance_id)

    event = AttendanceEvent(
        employee_id=attempt.employee.id,
        attendance_id=attendance.id if attendance else None,
        event_type=attempt.action,
        client_request_id=data.client_request_id,
        challenge_id=challenge_id,
        device_registration_id=attempt.device_id,
        server_received_at=now,
        device_reported_at=data.device_time,
        latitude=round(data.latitude, 6),
        longitude=round(data.longitude, 6),
        accuracy_m=round(data.accuracy_m, 2),
        fix_age_ms=data.fix_age_ms,
        location_id=location.id if location else None,
        distance_m=round(distance, 2) if distance is not None else None,
        app_version=data.app_version,
        os_version=data.os_version,
        ip_address=clean_ip(attempt.info.ip_address),
        result=decision.result,
        reason_code=decision.reason_code,
        employee_message_code=message_code or decision.message_code,
    )
    db.add(event)
    db.flush()
    verification = AttendanceVerification(
        event_id=event.id,
        **decision.signals,
        details=decision.details,
        risk_score=decision.risk_score,
        policy_snapshot=policy.snapshot(),
        final_result=decision.result,
    )
    db.add(verification)
    if decision.signals["qr_check"] != SignalResult.NOT_APPLICABLE:
        db.flush()
        db.add(VerificationSignal(verification_id=verification.id, signal_type=SignalType.QR,
                                  result=decision.signals["qr_check"],
                                  details=decision.details.get("qr_check", {})))

    if counts:
        pending = decision.result == EventResult.FLAGGED and not policy.flagged_counts_before_review
        if attempt.action == AttendanceAction.CHECK_IN:
            db.add(
                AttendanceSession(
                    attendance_id=attendance.id, employee_id=attempt.employee.id,
                    check_in_event_id=event.id, check_in_at=now, pending_review=pending,
                )
            )
        else:
            session = open_session
            session.check_out_event_id = event.id
            session.check_out_at = now
            session.status = SessionStatus.CLOSED
            session.worked_minutes = session_minutes(session.check_in_at, now)
            session.pending_review = session.pending_review or pending
        db.flush()
        recompute(db, attendance)

    for signal, reason in decision.failures:
        event_type, severity = _SECURITY_EVENTS.get(reason, (None, None))
        if event_type is None:
            continue
        write_security_event(
            db, event_type=event_type, severity=severity,
            organization_id=attempt.employee.organization_id, employee_id=attempt.employee.id,
            attendance_event_id=event.id, device_registration_id=attempt.device_id,
            ip_address=attempt.info.ip_address,
            details={"result": decision.result.value, "reason": reason, **decision.details.get(signal, {})},
        )
    attempt_alerts(db, attempt.employee, attempt.action, event, location, attendance)
    db.commit()
    return _result(db, event)


def _get_or_create_day(db: Session, employee: Employee, location: Location, now: datetime) -> Attendance:
    day = local_date(now, location.timezone)
    attendance = db.scalar(
        select(Attendance)
        .where(Attendance.employee_id == employee.id, Attendance.attendance_date == day)
        .with_for_update()
    )
    if attendance is None:
        ctx = day_context(db, employee, location, day)
        attendance = Attendance(
            employee_id=employee.id,
            attendance_date=day,
            location_id=location.id,
            scheduled_start=ctx.scheduled_start,
            scheduled_end=ctx.scheduled_end,
            grace_minutes=ctx.grace_minutes,
            early_departure_minutes=ctx.early_departure_minutes,
        )
        db.add(attendance)
        db.flush()
    return attendance


def recompute(db: Session, attendance: Attendance) -> None:
    """Rebuild the daily summary from its sessions (after every change)."""
    sessions = db.scalars(
        select(AttendanceSession).where(AttendanceSession.attendance_id == attendance.id)
    ).all()
    location = db.get(Location, attendance.location_id)
    employee = db.get(Employee, attendance.employee_id)
    ctx = day_context(db, employee, location, attendance.attendance_date)
    schedule = None
    if attendance.scheduled_start is not None:
        schedule = ScheduleView(
            attendance.scheduled_start, attendance.scheduled_end,
            attendance.grace_minutes or 0, attendance.early_departure_minutes or 0,
        )
    summary = summarize(
        [SessionView(s.check_in_at, s.check_out_at, s.status, s.pending_review) for s in sessions],
        attendance.attendance_date, schedule, location.timezone, _BASE_DAY_STATUS[ctx.day_type],
    )
    for field in (
        "first_check_in_at", "last_check_out_at", "worked_minutes", "arrival_status",
        "departure_status", "day_status", "verification_status",
    ):
        setattr(attendance, field, getattr(summary, field))


# Which failed checks are worth a security event for HR, and how serious they are.
_SECURITY_EVENTS = {
    "OUTSIDE_LOCATION": ("OUTSIDE_GEOFENCE", Severity.LOW),
    "MOCK_LOCATION": ("MOCK_LOCATION", Severity.HIGH),
    "INTEGRITY_FAIL": ("INTEGRITY_FAIL", Severity.HIGH),
    "INTEGRITY_MISSING": ("INTEGRITY_FAIL", Severity.HIGH),
    "IMPOSSIBLE_TRAVEL": ("IMPOSSIBLE_TRAVEL", Severity.MEDIUM),
    "CLOCK_SKEW": ("CLOCK_SKEW", Severity.LOW),
    "QR_INVALID": ("QR_INVALID", Severity.MEDIUM),
    "QR_MISSING": ("QR_MISSING", Severity.LOW),
    "BAD_SIGNATURE": ("BAD_SIGNATURE", Severity.HIGH),
    "NO_DEVICE_KEY": ("BAD_SIGNATURE", Severity.HIGH),
}

_VERIFICATION_BY_RESULT = {
    EventResult.ACCEPTED: VerificationStatus.VERIFIED,
    EventResult.FLAGGED: VerificationStatus.PENDING_REVIEW,
    EventResult.REJECTED: VerificationStatus.REJECTED,
}


def _result(db: Session, event: AttendanceEvent) -> CheckResult:
    attendance = db.get(Attendance, event.attendance_id) if event.attendance_id else None
    location = db.get(Location, event.location_id) if event.location_id else None
    accepted = event.result == EventResult.ACCEPTED
    return CheckResult(
        success=accepted,
        result=event.result,
        event_type=event.event_type,
        event_id=event.id,
        attendance_id=event.attendance_id,
        server_time=event.server_received_at,
        status=attendance.day_status if attendance else None,
        verification_status=_VERIFICATION_BY_RESULT[event.result],
        location=location.name if location and event.result != EventResult.REJECTED else None,
        distance_meters=round(event.distance_m) if accepted and event.distance_m is not None else None,
        message_code=event.employee_message_code,
        message=employee_message(event.employee_message_code),
    )


# --- Today & history ------------------------------------------------------------------------


def _day_out(db: Session, attendance: Attendance) -> AttendanceDay:
    sessions = db.scalars(
        select(AttendanceSession)
        .where(AttendanceSession.attendance_id == attendance.id)
        .order_by(AttendanceSession.check_in_at)
    ).all()
    location = db.get(Location, attendance.location_id) if attendance.location_id else None
    return AttendanceDay(
        attendance_id=attendance.id,
        date=attendance.attendance_date,
        location=location.name if location else None,
        first_check_in_at=attendance.first_check_in_at,
        last_check_out_at=attendance.last_check_out_at,
        worked_minutes=attendance.worked_minutes,
        arrival_status=attendance.arrival_status,
        departure_status=attendance.departure_status,
        day_status=attendance.day_status,
        verification_status=attendance.verification_status,
        sessions=[
            SessionOut(
                check_in_at=s.check_in_at, check_out_at=s.check_out_at,
                worked_minutes=s.worked_minutes, status=s.status, pending_review=s.pending_review,
            )
            for s in sessions
        ],
    )


def today(db: Session, user: User) -> TodayResponse:
    employee = employee_for(db, user)
    now = clock.now()
    location = primary_location(db, employee, now)
    tz = location.timezone if location else "Africa/Lagos"
    day = local_date(now, tz)

    open_session = db.scalar(
        select(AttendanceSession).where(
            AttendanceSession.employee_id == employee.id, AttendanceSession.status == SessionStatus.OPEN
        )
    )
    attendance = db.scalar(
        select(Attendance).where(Attendance.employee_id == employee.id, Attendance.attendance_date == day)
    )
    if attendance is None and open_session is not None:  # still checked in since yesterday
        attendance = db.get(Attendance, open_session.attendance_id)

    # An attendance row only exists once there has been a check-in that day.
    if open_session is not None:
        state, next_action = "CHECKED_IN", AttendanceAction.CHECK_OUT
    elif attendance is not None:
        state, next_action = "CHECKED_OUT", AttendanceAction.CHECK_IN
    else:
        state, next_action = "NOT_CHECKED_IN", AttendanceAction.CHECK_IN

    ctx = day_context(db, employee, location, day) if location else None
    attempts = db.scalars(
        select(AttendanceEvent)
        .where(
            AttendanceEvent.employee_id == employee.id,
            AttendanceEvent.server_received_at >= now - timedelta(hours=36),
        )
        .order_by(AttendanceEvent.server_received_at.desc())
        .limit(20)
    ).all()
    return TodayResponse(
        date=day,
        timezone=tz,
        day_type=(ctx.day_type if ctx else DayType.WORKING_DAY).value,
        day_description=ctx.description if ctx else None,
        scheduled_start=ctx.scheduled_start if ctx else None,
        scheduled_end=ctx.scheduled_end if ctx else None,
        state=state,
        next_action=next_action,
        qr_required=any(
            load_policy(db, employee.organization_id, loc.id).verification_mode
            in (VerificationMode.GPS_QR, VerificationMode.GPS_QR_PLUS)
            for loc in authorized_locations(db, employee, now)
        ),
        attendance=_day_out(db, attendance) if attendance else None,
        attempts=[
            AttemptOut(event_type=e.event_type, server_time=e.server_received_at, result=e.result,
                       message=employee_message(e.employee_message_code))
            for e in attempts
            if local_date(e.server_received_at, tz) == day
        ],
    )


def history(db: Session, user: User, date_from: date, date_to: date) -> list[AttendanceDay]:
    if date_to < date_from:
        raise AppError(422, "VALIDATION_ERROR", "'to' must be on or after 'from'.")
    if (date_to - date_from).days >= MAX_HISTORY_DAYS:
        raise AppError(422, "VALIDATION_ERROR", f"Choose at most {MAX_HISTORY_DAYS} days.")
    employee = employee_for(db, user)
    rows = db.scalars(
        select(Attendance)
        .where(
            Attendance.employee_id == employee.id,
            Attendance.attendance_date >= date_from,
            Attendance.attendance_date <= date_to,
        )
        .order_by(Attendance.attendance_date.desc())
    ).all()
    return [_day_out(db, a) for a in rows]
