"""Refresh tokens and registered phones."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, Timestamps, UUIDPk, str_enum
from app.models.enums import ClientType, DeviceStatus


class DeviceRegistration(UUIDPk, Timestamps, Base):
    """A phone registered by an employee. New phones need HR approval before use."""

    __tablename__ = "device_registrations"
    __table_args__ = (
        # One physical phone can be bound to only one employee at a time.
        Index(
            "uq_device_registrations_fingerprint_in_use",
            "device_fingerprint",
            unique=True,
            postgresql_where=text("status IN ('PENDING_APPROVAL', 'ACTIVE')"),
        ),
        # One active phone per employee.
        Index(
            "uq_device_registrations_one_active_per_employee",
            "employee_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_device_registrations_status", "status"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), index=True)
    # SHA-256 of Android's ANDROID_ID (stable across reinstalls; resets on factory reset).
    device_fingerprint: Mapped[str] = mapped_column(String(64))
    install_id: Mapped[str] = mapped_column(String(64))
    platform: Mapped[str] = mapped_column(String(16), default="android", server_default="android")
    device_model: Mapped[str | None] = mapped_column(String(100))
    os_version: Mapped[str | None] = mapped_column(String(50))
    app_version: Mapped[str | None] = mapped_column(String(50))
    # Public half of the key pair created in the Android Keystore; used to verify signatures.
    public_key: Mapped[str | None] = mapped_column(Text)
    key_algorithm: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[DeviceStatus] = mapped_column(
        str_enum(DeviceStatus, "device_status"),
        default=DeviceStatus.PENDING_APPROVAL,
        server_default=DeviceStatus.PENDING_APPROVAL.value,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    last_integrity_verdict: Mapped[dict | None] = mapped_column(JSONB)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(UUIDPk, CreatedAt, Base):
    """Only a hash of the token is stored. Tokens rotate; reuse of an old one revokes the family."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_expires_at", "expires_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    client_type: Mapped[ClientType] = mapped_column(str_enum(ClientType, "client_type"))
    device_registration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("device_registrations.id")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(String(50))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("refresh_tokens.id"))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(500))
