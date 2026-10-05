"""Alerts for managers and HR, shown in the dashboard (bell icon). No emails are sent.

Who gets which alert is configured per organization (HR -> Scheduled reports & alerts).
Without configuration the defaults below apply. Creating an alert never breaks the action
that caused it: any problem is logged and the check-in / device request still succeeds.
"""

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Employee, Manager, Notification, NotificationSetting, User
from app.models.enums import NotificationChannel, NotificationEvent, Role

log = logging.getLogger("app.notifications")

IN_APP = NotificationChannel.IN_APP
RECIPIENT_ROLES = ("MANAGER", "HR", "ADMIN")  # MANAGER = the employee's own manager


@dataclass
class EventInfo:
    label: str
    description: str
    default: tuple[bool, list[str]]  # (enabled, roles)
    thresholds: dict = field(default_factory=dict)


EVENTS: dict[NotificationEvent, EventInfo] = {
    NotificationEvent.SUSPICIOUS_CHECK_IN: EventInfo(
        "Check-in needs review", "A check-in or check-out was flagged and waits for HR review.", (True, ["HR"])),
    NotificationEvent.REJECTED_CHECK_IN: EventInfo(
        "Check-in rejected", "A check-in was refused by the security checks (at most once per employee per day).",
        (True, ["HR"])),
    NotificationEvent.DEVICE_APPROVAL_REQUESTED: EventInfo(
        "New phone waiting for approval", "An employee registered a new phone that HR must approve.", (True, ["HR"])),
    NotificationEvent.LATE_EMPLOYEE: EventInfo(
        "Late arrival", "An employee checked in late (once per employee per day).", (True, ["MANAGER"])),
    NotificationEvent.MISSING_CHECKOUT: EventInfo(
        "Missing check-out", "An employee did not check out (found by the end-of-day job).", (True, ["MANAGER"])),
    NotificationEvent.HIGH_ABSENCE: EventInfo(
        "Frequent absence", "An employee reached the absence limit within the period.",
        (True, ["HR", "MANAGER"]), {"absences": 3, "days": 30}),
    NotificationEvent.SECURITY_ALERT: EventInfo(
        "Security alert", "A monitoring rule found something to look at (e.g. an account locked by repeated "
        "wrong passwords). HR and Admin only.", (True, ["HR", "ADMIN"])),
    NotificationEvent.REPORT_GENERATED: EventInfo(
        "Scheduled report ready", "A scheduled report was created and can be downloaded.", (True, ["HR", "MANAGER"])),
}


@dataclass
class EventRule:
    enabled: bool
    roles: list[str]
    thresholds: dict


def rules(db: Session, organization_id: uuid.UUID) -> dict[NotificationEvent, EventRule]:
    """Effective settings for every event: stored settings, else the defaults."""
    stored = {s.event_type: s for s in db.scalars(select(NotificationSetting).where(
        NotificationSetting.organization_id == organization_id, NotificationSetting.channel == IN_APP))}
    out = {}
    for event, info in EVENTS.items():
        s = stored.get(event)
        thresholds = {**info.thresholds, **((s.thresholds or {}) if s else {})}
        if s:
            out[event] = EventRule(s.is_enabled, list(s.recipient_roles), thresholds)
        else:
            out[event] = EventRule(info.default[0], list(info.default[1]), thresholds)
    return out


def _recipients(db: Session, organization_id: uuid.UUID, roles: list[str], employee: Employee | None) -> list[User]:
    users: dict[uuid.UUID, User] = {}
    company_roles = [Role(r) for r in roles if r in ("HR", "ADMIN")]
    if company_roles:
        for u in db.scalars(select(User).where(
            User.organization_id == organization_id, User.role.in_(company_roles), User.is_active
        )):
            users[u.id] = u
    if "MANAGER" in roles and employee is not None and employee.manager_id:
        manager = db.get(Manager, employee.manager_id)
        if manager and manager.is_active and manager.user.is_active:
            users[manager.user.id] = manager.user
    if employee is not None:
        users.pop(employee.user_id, None)  # never alert people about themselves
    return list(users.values())


def add(db: Session, user: User, event: NotificationEvent, title: str, body: str,
        link: str | None = None, dedupe_key: str | None = None, data: dict | None = None) -> bool:
    """One alert for one person (skipped if the same dedupe key was used for them before)."""
    if dedupe_key and db.scalar(select(Notification.id).where(
            Notification.user_id == user.id, Notification.dedupe_key == dedupe_key)):
        return False
    db.add(Notification(user_id=user.id, event_type=event, title=title[:200], body=body,
                        data={"link": link, **(data or {})}, dedupe_key=dedupe_key))
    return True


def notify(
    db: Session,
    *,
    organization_id: uuid.UUID,
    event: NotificationEvent,
    employee: Employee | None,
    title: str,
    lines: list[str],
    rows: list[tuple[str, str]] | None = None,
    link: str | None = None,
    dedupe_key: str | None = None,
    rule: EventRule | None = None,
) -> int:
    """Create the alerts for one event. Returns how many were created.
    Runs in a savepoint: if anything goes wrong, nothing is created and the caller carries on."""
    try:
        with db.begin_nested():
            rule = rule or rules(db, organization_id)[event]
            if not rule.enabled:
                return 0
            data = {"employee_id": str(employee.id) if employee else None}
            body = " ".join(lines + [f"{label}: {value}." for label, value in rows or []])
            created = sum(
                add(db, user, event, title, body, link, dedupe_key, data)
                for user in _recipients(db, organization_id, rule.roles, employee)
            )
            db.flush()
            return created
    except SQLAlchemyError:
        log.exception("Could not create notification", extra={"event": event.value})
        return 0
