"""Attendance rules with the agreed schedule: 09:00-18:00, 15 minutes grace, Lagos time."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.enums import (
    ArrivalStatus,
    DayStatus,
    DepartureStatus,
    SessionStatus,
    VerificationStatus,
)
from app.services.attendance.rules import ScheduleView, SessionView, summarize

TZ = "Africa/Lagos"
DAY = date(2026, 10, 5)  # a Monday
SCHEDULE = ScheduleView(start=time(9), end=time(18), grace_minutes=15, early_departure_minutes=0)


def at(hh: int, mm: int, ss: int = 0, day: date = DAY) -> datetime:
    """Lagos local time -> UTC (as the server stores it)."""
    return datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=ZoneInfo(TZ)).astimezone(UTC)


def closed(i, o, **kw):
    return SessionView(i, o, SessionStatus.CLOSED, **kw)


def open_(i, **kw):
    return SessionView(i, None, SessionStatus.OPEN, **kw)


def run(*sessions, schedule=SCHEDULE, base=None):
    return summarize(sessions, DAY, schedule, TZ, base)


# --- Arrival --------------------------------------------------------------------------------


def test_0907_is_present():
    assert run(open_(at(9, 7))).arrival_status == ArrivalStatus.PRESENT


def test_exactly_end_of_grace_is_present():
    assert run(open_(at(9, 15, 0))).arrival_status == ArrivalStatus.PRESENT


def test_one_second_after_grace_is_late():
    assert run(open_(at(9, 15, 1))).arrival_status == ArrivalStatus.LATE


def test_0925_is_late():
    s = run(open_(at(9, 25)))
    assert s.arrival_status == ArrivalStatus.LATE
    assert s.day_status == DayStatus.LATE


def test_early_arrival_is_present():
    assert run(open_(at(7, 45))).arrival_status == ArrivalStatus.PRESENT


def test_lateness_uses_first_check_in_of_the_day():
    s = run(closed(at(9, 5), at(12, 0)), open_(at(13, 30)))
    assert s.arrival_status == ArrivalStatus.PRESENT


def test_timezone_is_respected():
    # 08:10 UTC is 09:10 in Lagos (UTC+1) -> PRESENT, not "08:10 = early".
    s = run(open_(datetime(2026, 10, 5, 8, 10, tzinfo=UTC)))
    assert s.arrival_status == ArrivalStatus.PRESENT
    s = run(open_(datetime(2026, 10, 5, 8, 20, tzinfo=UTC)))  # 09:20 Lagos
    assert s.arrival_status == ArrivalStatus.LATE


# --- Departure & hours ----------------------------------------------------------------------


def test_full_day():
    s = run(closed(at(9, 0), at(18, 0)))
    assert s.departure_status == DepartureStatus.CHECKED_OUT
    assert s.worked_minutes == 540


def test_leaving_before_end_is_early_departure():
    assert run(closed(at(9, 0), at(17, 59))).departure_status == DepartureStatus.EARLY_DEPARTURE


def test_early_departure_allowance():
    schedule = ScheduleView(time(9), time(18), 15, early_departure_minutes=10)
    assert run(closed(at(9, 0), at(17, 50)), schedule=schedule).departure_status == DepartureStatus.CHECKED_OUT
    assert run(closed(at(9, 0), at(17, 49)), schedule=schedule).departure_status == DepartureStatus.EARLY_DEPARTURE


def test_several_sessions_are_added_up():
    s = run(closed(at(9, 0), at(12, 30)), closed(at(13, 15), at(18, 5)))
    assert s.worked_minutes == 210 + 290
    assert s.first_check_in_at == at(9, 0)
    assert s.last_check_out_at == at(18, 5)
    assert s.departure_status == DepartureStatus.CHECKED_OUT


def test_while_checked_in_there_is_no_departure_status_yet():
    s = run(closed(at(9, 0), at(12, 0)), open_(at(13, 0)))
    assert s.departure_status is None
    assert s.last_check_out_at is None
    assert s.worked_minutes == 180  # only finished sessions count so far


def test_missing_checkout():
    s = run(SessionView(at(9, 0), None, SessionStatus.MISSING_CHECKOUT))
    assert s.departure_status == DepartureStatus.MISSING_CHECKOUT
    assert s.worked_minutes == 0


def test_checkout_after_midnight_is_not_early():
    next_day = DAY + timedelta(days=1)
    s = run(closed(at(9, 0), at(0, 30, day=next_day)))
    assert s.departure_status == DepartureStatus.CHECKED_OUT
    assert s.worked_minutes == 15 * 60 + 30


# --- Flagged (pending HR review) ------------------------------------------------------------


def test_flagged_check_in_does_not_count_until_approved():
    s = run(open_(at(9, 0), pending_review=True))
    assert s.arrival_status is None
    assert s.day_status == DayStatus.PENDING_REVIEW
    assert s.verification_status == VerificationStatus.PENDING_REVIEW
    assert s.worked_minutes == 0


def test_verified_session_plus_pending_session():
    s = run(closed(at(9, 0), at(12, 0)), closed(at(13, 0), at(18, 0), pending_review=True))
    assert s.worked_minutes == 180
    assert s.day_status == DayStatus.PRESENT
    assert s.verification_status == VerificationStatus.PENDING_REVIEW


def test_rejected_session_is_ignored():
    s = run(SessionView(at(9, 0), at(18, 0), SessionStatus.REJECTED))
    assert s.worked_minutes == 0 and s.day_status is None and s.verification_status is None


def test_all_verified():
    assert run(closed(at(9, 0), at(18, 0))).verification_status == VerificationStatus.VERIFIED


# --- Days without working hours -------------------------------------------------------------


def test_working_on_a_holiday_is_present_never_late():
    s = run(open_(at(11, 0)), schedule=None, base=DayStatus.HOLIDAY)
    assert s.arrival_status == ArrivalStatus.PRESENT


def test_holiday_without_attendance_keeps_holiday_status():
    assert run(schedule=None, base=DayStatus.HOLIDAY).day_status == DayStatus.HOLIDAY


def test_rejected_check_out_keeps_arrival_but_not_hours():
    s = run(SessionView(at(9, 0), at(18, 0), SessionStatus.MISSING_CHECKOUT))
    assert s.arrival_status == ArrivalStatus.PRESENT
    assert s.worked_minutes == 0
    assert s.departure_status == DepartureStatus.MISSING_CHECKOUT
    assert s.last_check_out_at is None
