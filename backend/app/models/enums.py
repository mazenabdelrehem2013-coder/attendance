"""All fixed value lists used by the database (stored as text with CHECK constraints)."""

from enum import StrEnum


class Role(StrEnum):
    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"
    HR = "HR"
    ADMIN = "ADMIN"


class EmploymentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"


class LeaveType(StrEnum):
    ANNUAL = "ANNUAL"
    SICK = "SICK"
    MATERNITY = "MATERNITY"
    PATERNITY = "PATERNITY"
    OFFICIAL_DUTY = "OFFICIAL_DUTY"
    UNPAID = "UNPAID"
    OTHER = "OTHER"


class LeaveStatus(StrEnum):
    APPROVED = "APPROVED"
    CANCELLED = "CANCELLED"


class ClientType(StrEnum):
    MOBILE = "MOBILE"
    WEB = "WEB"


class DeviceStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    DEACTIVATED = "DEACTIVATED"
    REREGISTRATION_REQUIRED = "REREGISTRATION_REQUIRED"


class AttendanceAction(StrEnum):
    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"


class VerificationMode(StrEnum):
    GPS_ONLY = "GPS_ONLY"
    GPS_QR = "GPS_QR"
    GPS_QR_PLUS = "GPS_QR_PLUS"


class PolicyAction(StrEnum):
    ALLOW = "ALLOW"
    FLAG = "FLAG"
    REJECT = "REJECT"


class EventResult(StrEnum):
    ACCEPTED = "ACCEPTED"
    FLAGGED = "FLAGGED"
    REJECTED = "REJECTED"


class SignalResult(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SignalType(StrEnum):
    QR = "QR"
    NFC = "NFC"
    BLE_BEACON = "BLE_BEACON"
    SELFIE = "SELFIE"


class ArrivalStatus(StrEnum):
    PRESENT = "PRESENT"
    LATE = "LATE"


class DepartureStatus(StrEnum):
    CHECKED_OUT = "CHECKED_OUT"
    EARLY_DEPARTURE = "EARLY_DEPARTURE"
    MISSING_CHECKOUT = "MISSING_CHECKOUT"


class DayStatus(StrEnum):
    PRESENT = "PRESENT"
    LATE = "LATE"
    ABSENT = "ABSENT"
    PENDING_REVIEW = "PENDING_REVIEW"
    ON_LEAVE = "ON_LEAVE"
    HOLIDAY = "HOLIDAY"
    NON_WORKING_DAY = "NON_WORKING_DAY"


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    SUSPICIOUS = "SUSPICIOUS"
    PENDING_REVIEW = "PENDING_REVIEW"
    REJECTED = "REJECTED"


class SessionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    MISSING_CHECKOUT = "MISSING_CHECKOUT"
    REJECTED = "REJECTED"  # HR rejected a flagged check-in/out of this session


class ReviewDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReportType(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    EMPLOYEE = "EMPLOYEE"
    LOCATION = "LOCATION"
    DEPARTMENT = "DEPARTMENT"
    MANAGER = "MANAGER"
    LATE = "LATE"
    ABSENCE = "ABSENCE"
    SUSPICIOUS = "SUSPICIOUS"


class ReportFormat(StrEnum):
    EXCEL = "EXCEL"
    PDF = "PDF"


class ReportRunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class NotificationEvent(StrEnum):
    LATE_EMPLOYEE = "LATE_EMPLOYEE"
    SUSPICIOUS_CHECK_IN = "SUSPICIOUS_CHECK_IN"
    REJECTED_CHECK_IN = "REJECTED_CHECK_IN"
    MISSING_CHECKOUT = "MISSING_CHECKOUT"
    HIGH_ABSENCE = "HIGH_ABSENCE"
    REPORT_GENERATED = "REPORT_GENERATED"
    DEVICE_APPROVAL_REQUESTED = "DEVICE_APPROVAL_REQUESTED"
    SECURITY_ALERT = "SECURITY_ALERT"


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"  # someone is looking at it
    RESOLVED = "RESOLVED"


class NotificationChannel(StrEnum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"


class RetentionCategory(StrEnum):
    ATTENDANCE = "ATTENDANCE"
    RAW_LOCATION = "RAW_LOCATION"
    SECURITY_EVENTS = "SECURITY_EVENTS"
    AUDIT_LOGS = "AUDIT_LOGS"
    REPORT_FILES = "REPORT_FILES"
    NOTIFICATIONS = "NOTIFICATIONS"
