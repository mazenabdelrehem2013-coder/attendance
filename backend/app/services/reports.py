"""Report data (shown on screen, exported to Excel/PDF in Phase 14, emailed in Phase 15).

Scope is always the requesting user's: managers get their own team, HR/admins everyone.
Location data is never included beyond the office name (privacy - spec section 25).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core import clock
from app.core.errors import AppError
from app.models import (
    Attendance,
    AttendanceEvent,
    AttendanceEventReview,
    Employee,
    EmployeeLocation,
    Location,
    Manager,
    Organization,
    User,
)
from app.models.enums import DayStatus, EmploymentStatus, EventResult
from app.schemas.reports import (
    DailyReport,
    DailyRow,
    EmployeePeriod,
    EventRow,
    GroupTotal,
    ListReport,
    PeriodReport,
)
from app.services.calendar_index import (
    HOLIDAY,
    NOT_EMPLOYED,
    ON_LEAVE,
    WORKING_DAY,
    CalendarIndex,
    primary_location,
)
from app.services.scope import employee_scope
from app.services.team_attendance import TeamFilters, team_day

MAX_PERIOD_DAYS = 366

REASON_TEXT = {
    "OUTSIDE_LOCATION": "Outside the office radius",
    "POOR_ACCURACY": "GPS signal too weak",
    "STALE_LOCATION": "Old GPS reading",
    "MOCK_LOCATION": "Fake-GPS app detected",
    "INTEGRITY_FAIL": "App/phone integrity failed",
    "INTEGRITY_MISSING": "No integrity token",
    "IMPOSSIBLE_TRAVEL": "Impossible travel speed",
    "CLOCK_SKEW": "Phone clock changed",
    "QR_INVALID": "Invalid office QR",
    "QR_MISSING": "Office QR not scanned",
    "MULTIPLE_WARNINGS": "Several small doubts",
    "BAD_SIGNATURE": "Not signed by the approved phone",
    "REPLAY": "Re-used request",
}


@dataclass
class ReportFilters:
    department_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None


def _org_tz(db: Session, user: User) -> ZoneInfo:
    return ZoneInfo(db.get(Organization, user.organization_id).default_timezone)


def _hhmm(moment: datetime | None, tz: ZoneInfo) -> str | None:
    return moment.astimezone(tz).strftime("%H:%M") if moment else None


def _minutes_of_day(moment: datetime, tz: ZoneInfo) -> int:
    local = moment.astimezone(tz)
    return local.hour * 60 + local.minute


def _fmt_minutes_of_day(value: float | None) -> str | None:
    if value is None:
        return None
    m = round(value)
    return f"{m // 60:02d}:{m % 60:02d}"


def _employees(db: Session, user: User, f: ReportFilters) -> list[Employee]:
    query = (
        select(Employee)
        .where(employee_scope(db, user), Employee.employment_status == EmploymentStatus.ACTIVE)
        .options(
            selectinload(Employee.department),
            selectinload(Employee.manager).selectinload(Manager.employee),
            selectinload(Employee.manager).selectinload(Manager.user),
            selectinload(Employee.locations).selectinload(EmployeeLocation.location),
        )
    )
    if f.department_id:
        query = query.where(Employee.department_id == f.department_id)
    if f.manager_id:
        query = query.where(Employee.manager_id == f.manager_id)
    if f.employee_id:
        query = query.where(Employee.id == f.employee_id)
    if f.location_id:
        query = query.where(Employee.id.in_(
            select(EmployeeLocation.employee_id).where(EmployeeLocation.location_id == f.location_id)))
    return list(db.scalars(query.order_by(Employee.full_name)))


def _manager_name(emp: Employee) -> str | None:
    if not emp.manager:
        return None
    return emp.manager.employee.full_name if emp.manager.employee else emp.manager.user.email


def _check_range(start: date, end: date, max_days: int = MAX_PERIOD_DAYS) -> None:
    if end < start:
        raise AppError(422, "VALIDATION_ERROR", "'to' must be on or after 'from'.")
    if (end - start).days >= max_days:
        raise AppError(422, "VALIDATION_ERROR", f"Choose at most {max_days} days.")


# --- Daily ----------------------------------------------------------------------------------


def daily(db: Session, user: User, day: date, f: ReportFilters) -> DailyReport:
    tz = _org_tz(db, user)
    team = team_day(db, user, day, TeamFilters(
        employee_id=f.employee_id, department_id=f.department_id, location_id=f.location_id))
    managers = {e.id: _manager_name(e) for e in _employees(db, user, f)}
    rows = [
        DailyRow(
            employee=r.full_name, employee_code=r.employee_code, department=r.department,
            manager=managers.get(r.employee_id), location=r.location,
            check_in=_hhmm(r.check_in, tz), check_out=_hhmm(r.check_out, tz),
            worked_minutes=r.worked_minutes,
            status=r.status,
            departure_status=r.departure_status,
            verification_status=r.verification_status,
        )
        for r in team.rows
        if not f.manager_id or r.employee_id in managers
    ]
    s = team.summary
    return DailyReport(
        title="Daily attendance report", date=day, generated_at=clock.now(), rows=rows,
        totals={"employees": s.total_employees, "present": s.present, "late": s.late, "absent": s.absent,
                "missing_checkout": s.missing_checkout, "pending_review": s.suspicious, "on_leave": s.on_leave},
    )


# --- Period (weekly / monthly / any range) --------------------------------------------------


def period(db: Session, user: User, start: date, end: date, f: ReportFilters, title: str) -> PeriodReport:
    _check_range(start, end)
    tz = _org_tz(db, user)
    today = clock.now().astimezone(tz).date()
    employees = _employees(db, user, f)
    ids = [e.id for e in employees]
    calendar = CalendarIndex(db, user.organization_id, ids, start, end)
    records: dict[uuid.UUID, dict[date, Attendance]] = defaultdict(dict)
    for a in db.scalars(select(Attendance).where(
            Attendance.employee_id.in_(ids), Attendance.attendance_date.between(start, end))):
        records[a.employee_id][a.attendance_date] = a

    rows: list[EmployeePeriod] = []
    for emp in employees:
        location = primary_location(emp)
        c = defaultdict(int)
        ins, outs, worked = [], [], []
        day = start
        while day <= end and day <= today:
            a = records[emp.id].get(day)
            info = calendar.day(emp, location, day)
            status = a.day_status if a else None
            attended = status in (DayStatus.PRESENT, DayStatus.LATE)
            if info.kind == NOT_EMPLOYED:
                pass
            elif info.kind == ON_LEAVE and not attended:
                c["leave"] += 1
            elif info.kind == HOLIDAY and not attended:
                c["holiday"] += 1
            elif info.kind == WORKING_DAY or attended:
                # Today counts as a working day only once the person has attended - before the
                # day is over nobody is "absent" yet, so it mustn't lower the attendance rate.
                if info.kind == WORKING_DAY and (day < today or attended):
                    c["working"] += 1
                if attended:
                    c["present"] += 1
                    c["late"] += status == DayStatus.LATE
                    ins.append(_minutes_of_day(a.first_check_in_at, tz))
                    if a.last_check_out_at:
                        outs.append(_minutes_of_day(a.last_check_out_at, tz))
                    if a.worked_minutes:
                        worked.append(a.worked_minutes)
                    c["early"] += (a.departure_status is not None and a.departure_status.value == "EARLY_DEPARTURE")
                    c["missing"] += (a.departure_status is not None and a.departure_status.value == "MISSING_CHECKOUT")
                elif status == DayStatus.PENDING_REVIEW:
                    c["pending"] += 1
                elif day < today:
                    c["absent"] += 1
            day += timedelta(days=1)
        rows.append(EmployeePeriod(
            employee_id=emp.id, employee=emp.full_name, employee_code=emp.employee_code,
            department=emp.department.name if emp.department else None, manager=_manager_name(emp),
            location=location.name if location else None,
            working_days=c["working"], present_days=c["present"], late_days=c["late"],
            absent_days=c["absent"], pending_review_days=c["pending"], leave_days=c["leave"],
            holiday_days=c["holiday"], early_departure_days=c["early"], missing_checkout_days=c["missing"],
            average_check_in=_fmt_minutes_of_day(mean(ins) if ins else None),
            average_check_out=_fmt_minutes_of_day(mean(outs) if outs else None),
            average_worked_minutes=round(mean(worked)) if worked else None,
            total_worked_minutes=sum(worked),
            attendance_rate=round(c["present"] / c["working"], 4) if c["working"] else None,
        ))

    def group(key) -> list[GroupTotal]:
        buckets: dict[str, list[EmployeePeriod]] = defaultdict(list)
        for r in rows:
            buckets[key(r) or "—"].append(r)
        out = []
        for name, rs in sorted(buckets.items()):
            working = sum(r.working_days for r in rs)
            present = sum(r.present_days for r in rs)
            out.append(GroupTotal(
                name=name, employees=len(rs), working_days=working, present_days=present,
                late_days=sum(r.late_days for r in rs), absent_days=sum(r.absent_days for r in rs),
                attendance_rate=round(present / working, 4) if working else None))
        return out

    working = sum(r.working_days for r in rows)
    present = sum(r.present_days for r in rows)
    return PeriodReport(
        title=title, date_from=start, date_to=end, generated_at=clock.now(), rows=rows,
        totals={
            "employees": len(rows), "working_days": working, "present_days": present,
            "late_days": sum(r.late_days for r in rows), "absent_days": sum(r.absent_days for r in rows),
            "early_departure_days": sum(r.early_departure_days for r in rows),
            "missing_checkout_days": sum(r.missing_checkout_days for r in rows),
            "total_worked_minutes": sum(r.total_worked_minutes for r in rows),
            "attendance_rate": round(present / working, 4) if working else None,
        },
        by_location=group(lambda r: r.location),
        by_department=group(lambda r: r.department),
        by_manager=group(lambda r: r.manager),
    )


def month_range(month: str) -> tuple[date, date]:
    try:
        year, mon = (int(x) for x in month.split("-"))
        first = date(year, mon, 1)
    except (ValueError, TypeError):
        raise AppError(422, "VALIDATION_ERROR", "Month must look like 2026-10.") from None
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return first, last


def week_range(any_day: date) -> tuple[date, date]:
    monday = any_day - timedelta(days=any_day.weekday())
    return monday, monday + timedelta(days=6)


# --- Lists: late, absence, suspicious ------------------------------------------------------


def _employee_index(db: Session, user: User, f: ReportFilters) -> dict[uuid.UUID, Employee]:
    return {e.id: e for e in _employees(db, user, f)}


def late_list(db: Session, user: User, start: date, end: date, f: ReportFilters) -> ListReport:
    _check_range(start, end)
    tz = _org_tz(db, user)
    emps = _employee_index(db, user, f)
    rows = []
    for a in db.scalars(select(Attendance).where(
            Attendance.employee_id.in_(emps), Attendance.attendance_date.between(start, end),
            Attendance.day_status == DayStatus.LATE).order_by(Attendance.attendance_date)):
        e = emps[a.employee_id]
        minutes = None
        if a.scheduled_start and a.first_check_in_at:
            arrived = a.first_check_in_at.astimezone(tz)
            minutes = (arrived.hour * 60 + arrived.minute) - (a.scheduled_start.hour * 60 + a.scheduled_start.minute)
        loc = db.get(Location, a.location_id) if a.location_id else None
        rows.append(EventRow(
            date=a.attendance_date, employee=e.full_name, employee_code=e.employee_code,
            department=e.department.name if e.department else None, location=loc.name if loc else None,
            detail=f"Arrived {_hhmm(a.first_check_in_at, tz)}" + (f" ({minutes} min late)" if minutes else ""),
            minutes=minutes))
    return ListReport(title="Late arrivals", date_from=start, date_to=end, generated_at=clock.now(), rows=rows)


def absence_list(db: Session, user: User, start: date, end: date, f: ReportFilters) -> ListReport:
    """Absences come from the period calculation, so they match the monthly numbers exactly."""
    _check_range(start, end)
    tz = _org_tz(db, user)
    today = clock.now().astimezone(tz).date()
    employees = _employees(db, user, f)
    calendar = CalendarIndex(db, user.organization_id, [e.id for e in employees], start, end)
    attended = {
        (a.employee_id, a.attendance_date)
        for a in db.scalars(select(Attendance).where(
            Attendance.employee_id.in_([e.id for e in employees]), Attendance.attendance_date.between(start, end),
            Attendance.day_status.in_([DayStatus.PRESENT, DayStatus.LATE, DayStatus.PENDING_REVIEW])))
    }
    rows = []
    day = start
    while day <= end and day < today:
        for e in employees:
            location = primary_location(e)
            if (e.id, day) not in attended and calendar.day(e, location, day).kind == WORKING_DAY:
                rows.append(EventRow(
                    date=day, employee=e.full_name, employee_code=e.employee_code,
                    department=e.department.name if e.department else None,
                    location=location.name if location else None, detail="Absent"))
        day += timedelta(days=1)
    return ListReport(title="Absences", date_from=start, date_to=end, generated_at=clock.now(), rows=rows)


def suspicious_list(db: Session, user: User, start: date, end: date, f: ReportFilters) -> ListReport:
    _check_range(start, end)
    tz = _org_tz(db, user)
    emps = _employee_index(db, user, f)
    begin = datetime.combine(start, datetime.min.time(), tz)
    finish = datetime.combine(end + timedelta(days=1), datetime.min.time(), tz)
    rows = []
    query = (
        select(AttendanceEvent, AttendanceEventReview, Location)
        .outerjoin(AttendanceEventReview, AttendanceEventReview.event_id == AttendanceEvent.id)
        .outerjoin(Location, Location.id == AttendanceEvent.location_id)
        .where(
            AttendanceEvent.employee_id.in_(emps),
            AttendanceEvent.server_received_at >= begin, AttendanceEvent.server_received_at < finish,
            or_(AttendanceEvent.result == EventResult.FLAGGED, AttendanceEvent.result == EventResult.REJECTED),
        )
        .order_by(AttendanceEvent.server_received_at)
    )
    for ev, review, loc in db.execute(query):
        e = emps[ev.employee_id]
        outcome = (f"HR {review.decision.value.lower()}" if review
                   else "waiting for HR" if ev.result == EventResult.FLAGGED else "rejected automatically")
        action = "Check-in" if ev.event_type.value == "CHECK_IN" else "Check-out"
        reason = REASON_TEXT.get(ev.reason_code or "", ev.reason_code or "")
        rows.append(EventRow(
            date=ev.server_received_at.astimezone(tz).date(), employee=e.full_name, employee_code=e.employee_code,
            department=e.department.name if e.department else None, location=loc.name if loc else None,
            detail=f"{_hhmm(ev.server_received_at, tz)} {action}: {reason} – {outcome}"))
    return ListReport(title="Suspicious attendance", date_from=start, date_to=end,
                      generated_at=clock.now(), rows=rows)
