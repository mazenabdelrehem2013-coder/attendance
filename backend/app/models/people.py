"""Users, employees, managers, authorized locations and leave."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk, str_enum
from app.models.enums import EmploymentStatus, LeaveStatus, LeaveType, Role
from app.models.organization import Department, Location


class User(UUIDPk, Timestamps, Base):
    """A login account. Employees, managers, HR and admins all have one."""

    __tablename__ = "users"
    __table_args__ = (
        # Emails are unique regardless of upper/lower case.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_positive"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Included in every access token. Increasing it (password change, forced logout)
    # immediately invalidates all of the user's existing tokens.
    token_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class Manager(UUIDPk, Timestamps, Base):
    """A user who manages employees. employee_id is set when the manager also checks in."""

    __tablename__ = "managers"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    # use_alter: employees.manager_id -> managers and managers.employee_id -> employees form a cycle.
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id", use_alter=True), unique=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    employee: Mapped["Employee | None"] = relationship(foreign_keys=[employee_id])


class Employee(UUIDPk, Timestamps, Base):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("organization_id", "employee_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    employee_code: Mapped[str] = mapped_column(String(32))
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id"), index=True
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("managers.id"), index=True)
    # Optional override; otherwise the schedule of the location is used.
    work_schedule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_schedules.id"))
    hire_date: Mapped[date | None] = mapped_column(Date)
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        str_enum(EmploymentStatus, "employment_status"),
        default=EmploymentStatus.ACTIVE,
        server_default=EmploymentStatus.ACTIVE.value,
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    department: Mapped["Department | None"] = relationship()
    manager: Mapped[Manager | None] = relationship(foreign_keys=[manager_id])
    locations: Mapped[list["EmployeeLocation"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


class EmployeeLocation(UUIDPk, Timestamps, Base):
    """Locations where an employee is allowed to check in."""

    __tablename__ = "employee_locations"
    __table_args__ = (
        UniqueConstraint("employee_id", "location_id"),
        # At most one primary location per employee.
        Index(
            "uq_employee_locations_one_primary",
            "employee_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_range"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    valid_from: Mapped[date] = mapped_column(Date, server_default=text("CURRENT_DATE"))
    valid_to: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    employee: Mapped[Employee] = relationship(back_populates="locations")
    location: Mapped["Location"] = relationship()


class LeaveRecord(UUIDPk, Timestamps, Base):
    """Leave recorded by HR. Days covered are ON_LEAVE instead of ABSENT."""

    __tablename__ = "leave_records"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="end_after_start"),
        Index("ix_leave_records_employee_dates", "employee_id", "start_date", "end_date"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    leave_type: Mapped[LeaveType] = mapped_column(str_enum(LeaveType, "leave_type"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[LeaveStatus] = mapped_column(
        str_enum(LeaveStatus, "leave_status"),
        default=LeaveStatus.APPROVED,
        server_default=LeaveStatus.APPROVED.value,
    )
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
