"""Report schedules/runs, notifications and data-retention settings."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, Timestamps, UUIDPk, str_enum
from app.models.enums import (
    NotificationChannel,
    NotificationEvent,
    ReportFormat,
    ReportRunStatus,
    ReportType,
    RetentionCategory,
)


class ReportSetting(UUIDPk, Timestamps, Base):
    __tablename__ = "report_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    report_type: Mapped[ReportType] = mapped_column(str_enum(ReportType, "report_type"))
    cron_expression: Mapped[str] = mapped_column(String(100))  # e.g. "30 9 * * 1-6"
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Lagos")
    formats: Mapped[list[str]] = mapped_column(ARRAY(String(16)))
    # Roles that receive it, e.g. ["HR"]; "MANAGER" means each manager gets only their team.
    recipient_roles: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    extra_recipients: Mapped[list[str]] = mapped_column(ARRAY(String(320)), default=list)
    filters: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    include_location_details: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # The scheduled time most recently handled, so each scheduled time is sent once only.
    last_scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportRun(UUIDPk, CreatedAt, Base):
    __tablename__ = "report_runs"
    __table_args__ = (Index("ix_report_runs_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    report_setting_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("report_settings.id"))
    report_type: Mapped[ReportType] = mapped_column(str_enum(ReportType, "report_type"))
    format: Mapped[ReportFormat] = mapped_column(str_enum(ReportFormat, "format"))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # NULL = scheduler
    # Scheduled team report: the manager it belongs to. NULL = company-wide (HR / Admin).
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[ReportRunStatus] = mapped_column(
        str_enum(ReportRunStatus, "status"),
        default=ReportRunStatus.QUEUED,
        server_default=ReportRunStatus.QUEUED.value,
    )
    storage_path: Mapped[str | None] = mapped_column(String(500))  # Cloud Storage object
    row_count: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationSetting(UUIDPk, Timestamps, Base):
    __tablename__ = "notification_settings"
    __table_args__ = (UniqueConstraint("organization_id", "event_type", "channel"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    event_type: Mapped[NotificationEvent] = mapped_column(
        str_enum(NotificationEvent, "event_type")
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        str_enum(NotificationChannel, "channel")
    )
    recipient_roles: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    thresholds: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Notification(UUIDPk, CreatedAt, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "read_at"),
        Index("uq_notifications_user_dedupe", "user_id", "dedupe_key", unique=True,
              postgresql_where=text("dedupe_key IS NOT NULL")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[NotificationEvent] = mapped_column(
        str_enum(NotificationEvent, "event_type")
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Same alert for the same thing is created once only (e.g. "late:<employee>:<date>").
    dedupe_key: Mapped[str | None] = mapped_column(String(200))


class ReportFile(UUIDPk, CreatedAt, Base):
    """A generated report file (scheduled reports), kept for download for a limited time."""

    __tablename__ = "report_files"

    report_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_runs.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(150))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary)


class RetentionSetting(UUIDPk, Timestamps, Base):
    __tablename__ = "retention_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", "data_category"),
        CheckConstraint("retain_days >= 30", name="retain_days_min"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    data_category: Mapped[RetentionCategory] = mapped_column(
        str_enum(RetentionCategory, "data_category")
    )
    retain_days: Mapped[int] = mapped_column(Integer)
