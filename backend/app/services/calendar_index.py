"""Bulk "what kind of day was it" for many employees over a date range, in a few queries
(used by reports and the end-of-day job, where per-employee lookups would be too slow)."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Employee, Holiday, LeaveRecord, Location, WorkSchedule, WorkScheduleDay
from app.models.enums import LeaveStatus

WORKING_DAY = "WORKING_DAY"
NON_WORKING_DAY = "NON_WORKING_DAY"
HOLIDAY = "HOLIDAY"
ON_LEAVE = "ON_LEAVE"
NOT_EMPLOYED = "NOT_EMPLOYED"  # before the hire date


@dataclass(frozen=True)
class DayInfo:
    kind: str
    hours: WorkScheduleDay | None = None  # set on working days with a schedule
    leave_type: str | None = None
    holiday: str | None = None


class CalendarIndex:
    def __init__(self, db: Session, org_id: uuid.UUID, employee_ids: list[uuid.UUID], start: date, end: date):
        self._leave: dict[uuid.UUID, list[LeaveRecord]] = defaultdict(list)
        for leave in db.scalars(
            select(LeaveRecord).where(
                LeaveRecord.employee_id.in_(employee_ids),
                LeaveRecord.status == LeaveStatus.APPROVED,
                LeaveRecord.start_date <= end,
                LeaveRecord.end_date >= start,
            )
        ):
            self._leave[leave.employee_id].append(leave)
        self._holidays: dict[tuple[date, uuid.UUID | None], str] = {
            (h.holiday_date, h.location_id): h.name
            for h in db.scalars(
                select(Holiday).where(
                    Holiday.organization_id == org_id, Holiday.holiday_date.between(start, end)
                )
            )
        }
        self._schedules: dict[uuid.UUID, dict[int, WorkScheduleDay]] = {
            s.id: {d.weekday: d for d in s.days}
            for s in db.scalars(
                select(WorkSchedule)
                .where(WorkSchedule.organization_id == org_id, WorkSchedule.is_active)
                .options(selectinload(WorkSchedule.days))
            )
        }

    def day(self, employee: Employee, location: Location | None, day: date) -> DayInfo:
        if employee.hire_date and day < employee.hire_date:
            return DayInfo(NOT_EMPLOYED)
        leave = next((l for l in self._leave[employee.id] if l.start_date <= day <= l.end_date), None)
        if leave is not None:
            return DayInfo(ON_LEAVE, leave_type=leave.leave_type.value)
        holiday = self._holidays.get((day, None)) or (
            self._holidays.get((day, location.id)) if location else None
        )
        if holiday:
            return DayInfo(HOLIDAY, holiday=holiday)
        schedule_id = employee.work_schedule_id or (location.work_schedule_id if location else None)
        if schedule_id is None or schedule_id not in self._schedules:
            return DayInfo(WORKING_DAY)  # no working hours set up: every day counts
        hours = self._schedules[schedule_id].get(day.weekday())
        return DayInfo(WORKING_DAY, hours=hours) if hours else DayInfo(NON_WORKING_DAY)


def primary_location(employee: Employee) -> Location | None:
    """Needs Employee.locations loaded with their Location."""
    links = [l for l in employee.locations if l.location.is_active]
    if not links:
        return None
    return next((l.location for l in links if l.is_primary), links[0].location)
