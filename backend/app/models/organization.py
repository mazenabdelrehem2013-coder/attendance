"""Organization structure: organizations, branches, locations, departments, schedules, holidays."""

import uuid
from datetime import date, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk


class Organization(UUIDPk, Timestamps, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    default_timezone: Mapped[str] = mapped_column(String(64), default="Africa/Lagos")
    # Non-secret settings, e.g. company name/logo on reports, email "from" name.
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Branch(UUIDPk, Timestamps, Base):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class WorkSchedule(UUIDPk, Timestamps, Base):
    """Working hours. Times are interpreted in the timezone of the location."""

    __tablename__ = "work_schedules"
    __table_args__ = (
        UniqueConstraint("organization_id", "name"),
        CheckConstraint("grace_minutes BETWEEN 0 AND 240", name="grace_minutes_range"),
        CheckConstraint(
            "early_departure_minutes BETWEEN 0 AND 240", name="early_departure_minutes_range"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    grace_minutes: Mapped[int] = mapped_column(Integer, default=15, server_default="15")
    early_departure_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    days: Mapped[list["WorkScheduleDay"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", order_by="WorkScheduleDay.weekday"
    )


class WorkScheduleDay(UUIDPk, Timestamps, Base):
    """One row per working weekday. A weekday with no row is a non-working day."""

    __tablename__ = "work_schedule_days"
    __table_args__ = (
        UniqueConstraint("work_schedule_id", "weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),  # 0 = Monday
        CheckConstraint("end_time > start_time", name="end_after_start"),
    )

    work_schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_schedules.id", ondelete="CASCADE")
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    schedule: Mapped[WorkSchedule] = relationship(back_populates="days")


class Location(UUIDPk, Timestamps, Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        CheckConstraint("radius_m BETWEEN 10 AND 5000", name="radius_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    radius_m: Mapped[int] = mapped_column(Integer, default=200, server_default="200")
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Lagos")
    work_schedule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_schedules.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Department(UUIDPk, Timestamps, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Holiday(UUIDPk, Timestamps, Base):
    """Public/company holiday. location_id NULL = applies to every location."""

    __tablename__ = "holidays"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "location_id", "holiday_date", postgresql_nulls_not_distinct=True
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    holiday_date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(200))
