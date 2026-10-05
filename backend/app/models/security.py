"""Security events and the audit log (both append-only, enforced in the database), security
alerts raised by the monitoring rules, and audit-chain verification checkpoints."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, Timestamps, UUIDPk, str_enum
from app.models.enums import AlertStatus, Severity


class SecurityEvent(UUIDPk, CreatedAt, Base):
    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_created_at", "created_at"),
        Index("ix_security_events_employee_time", "employee_id", "created_at"),
        Index("ix_security_events_type_time", "event_type", "created_at"),
    )

    # NULL when the event can't be tied to a company, e.g. a login attempt for an unknown name.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    # Open list on purpose (MOCK_LOCATION, INTEGRITY_FAIL, REPLAY, IMPOSSIBLE_TRAVEL,
    # LOGIN_FAILED, REFRESH_TOKEN_REUSE, QR_INVALID, DEVICE_SHARED, ...).
    event_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "severity"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id"))
    attendance_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attendance_events.id")
    )
    device_registration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("device_registrations.id")
    )
    ip_address: Mapped[str | None] = mapped_column(INET)
    details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class AuditLog(UUIDPk, CreatedAt, Base):
    """Who changed what. seq/prev_hash/row_hash are filled by a database trigger that chains
    each row to the previous one, so any later tampering is detectable."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_object", "object_type", "object_id"),
        Index("ix_audit_logs_actor_time", "actor_user_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # NULL = system
    actor_role: Mapped[str | None] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64))  # e.g. LOCATION_RADIUS_CHANGED
    object_type: Mapped[str | None] = mapped_column(String(64))
    object_id: Mapped[str | None] = mapped_column(String(64))
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    request_id: Mapped[str | None] = mapped_column(String(64))
    seq: Mapped[int] = mapped_column(BigInteger, unique=True)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    row_hash: Mapped[str] = mapped_column(String(64))


class SecurityAlert(UUIDPk, Timestamps, Base):
    """Something that needs a person's attention, found by a monitoring rule (e.g. an account
    locked by repeated wrong passwords). One alert per rule + subject while it is not resolved."""

    __tablename__ = "security_alerts"
    __table_args__ = (
        Index("ix_security_alerts_org_status", "organization_id", "status", "last_seen_at"),
        Index("uq_security_alerts_active", "organization_id", "rule", "subject_key", unique=True,
              postgresql_where=text("status <> 'RESOLVED'")),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    rule: Mapped[str] = mapped_column(String(64))  # e.g. ACCOUNT_LOCKED
    subject_key: Mapped[str] = mapped_column(String(200))  # who/what it is about, e.g. a user id
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "severity"))
    title: Mapped[str] = mapped_column(String(300))
    details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id"))
    count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")  # events in the rule's window
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[AlertStatus] = mapped_column(
        str_enum(AlertStatus, "status"), default=AlertStatus.OPEN, server_default=AlertStatus.OPEN.value
    )
    handled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)


class AuditCheckpoint(UUIDPk, CreatedAt, Base):
    """Result of one audit-chain verification. The last good (seq, hash) is checked again next
    time, so deleting the newest rows is detected too."""

    __tablename__ = "audit_checkpoints"

    ok: Mapped[bool] = mapped_column(Boolean)
    last_seq: Mapped[int | None] = mapped_column(BigInteger)
    last_hash: Mapped[str | None] = mapped_column(String(64))
    rows_checked: Mapped[int] = mapped_column(BigInteger)
    problem: Mapped[str | None] = mapped_column(Text)
    problem_seq: Mapped[int | None] = mapped_column(BigInteger)
