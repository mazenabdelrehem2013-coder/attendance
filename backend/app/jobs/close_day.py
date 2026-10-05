r"""End-of-day job: finalise a finished day for every employee.

  - check-ins never checked out          -> session MISSING_CHECKOUT (no hours counted)
  - no check-in on a working day         -> stored ABSENT record
    (not on leave, holidays, days off, or before the hire date)

Safe to run more than once for the same day. In production Cloud Scheduler runs it every
night (Phase 18); locally:

    .venv\Scripts\python -m app.jobs.close_day                  (yesterday)
    .venv\Scripts\python -m app.jobs.close_day --date 2026-10-02
"""

import argparse
import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core import clock
from app.models import (
    Attendance,
    AttendanceSession,
    Employee,
    EmployeeLocation,
    Organization,
)
from app.models.enums import DayStatus, EmploymentStatus, NotificationEvent, SessionStatus
from app.services.attendance.service import recompute
from app.services.audit import write_audit
from app.services.calendar_index import WORKING_DAY, CalendarIndex, primary_location
from app.services.notifications import notify, rules

log = logging.getLogger("app.jobs.close_day")


@dataclass
class CloseResult:
    day: date
    missing_checkouts: int = 0
    absences: int = 0
    alerts: int = 0


def _absence_alerts(db: Session, org_id: uuid.UUID, day: date, absent: list[Employee], rule) -> int:
    """HIGH_ABSENCE: an employee reached N absences within the last D days (default 3 in 30).
    Sent at most once per employee per D-day block."""
    limit, days = int(rule.thresholds.get("absences", 3)), int(rule.thresholds.get("days", 30))
    since = day - timedelta(days=days - 1)
    counts = dict(db.execute(
        select(Attendance.employee_id, func.count())
        .where(Attendance.employee_id.in_([e.id for e in absent]), Attendance.day_status == DayStatus.ABSENT,
               Attendance.attendance_date.between(since, day))
        .group_by(Attendance.employee_id)
    ).all())
    created = 0
    for emp in absent:
        count = counts.get(emp.id, 0)
        if count < limit:
            continue
        created += notify(
            db, organization_id=org_id, employee=emp, event=NotificationEvent.HIGH_ABSENCE,
            title=f"Frequent absence: {emp.full_name}",
            lines=[f"{emp.full_name} has been absent {count} times in the last {days} days."],
            rows=[("Employee", f"{emp.full_name} ({emp.employee_code})"),
                  ("Absences", f"{count} in {days} days"), ("Latest", day.strftime("%a %d %b %Y"))],
            link="/reports", dedupe_key=f"absence:{emp.id}:{day.toordinal() // days}", rule=rule,
        )
    return created


def close_day(db: Session, org_id: uuid.UUID, day: date) -> CloseResult:
    org = db.get(Organization, org_id)
    today = clock.now().astimezone(ZoneInfo(org.default_timezone)).date()
    if day >= today:
        raise ValueError(f"{day} is not over yet in {org.default_timezone}.")
    result = CloseResult(day)

    # 1. Sessions of that day (or earlier) that are still open.
    stale = db.execute(
        select(AttendanceSession, Attendance)
        .join(Attendance, Attendance.id == AttendanceSession.attendance_id)
        .join(Employee, Employee.id == Attendance.employee_id)
        .where(
            Employee.organization_id == org_id,
            AttendanceSession.status == SessionStatus.OPEN,
            Attendance.attendance_date <= day,
        )
        .with_for_update(of=AttendanceSession)
    ).all()
    alert_rules = rules(db, org_id)
    for session, attendance in stale:
        session.status = SessionStatus.MISSING_CHECKOUT
        session.worked_minutes = 0
        db.flush()
        recompute(db, attendance)
        result.missing_checkouts += 1
        employee = db.get(Employee, attendance.employee_id)
        when = attendance.attendance_date.strftime("%a %d %b %Y")
        result.alerts += notify(
            db, organization_id=org_id, employee=employee, event=NotificationEvent.MISSING_CHECKOUT,
            title=f"Missing check-out: {employee.full_name}",
            lines=[f"{employee.full_name} checked in on {when} but never checked out. "
                   "Hours of that visit are not counted."],
            rows=[("Employee", f"{employee.full_name} ({employee.employee_code})"), ("Date", when)],
            link="/attendance", dedupe_key=f"no-out:{employee.id}:{attendance.attendance_date.isoformat()}",
            rule=alert_rules[NotificationEvent.MISSING_CHECKOUT],
        )

    # 2. Absences: working day, no attendance record at all.
    employees = list(db.scalars(
        select(Employee)
        .where(Employee.organization_id == org_id, Employee.employment_status == EmploymentStatus.ACTIVE)
        .options(selectinload(Employee.locations).selectinload(EmployeeLocation.location))
    ))
    have_record = set(db.scalars(
        select(Attendance.employee_id).where(
            Attendance.employee_id.in_([e.id for e in employees]), Attendance.attendance_date == day
        )
    ))
    calendar = CalendarIndex(db, org_id, [e.id for e in employees], day, day)
    absent: list[Employee] = []
    for emp in employees:
        if emp.id in have_record:
            continue
        location = primary_location(emp)
        info = calendar.day(emp, location, day)
        if info.kind != WORKING_DAY or location is None:
            continue
        db.add(Attendance(
            employee_id=emp.id,
            attendance_date=day,
            location_id=location.id,
            scheduled_start=info.hours.start_time if info.hours else None,
            scheduled_end=info.hours.end_time if info.hours else None,
            day_status=DayStatus.ABSENT,
        ))
        result.absences += 1
        absent.append(emp)

    if absent:
        db.flush()
        result.alerts += _absence_alerts(db, org_id, day, absent, alert_rules[NotificationEvent.HIGH_ABSENCE])

    write_audit(
        db, action="DAY_CLOSED", organization_id=org_id, actor_user_id=None, actor_role="SYSTEM",
        object_type="attendance_day", object_id=day.isoformat(),
        new_value={"missing_checkouts": result.missing_checkouts, "absences": result.absences},
    )
    db.commit()
    log.info("Day closed", extra={"day": day.isoformat(), "missing_checkouts": result.missing_checkouts,
                                  "absences": result.absences})
    return result


def main() -> None:
    from app.core.config import get_settings
    from app.core.logging import configure_logging
    from app.db.session import make_session_factory

    parser = argparse.ArgumentParser(description="Close a finished attendance day")
    parser.add_argument("--date", type=date.fromisoformat, help="Day to close (default: yesterday)")
    args = parser.parse_args()
    configure_logging(get_settings().log_level)

    Session_ = make_session_factory()
    with Session_() as db:
        for org in db.scalars(select(Organization).where(Organization.is_active)):
            day = args.date or clock.now().astimezone(ZoneInfo(org.default_timezone)).date() - timedelta(days=1)
            r = close_day(db, org.id, day)
            print(f"{org.name}: {day} closed - {r.missing_checkouts} missing check-out(s), {r.absences} absence(s)")


if __name__ == "__main__":
    main()
