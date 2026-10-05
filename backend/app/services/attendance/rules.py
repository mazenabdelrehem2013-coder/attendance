"""Attendance rules: turn a day's sessions into PRESENT / LATE / EARLY_DEPARTURE / worked hours.

Pure functions (no database), so every rule is easy to test. All times are server times;
they are converted to the location's timezone before comparing with working hours.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.enums import (
    ArrivalStatus,
    DayStatus,
    DepartureStatus,
    SessionStatus,
    VerificationStatus,
)


@dataclass(frozen=True)
class SessionView:
    check_in_at: datetime
    check_out_at: datetime | None
    status: SessionStatus
    pending_review: bool = False


@dataclass(frozen=True)
class ScheduleView:
    start: time | None
    end: time | None
    grace_minutes: int = 0
    early_departure_minutes: int = 0


@dataclass(frozen=True)
class DaySummary:
    first_check_in_at: datetime | None
    last_check_out_at: datetime | None
    worked_minutes: int
    arrival_status: ArrivalStatus | None
    departure_status: DepartureStatus | None
    day_status: DayStatus | None
    verification_status: VerificationStatus | None


def session_minutes(check_in_at: datetime, check_out_at: datetime | None) -> int:
    if check_out_at is None or check_out_at <= check_in_at:
        return 0
    return int((check_out_at - check_in_at).total_seconds() // 60)


def arrival_status(
    first_check_in: datetime, day: date, schedule: ScheduleView, tz: str
) -> ArrivalStatus:
    """PRESENT if at or before start + grace (e.g. 09:00 + 15 min = 09:15:00), otherwise LATE."""
    if schedule.start is None:
        return ArrivalStatus.PRESENT
    zone = ZoneInfo(tz)
    deadline = datetime.combine(day, schedule.start, zone) + timedelta(minutes=schedule.grace_minutes)
    return ArrivalStatus.PRESENT if first_check_in <= deadline else ArrivalStatus.LATE


def departure_status(
    last_check_out: datetime, day: date, schedule: ScheduleView, tz: str
) -> DepartureStatus:
    """EARLY_DEPARTURE if leaving before end - allowed early minutes, otherwise CHECKED_OUT."""
    if schedule.end is None:
        return DepartureStatus.CHECKED_OUT
    zone = ZoneInfo(tz)
    earliest = datetime.combine(day, schedule.end, zone) - timedelta(
        minutes=schedule.early_departure_minutes
    )
    return DepartureStatus.EARLY_DEPARTURE if last_check_out < earliest else DepartureStatus.CHECKED_OUT


def summarize(
    sessions: Iterable[SessionView],
    day: date,
    schedule: ScheduleView | None,
    tz: str,
    base_day_status: DayStatus | None = None,
) -> DaySummary:
    """
    sessions        all sessions of the day
    schedule        working hours that applied (None on weekends/holidays/leave)
    base_day_status HOLIDAY / ON_LEAVE / NON_WORKING_DAY when it isn't a normal working day
    """
    sessions = list(sessions)
    counted = [s for s in sessions if not s.pending_review and s.status != SessionStatus.REJECTED]
    pending = any(s.pending_review and s.status != SessionStatus.REJECTED for s in sessions)
    schedule = schedule or ScheduleView(None, None)

    first_in = min((s.check_in_at for s in counted), default=None)
    still_open = any(s.status == SessionStatus.OPEN for s in counted)
    # Only properly closed sessions give hours and a check-out time (a check-out HR rejected
    # leaves the session MISSING_CHECKOUT: the arrival counts, the hours don't).
    closed = [s for s in counted if s.status == SessionStatus.CLOSED and s.check_out_at is not None]
    last_out = None if still_open or not closed else max(s.check_out_at for s in closed)
    worked = sum(session_minutes(s.check_in_at, s.check_out_at) for s in closed)

    arrival = arrival_status(first_in, day, schedule, tz) if first_in else None

    if any(s.status == SessionStatus.MISSING_CHECKOUT for s in counted) and not still_open:
        departure = DepartureStatus.MISSING_CHECKOUT
    elif last_out is not None:
        departure = departure_status(last_out, day, schedule, tz)
    else:
        departure = None

    if arrival is not None:
        day_status = DayStatus(arrival.value)  # PRESENT or LATE
    elif pending:
        day_status = DayStatus.PENDING_REVIEW
    else:
        day_status = base_day_status

    if pending:
        verification = VerificationStatus.PENDING_REVIEW
    elif counted:
        verification = VerificationStatus.VERIFIED
    else:
        verification = None

    return DaySummary(first_in, last_out, worked, arrival, departure, day_status, verification)
