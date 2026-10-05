"""What kind of day is it for this employee at this location? (working / weekend / holiday / leave)"""

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Employee, Holiday, LeaveRecord, Location, WorkSchedule
from app.models.enums import LeaveStatus


class DayType(StrEnum):
    WORKING_DAY = "WORKING_DAY"
    NON_WORKING_DAY = "NON_WORKING_DAY"
    HOLIDAY = "HOLIDAY"
    ON_LEAVE = "ON_LEAVE"


@dataclass(frozen=True)
class DayContext:
    local_date: date
    timezone: str
    day_type: DayType
    scheduled_start: time | None = None
    scheduled_end: time | None = None
    grace_minutes: int | None = None
    early_departure_minutes: int | None = None
    description: str | None = None  # holiday name or leave type


def local_date(moment: datetime, timezone: str) -> date:
    return moment.astimezone(ZoneInfo(timezone)).date()


def resolve_schedule(db: Session, employee: Employee, location: Location) -> WorkSchedule | None:
    """An employee's own schedule overrides the location's."""
    schedule_id = employee.work_schedule_id or location.work_schedule_id
    if schedule_id is None:
        return None
    return db.scalar(
        select(WorkSchedule)
        .where(WorkSchedule.id == schedule_id, WorkSchedule.is_active)
        .options(selectinload(WorkSchedule.days))
    )


def day_context(
    db: Session, employee: Employee, location: Location, day: date
) -> DayContext:
    tz = location.timezone

    leave = db.scalar(
        select(LeaveRecord).where(
            LeaveRecord.employee_id == employee.id,
            LeaveRecord.status == LeaveStatus.APPROVED,
            LeaveRecord.start_date <= day,
            LeaveRecord.end_date >= day,
        )
    )
    if leave is not None:
        return DayContext(day, tz, DayType.ON_LEAVE, description=leave.leave_type.value)

    holiday = db.scalar(
        select(Holiday).where(
            Holiday.organization_id == employee.organization_id,
            Holiday.holiday_date == day,
            (Holiday.location_id == location.id) | Holiday.location_id.is_(None),
        )
    )
    if holiday is not None:
        return DayContext(day, tz, DayType.HOLIDAY, description=holiday.name)

    schedule = resolve_schedule(db, employee, location)
    if schedule is None:
        # No working hours configured: treat as a working day without late/early rules.
        return DayContext(day, tz, DayType.WORKING_DAY)
    today = next((d for d in schedule.days if d.weekday == day.weekday()), None)
    if today is None:
        return DayContext(day, tz, DayType.NON_WORKING_DAY)
    return DayContext(
        day, tz, DayType.WORKING_DAY,
        scheduled_start=today.start_time,
        scheduled_end=today.end_time,
        grace_minutes=schedule.grace_minutes,
        early_departure_minutes=schedule.early_departure_minutes,
    )

