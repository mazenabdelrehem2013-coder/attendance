"""Helpers to write audit-log rows and security events.

They only add rows to the session; the caller's transaction commits them together with the
change they describe, so a change can never be saved without its log entry.
"""

import ipaddress
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, SecurityEvent, User
from app.models.enums import Severity


@dataclass
class RequestInfo:
    ip_address: str | None
    user_agent: str | None
    request_id: str | None


@dataclass
class Actor:
    """Who is making a change, and from where (for the audit log)."""

    user: User
    info: RequestInfo


def clean_ip(value: str | None) -> str | None:
    """Return a valid IP address string or None (the column type only accepts real IPs)."""
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def write_audit(
    db: Session,
    *,
    action: str,
    organization_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
    object_type: str | None = None,
    object_id: Any = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id is not None else None,
            old_value=old_value,
            new_value=new_value,
            ip_address=clean_ip(ip_address),
            user_agent=(user_agent or "")[:500] or None,
            request_id=request_id,
        )
    )


def write_security_event(
    db: Session,
    *,
    event_type: str,
    severity: Severity,
    organization_id: uuid.UUID | None,
    user_id: uuid.UUID | None = None,
    employee_id: uuid.UUID | None = None,
    attendance_event_id: uuid.UUID | None = None,
    device_registration_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        SecurityEvent(
            organization_id=organization_id,
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            employee_id=employee_id,
            attendance_event_id=attendance_event_id,
            device_registration_id=device_registration_id,
            ip_address=clean_ip(ip_address),
            details=details or {},
        )
    )


def snapshot(obj: Any, fields: list[str]) -> dict:
    """JSON-safe copy of selected attributes, for audit old/new values."""
    out = {}
    for name in fields:
        value = getattr(obj, name)
        if value is None or isinstance(value, (bool, int, str)):
            out[name] = value
        elif hasattr(value, "value"):  # enums
            out[name] = value.value
        else:  # UUID, Decimal, date, time
            out[name] = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return out


def changed_fields(before: dict, after: dict) -> tuple[dict, dict]:
    """Only the fields that actually changed, as (old, new)."""
    keys = [k for k in after if before.get(k) != after.get(k)]
    return {k: before.get(k) for k in keys}, {k: after[k] for k in keys}


def audit(
    db: Session,
    actor: Actor,
    action: str,
    object_type: str,
    object_id: Any,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    write_audit(
        db,
        action=action,
        organization_id=actor.user.organization_id,
        actor_user_id=actor.user.id,
        actor_role=actor.user.role.value,
        object_type=object_type,
        object_id=object_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=actor.info.ip_address,
        user_agent=actor.info.user_agent,
        request_id=actor.info.request_id,
    )
