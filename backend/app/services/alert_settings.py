"""The logged-in user's own alerts (bell icon) and the alert settings (HR)."""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.models import Notification, NotificationSetting, User
from app.models.enums import NotificationChannel, NotificationEvent
from app.schemas.schedules import AlertSetting, AlertSettingUpdate, NotificationList, NotificationOut
from app.services.audit import Actor, audit
from app.services.notifications import EVENTS, rules

# --- My alerts ------------------------------------------------------------------------------


def my_notifications(db: Session, user: User, limit: int, unread_only: bool) -> NotificationList:
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    items = db.scalars(query.order_by(Notification.created_at.desc()).limit(limit))
    unread = db.scalar(select(func.count()).select_from(Notification)
                       .where(Notification.user_id == user.id, Notification.read_at.is_(None)))
    return NotificationList(
        items=[NotificationOut(id=n.id, event=n.event_type.value, title=n.title, body=n.body,
                               link=(n.data or {}).get("link"), created_at=n.created_at,
                               read=n.read_at is not None) for n in items],
        unread=unread,
    )


def mark_read(db: Session, user: User, notification_id: uuid.UUID | None) -> None:
    query = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if notification_id is not None:
        query = query.where(Notification.id == notification_id)
    db.execute(query.values(read_at=clock.now()))
    db.commit()


# --- Alert settings -------------------------------------------------------------------------


def alert_settings(db: Session, user: User) -> list[AlertSetting]:
    return [
        AlertSetting(event=event.value, label=EVENTS[event].label, description=EVENTS[event].description,
                     enabled=rule.enabled, roles=rule.roles, thresholds=rule.thresholds)
        for event, rule in rules(db, user.organization_id).items()
    ]


def update_alert(db: Session, actor: Actor, event_name: str, data: AlertSettingUpdate) -> AlertSetting:
    try:
        event = NotificationEvent(event_name)
    except ValueError:
        event = None
    if event not in EVENTS:
        raise AppError(404, "NOT_FOUND", "Unknown alert.")
    org_id = actor.user.organization_id
    before = rules(db, org_id)[event]
    row = db.scalar(select(NotificationSetting).where(
        NotificationSetting.organization_id == org_id, NotificationSetting.event_type == event,
        NotificationSetting.channel == NotificationChannel.IN_APP))
    if row is None:
        row = NotificationSetting(organization_id=org_id, event_type=event, channel=NotificationChannel.IN_APP)
        db.add(row)
    row.is_enabled = data.enabled
    row.recipient_roles = sorted(set(data.roles))
    row.thresholds = {**EVENTS[event].thresholds, **data.thresholds} if EVENTS[event].thresholds else {}
    audit(db, actor, "ALERT_SETTINGS_UPDATED", "notification_setting", event.value,
          old_value=before.__dict__, new_value=data.model_dump())
    db.commit()
    return next(a for a in alert_settings(db, actor.user) if a.event == event.value)
