"""Employee attendance: challenge, check-in, check-out, today, history; phone registration;
holidays and leave."""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import actor_with_roles, get_current_user, request_info, require_roles
from app.core import clock
from app.db.session import get_db
from app.models import User
from app.models.enums import AttendanceAction, DeviceStatus, Role
from app.schemas.attendance import (
    AttendanceDay,
    AttendanceSubmission,
    ChallengeRequest,
    ChallengeResponse,
    CheckResult,
    TodayResponse,
)
from app.schemas.calendar import HolidayCreate, HolidayOut, LeaveCreate, LeaveOut
from app.schemas.common import Page, PageParams
from app.schemas.devices import DeviceDecision, DeviceOut, DeviceRegister
from app.services import calendar_service, device_service
from app.services.attendance import service as attendance
from app.services.audit import Actor, RequestInfo

router = APIRouter()
hr_actor = actor_with_roles(Role.HR)


# --- Attendance -----------------------------------------------------------------------------


@router.post("/attendance/challenge", response_model=ChallengeResponse, tags=["attendance"],
             summary="Step 1: get a one-time code right before capturing GPS")
def challenge(
    body: ChallengeRequest,
    user: User = Depends(get_current_user),
    info: RequestInfo = Depends(request_info),
    db: Session = Depends(get_db),
):
    return attendance.create_challenge(db, user, body, info)


@router.post("/attendance/check-in", response_model=CheckResult, tags=["attendance"],
             summary="Step 2: send the evidence. Result: ACCEPTED, FLAGGED or REJECTED")
def check_in(
    body: AttendanceSubmission,
    user: User = Depends(get_current_user),
    info: RequestInfo = Depends(request_info),
    db: Session = Depends(get_db),
):
    return attendance.submit(db, user, AttendanceAction.CHECK_IN, body, info)


@router.post("/attendance/check-out", response_model=CheckResult, tags=["attendance"])
def check_out(
    body: AttendanceSubmission,
    user: User = Depends(get_current_user),
    info: RequestInfo = Depends(request_info),
    db: Session = Depends(get_db),
):
    return attendance.submit(db, user, AttendanceAction.CHECK_OUT, body, info)


@router.get("/attendance/today", response_model=TodayResponse, tags=["attendance"])
def today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return attendance.today(db, user)


@router.get("/attendance/history", response_model=list[AttendanceDay], tags=["attendance"],
            summary="My attendance per day (default: last 31 days, max 93)")
def history(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    date_to = date_to or clock.now().date()
    date_from = date_from or date_to - timedelta(days=30)
    return attendance.history(db, user, date_from, date_to)


# --- Devices --------------------------------------------------------------------------------


@router.post("/devices/register", response_model=DeviceOut, tags=["devices"],
             summary="Register this phone (needs HR approval before use)")
def register_device(
    body: DeviceRegister,
    user: User = Depends(get_current_user),
    info: RequestInfo = Depends(request_info),
    db: Session = Depends(get_db),
):
    employee = attendance.employee_for(db, user)
    return device_service.register(db, Actor(user, info), employee, body)


@router.get("/devices/me", response_model=list[DeviceOut], tags=["devices"])
def my_devices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return device_service.my_devices(db, attendance.employee_for(db, user))


@router.get("/devices", response_model=Page[DeviceOut], tags=["devices"])
def list_devices(
    status_filter: DeviceStatus | None = Query(None, alias="status"),
    page: PageParams = Depends(),
    user: User = Depends(require_roles(Role.HR)),
    db: Session = Depends(get_db),
):
    return device_service.list_devices(db, user.organization_id, status_filter, page)


@router.post("/devices/{device_id}/approve", response_model=DeviceOut, tags=["devices"])
def approve_device(
    device_id: uuid.UUID, body: DeviceDecision | None = None,
    actor: Actor = Depends(hr_actor), db: Session = Depends(get_db),
):
    return device_service.approve(db, actor, device_id, body.note if body else None)


@router.post("/devices/{device_id}/reject", response_model=DeviceOut, tags=["devices"])
def reject_device(
    device_id: uuid.UUID, body: DeviceDecision | None = None,
    actor: Actor = Depends(hr_actor), db: Session = Depends(get_db),
):
    return device_service.reject(db, actor, device_id, body.note if body else None)


@router.post("/devices/{device_id}/deactivate", response_model=DeviceOut, tags=["devices"])
def deactivate_device(
    device_id: uuid.UUID, body: DeviceDecision | None = None,
    actor: Actor = Depends(hr_actor), db: Session = Depends(get_db),
):
    return device_service.deactivate(db, actor, device_id, body.note if body else None)


# --- Holidays & leave -----------------------------------------------------------------------


@router.get("/holidays", response_model=list[HolidayOut], tags=["calendar"])
def list_holidays(
    year: int | None = Query(None, ge=2000, le=2100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return calendar_service.list_holidays(db, user.organization_id, year)


@router.post("/holidays", response_model=HolidayOut, status_code=status.HTTP_201_CREATED, tags=["calendar"])
def create_holiday(body: HolidayCreate, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    return calendar_service.create_holiday(db, actor, body)


@router.delete("/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["calendar"])
def delete_holiday(holiday_id: uuid.UUID, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    calendar_service.delete_holiday(db, actor, holiday_id)


@router.get("/leave", response_model=list[LeaveOut], tags=["calendar"],
            summary="Leave records (managers: own team; employees: their own)")
def list_leave(
    employee_id: uuid.UUID | None = None,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return calendar_service.list_leave(db, user, employee_id, date_from, date_to)


@router.post("/leave", response_model=LeaveOut, status_code=status.HTTP_201_CREATED, tags=["calendar"])
def create_leave(body: LeaveCreate, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    return calendar_service.create_leave(db, actor, body)


@router.post("/leave/{leave_id}/cancel", response_model=LeaveOut, tags=["calendar"])
def cancel_leave(leave_id: uuid.UUID, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    return calendar_service.cancel_leave(db, actor, leave_id)
