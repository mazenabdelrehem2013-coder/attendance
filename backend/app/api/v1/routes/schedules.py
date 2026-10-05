"""Alerts (everyone: their own bell), and for HR / Admin: scheduled reports and alert settings.
The files made by scheduled reports are downloaded via /reports/ready."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import actor_with_roles, get_current_user, require_roles
from app.db.session import get_db
from app.models import User
from app.models.enums import Role
from app.schemas.schedules import (
    AlertSetting,
    AlertSettingUpdate,
    NotificationList,
    RunResult,
    ScheduleIn,
    ScheduleOut,
)
from app.services import alert_settings, report_schedules
from app.services.audit import Actor

router = APIRouter(tags=["scheduled reports & alerts"])
hr = require_roles(Role.HR)
hr_actor = actor_with_roles(Role.HR)


# --- My alerts (bell icon) ------------------------------------------------------------------


@router.get("/notifications", response_model=NotificationList, summary="My latest alerts")
def my_notifications(
    unread_only: bool = False,
    limit: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return alert_settings.my_notifications(db, user, limit, unread_only)


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT,
             summary="Mark one alert as read")
def read_one(notification_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    alert_settings.mark_read(db, user, notification_id)


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT, summary="Mark all my alerts as read")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    alert_settings.mark_read(db, user, None)


# --- Scheduled reports ----------------------------------------------------------------------


@router.get("/hr/report-schedules", response_model=list[ScheduleOut], summary="Scheduled reports")
def list_schedules(user: User = Depends(hr), db: Session = Depends(get_db)):
    return report_schedules.list_schedules(db, user)


@router.post("/hr/report-schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED,
             summary="Create a scheduled report")
def create_schedule(data: ScheduleIn, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    return report_schedules.create(db, actor, data)


@router.put("/hr/report-schedules/{schedule_id}", response_model=ScheduleOut, summary="Change a scheduled report")
def update_schedule(schedule_id: uuid.UUID, data: ScheduleIn, actor: Actor = Depends(hr_actor),
                    db: Session = Depends(get_db)):
    return report_schedules.update(db, actor, schedule_id, data)


@router.delete("/hr/report-schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a scheduled report (files already created stay until the keep period ends)")
def delete_schedule(schedule_id: uuid.UUID, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    report_schedules.delete(db, actor, schedule_id)


@router.post("/hr/report-schedules/{schedule_id}/run-now", response_model=RunResult,
             summary="Create this report now, without waiting for its time")
def run_now(schedule_id: uuid.UUID, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    return report_schedules.run_now(db, actor, schedule_id)


# --- Alert settings -------------------------------------------------------------------------


@router.get("/hr/alert-settings", response_model=list[AlertSetting], summary="Who gets which alert")
def get_alert_settings(user: User = Depends(hr), db: Session = Depends(get_db)):
    return alert_settings.alert_settings(db, user)


@router.put("/hr/alert-settings/{event}", response_model=AlertSetting, summary="Change one alert")
def update_alert(event: str, data: AlertSettingUpdate, actor: Actor = Depends(hr_actor),
                 db: Session = Depends(get_db)):
    return alert_settings.update_alert(db, actor, event, data)
