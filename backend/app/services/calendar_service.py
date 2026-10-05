"""Holidays and leave (recorded by HR). Days covered are HOLIDAY / ON_LEAVE, never ABSENT."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Employee, Holiday, LeaveRecord, Location, User
from app.models.enums import LeaveStatus
from app.schemas.calendar import HolidayCreate, LeaveCreate, LeaveOut
from app.services.audit import Actor, audit, snapshot
from app.services.org_service import get_in_org
from app.services.scope import employee_scope, get_visible_employee

# --- Holidays -------------------------------------------------------------------------------


def list_holidays(db: Session, org_id: uuid.UUID, year: int | None) -> list[Holiday]:
    query = select(Holiday).where(Holiday.organization_id == org_id)
    if year:
        query = query.where(Holiday.holiday_date.between(date(year, 1, 1), date(year, 12, 31)))
    return list(db.scalars(query.order_by(Holiday.holiday_date)))


def create_holiday(db: Session, actor: Actor, data: HolidayCreate) -> Holiday:
    org = actor.user.organization_id
    if data.location_id:
        get_in_org(db, Location, data.location_id, org, "Location")
    holiday = Holiday(organization_id=org, **data.model_dump())
    db.add(holiday)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "DUPLICATE", "There is already a holiday on this date.") from None
    audit(db, actor, "HOLIDAY_CREATED", "holiday", holiday.id,
          new_value=snapshot(holiday, ["holiday_date", "name", "location_id"]))
    db.commit()
    return holiday


def delete_holiday(db: Session, actor: Actor, holiday_id: uuid.UUID) -> None:
    holiday = get_in_org(db, Holiday, holiday_id, actor.user.organization_id, "Holiday")
    audit(db, actor, "HOLIDAY_DELETED", "holiday", holiday.id,
          old_value=snapshot(holiday, ["holiday_date", "name", "location_id"]))
    db.delete(holiday)
    db.commit()


# --- Leave ----------------------------------------------------------------------------------


def _leave_out(leave: LeaveRecord, employee: Employee) -> LeaveOut:
    return LeaveOut(
        id=leave.id, employee_id=employee.id, employee_name=employee.full_name,
        leave_type=leave.leave_type, start_date=leave.start_date, end_date=leave.end_date,
        status=leave.status, note=leave.note,
    )


def list_leave(
    db: Session, user: User, employee_id: uuid.UUID | None, date_from: date | None, date_to: date | None
) -> list[LeaveOut]:
    query = (
        select(LeaveRecord, Employee)
        .join(Employee, Employee.id == LeaveRecord.employee_id)
        .where(employee_scope(db, user))
    )
    if employee_id:
        query = query.where(LeaveRecord.employee_id == employee_id)
    if date_from:
        query = query.where(LeaveRecord.end_date >= date_from)
    if date_to:
        query = query.where(LeaveRecord.start_date <= date_to)
    rows = db.execute(query.order_by(LeaveRecord.start_date.desc()).limit(500)).all()
    return [_leave_out(l, e) for l, e in rows]


def create_leave(db: Session, actor: Actor, data: LeaveCreate) -> LeaveOut:
    employee = get_visible_employee(db, actor.user, data.employee_id)
    overlap = db.scalar(
        select(LeaveRecord.id).where(
            LeaveRecord.employee_id == employee.id,
            LeaveRecord.status == LeaveStatus.APPROVED,
            LeaveRecord.start_date <= data.end_date,
            LeaveRecord.end_date >= data.start_date,
        )
    )
    if overlap:
        raise AppError(409, "LEAVE_OVERLAP", "This employee already has leave in that period.")
    leave = LeaveRecord(recorded_by=actor.user.id, **data.model_dump())
    db.add(leave)
    db.flush()
    audit(db, actor, "LEAVE_RECORDED", "leave", leave.id,
          new_value=snapshot(leave, ["employee_id", "leave_type", "start_date", "end_date"]))
    db.commit()
    return _leave_out(leave, employee)


def cancel_leave(db: Session, actor: Actor, leave_id: uuid.UUID) -> LeaveOut:
    leave = db.get(LeaveRecord, leave_id)
    employee = db.get(Employee, leave.employee_id) if leave else None
    if leave is None or employee.organization_id != actor.user.organization_id:
        raise AppError(404, "NOT_FOUND", "Leave record not found.")
    if leave.status == LeaveStatus.CANCELLED:
        raise AppError(409, "INVALID_STATE", "This leave is already cancelled.")
    leave.status = LeaveStatus.CANCELLED
    audit(db, actor, "LEAVE_CANCELLED", "leave", leave.id, {"status": "APPROVED"}, {"status": "CANCELLED"})
    db.commit()
    return _leave_out(leave, employee)
