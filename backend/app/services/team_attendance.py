"""Attendance of a team (manager) or the whole company (HR) for one day.

Every employee in scope gets one row - also those without any check-in, whose status is
worked out here: ON_LEAVE, HOLIDAY, NON_WORKING_DAY, NOT_CHECKED_IN (day still running) or
ABSENT (working day over). Everything is loaded in a few queries, so a 500-person company
is one quick request.
"""

import uuid
from dataclasses import dataclass
from datetime import date, time
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core import clock
from app.models import (
    Attendance,
    AttendanceSession,
    Employee,
    EmployeeLocation,
    Holiday,
    LeaveRecord,
    Location,
    Organization,
    User,
    WorkSchedule,
)
from app.models.enums import (
    DepartureStatus,
    EmploymentStatus,
    LeaveStatus,
    SessionStatus,
    VerificationStatus,
)
from app.schemas.team import TeamAttendance, TeamRow, TeamSummary
from app.services.scope import employee_scope

ALL_STATUSES = (
    "PRESENT", "LATE", "PENDING_REVIEW", "NOT_CHECKED_IN", "ABSENT",
    "ON_LEAVE", "HOLIDAY", "NON_WORKING_DAY",
)


@dataclass
class TeamFilters:
    q: str | None = None
    employee_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    statuses: list[str] | None = None


def _primary(emp: Employee) -> Location | None:
    links = [l for l in emp.locations if l.location.is_active]
    if not links:
        return None
    return next((l.location for l in links if l.is_primary), links[0].location)


def team_day(db: Session, user: User, day: date, filters: TeamFilters) -> TeamAttendance:
    org = db.get(Organization, user.organization_id)
    now = clock.now()

    # 1. Employees in scope (manager: own team; HR/admin: everyone).
    query = (
        select(Employee)
        .join(User, User.id == Employee.user_id)
        .where(employee_scope(db, user), Employee.employment_status == EmploymentStatus.ACTIVE)
        .options(
            selectinload(Employee.department),
            selectinload(Employee.locations).selectinload(EmployeeLocation.location),
        )
    )
    if filters.q:
        like = f"%{filters.q.strip()}%"
        query = query.where(or_(Employee.full_name.ilike(like), Employee.employee_code.ilike(like)))
    if filters.employee_id:
        query = query.where(Employee.id == filters.employee_id)
    if filters.department_id:
        query = query.where(Employee.department_id == filters.department_id)
    if filters.location_id:
        query = query.where(Employee.id.in_(
            select(EmployeeLocation.employee_id).where(EmployeeLocation.location_id == filters.location_id)
        ))
    employees = list(db.scalars(query.order_by(Employee.full_name)))
    ids = [e.id for e in employees]

    # 2. Everything else for that day, in bulk.
    attendance = {
        a.employee_id: a
        for a in db.scalars(select(Attendance).where(Attendance.employee_id.in_(ids), Attendance.attendance_date == day))
    }
    open_sessions = set(
        db.scalars(
            select(AttendanceSession.attendance_id).where(
                AttendanceSession.attendance_id.in_([a.id for a in attendance.values()]),
                AttendanceSession.status == SessionStatus.OPEN,
            )
        )
    )
    leave = {
        l.employee_id: l.leave_type.value
        for l in db.scalars(
            select(LeaveRecord).where(
                LeaveRecord.employee_id.in_(ids),
                LeaveRecord.status == LeaveStatus.APPROVED,
                LeaveRecord.start_date <= day,
                LeaveRecord.end_date >= day,
            )
        )
    }
    holidays = {
        h.location_id
        for h in db.scalars(
            select(Holiday).where(Holiday.organization_id == org.id, Holiday.holiday_date == day)
        )
    }
    schedules = {
        s.id: {d.weekday: d for d in s.days}
        for s in db.scalars(
            select(WorkSchedule)
            .where(WorkSchedule.organization_id == org.id, WorkSchedule.is_active)
            .options(selectinload(WorkSchedule.days))
        )
    }
    locations = {l.id: l for l in db.scalars(select(Location).where(Location.organization_id == org.id))}

    # 3. One row per employee.
    rows: list[TeamRow] = []
    for emp in employees:
        a = attendance.get(emp.id)
        location = locations.get(a.location_id) if a and a.location_id else _primary(emp)
        tz = ZoneInfo(location.timezone if location else org.default_timezone)
        local_now = now.astimezone(tz)
        day_over = day < local_now.date()
        checked_in_now = bool(a and a.id in open_sessions and not day_over)
        missing_checkout = bool(
            a and (a.departure_status == DepartureStatus.MISSING_CHECKOUT or (a.id in open_sessions and day_over))
        )

        if a and a.day_status and a.day_status.value in ("PRESENT", "LATE", "PENDING_REVIEW"):
            status = a.day_status.value
        elif emp.id in leave:
            status = "ON_LEAVE"
        elif location is not None and (None in holidays or location.id in holidays):
            status = "HOLIDAY"
        else:
            schedule_id = emp.work_schedule_id or (location.work_schedule_id if location else None)
            today_hours = schedules.get(schedule_id, {}).get(day.weekday()) if schedule_id else None
            if schedule_id in schedules and today_hours is None:
                status = "NON_WORKING_DAY"
            else:
                end = today_hours.end_time if today_hours else time(23, 59)
                finished = day_over or (day == local_now.date() and local_now.time() >= end)
                status = "ABSENT" if finished else "NOT_CHECKED_IN"

        rows.append(TeamRow(
            employee_id=emp.id,
            employee_code=emp.employee_code,
            full_name=emp.full_name,
            department=emp.department.name if emp.department else None,
            location=location.name if location else None,
            check_in=a.first_check_in_at if a else None,
            check_out=a.last_check_out_at if a else None,
            worked_minutes=a.worked_minutes if a else 0,
            status=status,
            arrival_status=a.arrival_status.value if a and a.arrival_status else None,
            departure_status="MISSING_CHECKOUT" if missing_checkout else (
                a.departure_status.value if a and a.departure_status else None),
            checked_in_now=checked_in_now,
            verification_status=a.verification_status.value if a and a.verification_status else None,
            note=leave.get(emp.id),
        ))

    summary = TeamSummary(
        total_employees=len(rows),
        present=sum(r.status in ("PRESENT", "LATE") for r in rows),
        late=sum(r.status == "LATE" for r in rows),
        absent=sum(r.status == "ABSENT" for r in rows),
        not_checked_in=sum(r.status == "NOT_CHECKED_IN" for r in rows),
        checked_in_now=sum(r.checked_in_now for r in rows),
        missing_checkout=sum(r.departure_status == "MISSING_CHECKOUT" for r in rows),
        suspicious=sum(r.verification_status == VerificationStatus.PENDING_REVIEW.value for r in rows),
        on_leave=sum(r.status == "ON_LEAVE" for r in rows),
    )
    if filters.statuses:
        wanted = set(filters.statuses)
        rows = [
            r for r in rows
            if r.status in wanted
            or ("MISSING_CHECKOUT" in wanted and r.departure_status == "MISSING_CHECKOUT")
            or ("CHECKED_IN" in wanted and r.checked_in_now)
            or ("SUSPICIOUS" in wanted and r.verification_status == "PENDING_REVIEW")
        ]
    return TeamAttendance(date=day, generated_at=now, summary=summary, rows=rows)


def org_today(db: Session, user: User) -> date:
    org = db.get(Organization, user.organization_id)
    return clock.now().astimezone(ZoneInfo(org.default_timezone)).date()

