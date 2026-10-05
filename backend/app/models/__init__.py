"""Importing this package registers every table on Base.metadata (needed by Alembic)."""

from app.models.attendance import (
    Attendance,
    AttendanceAdjustment,
    AttendanceChallenge,
    AttendanceEvent,
    AttendanceEventReview,
    AttendancePolicy,
    AttendanceSession,
    AttendanceVerification,
    QrSession,
    VerificationSignal,
)
from app.models.auth import DeviceRegistration, RefreshToken
from app.models.organization import (
    Branch,
    Department,
    Holiday,
    Location,
    Organization,
    WorkSchedule,
    WorkScheduleDay,
)
from app.models.people import Employee, EmployeeLocation, LeaveRecord, Manager, User
from app.models.reporting import (
    Notification,
    NotificationSetting,
    ReportFile,
    ReportRun,
    ReportSetting,
    RetentionSetting,
)
from app.models.security import AuditCheckpoint, AuditLog, SecurityAlert, SecurityEvent

__all__ = [
    "Attendance",
    "AttendanceAdjustment",
    "AttendanceChallenge",
    "AttendanceEvent",
    "AttendanceEventReview",
    "AttendancePolicy",
    "AttendanceSession",
    "AttendanceVerification",
    "AuditCheckpoint",
    "AuditLog",
    "Branch",
    "Department",
    "DeviceRegistration",
    "Employee",
    "EmployeeLocation",
    "Holiday",
    "LeaveRecord",
    "Location",
    "Manager",
    "Notification",
    "NotificationSetting",
    "Organization",
    "QrSession",
    "RefreshToken",
    "ReportFile",
    "ReportRun",
    "ReportSetting",
    "RetentionSetting",
    "SecurityAlert",
    "SecurityEvent",
    "User",
    "VerificationSignal",
    "WorkSchedule",
    "WorkScheduleDay",
]
