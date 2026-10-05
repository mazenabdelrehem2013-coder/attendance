"""Alerts raised by a check-in / check-out attempt (flagged, rejected, late)."""

from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Attendance, AttendanceEvent, Employee, Location, Organization
from app.models.enums import ArrivalStatus, AttendanceAction, EventResult, NotificationEvent
from app.services.notifications import notify

# Human wording for HR / managers (the employee never sees these).
REASONS = {
    "OUTSIDE_LOCATION": "Outside the office radius",
    "POOR_ACCURACY": "GPS signal too weak",
    "STALE_LOCATION": "Old GPS reading",
    "MOCK_LOCATION": "Fake-GPS app detected",
    "INTEGRITY_FAIL": "App/phone integrity check failed",
    "INTEGRITY_MISSING": "No integrity token",
    "IMPOSSIBLE_TRAVEL": "Impossible travel speed",
    "CLOCK_SKEW": "Phone clock changed",
    "QR_INVALID": "Invalid or expired office QR",
    "QR_MISSING": "Office QR not scanned",
    "MULTIPLE_WARNINGS": "Several small doubts together",
    "BAD_SIGNATURE": "Request not signed by the approved phone",
    "NO_DEVICE_KEY": "Phone has no security key",
    "REPLAY": "Re-used request (possible copy)",
}

# Ordinary mistakes, not worth an alert.
_ROUTINE_REJECTIONS = {
    "ALREADY_CHECKED_IN", "NOT_CHECKED_IN", "NO_ASSIGNED_LOCATION",
    "CHALLENGE_EXPIRED", "CHALLENGE_UNKNOWN", "CHALLENGE_MISMATCH",
}


def reason_label(code: str | None) -> str:
    return REASONS.get(code or "", (code or "Unknown").replace("_", " ").capitalize())


def attempt_alerts(
    db: Session,
    employee: Employee,
    action: AttendanceAction,
    event: AttendanceEvent,
    location: Location | None,
    attendance: Attendance | None,
) -> int:
    """Create the alerts for one stored attempt. Returns the number created."""
    org = db.get(Organization, employee.organization_id)
    tz = ZoneInfo(location.timezone if location else org.default_timezone)
    local = event.server_received_at.astimezone(tz)
    what = "Check-in" if action == AttendanceAction.CHECK_IN else "Check-out"
    rows = [("Employee", f"{employee.full_name} ({employee.employee_code})"),
            ("Time", local.strftime("%a %d %b %Y, %H:%M")),
            ("Location", location.name if location else "-")]
    common = dict(organization_id=employee.organization_id, employee=employee)
    created = 0

    if event.result == EventResult.FLAGGED:
        created += notify(
            db, **common, event=NotificationEvent.SUSPICIOUS_CHECK_IN,
            title=f"{what} needs review: {employee.full_name}",
            lines=[f"{employee.full_name}'s {what.lower()} was recorded but needs HR review before it counts."],
            rows=rows + [("Reason", reason_label(event.reason_code))],
            link="/review", dedupe_key=f"flag:{event.id}",
        )
    elif event.result == EventResult.REJECTED and event.reason_code not in _ROUTINE_REJECTIONS:
        created += notify(
            db, **common, event=NotificationEvent.REJECTED_CHECK_IN,
            title=f"{what} rejected: {employee.full_name}",
            lines=[f"A {what.lower()} by {employee.full_name} was refused by the security checks."],
            rows=rows + [("Reason", reason_label(event.reason_code))],
            link="/review", dedupe_key=f"reject:{employee.id}:{local.date().isoformat()}",
        )

    if (action == AttendanceAction.CHECK_IN and attendance is not None
            and attendance.arrival_status == ArrivalStatus.LATE):
        start = attendance.scheduled_start.strftime("%H:%M") if attendance.scheduled_start else "-"
        created += notify(
            db, **common, event=NotificationEvent.LATE_EMPLOYEE,
            title=f"Late arrival: {employee.full_name}",
            lines=[f"{employee.full_name} checked in late today."],
            rows=rows + [("Work starts", start)],
            link="/attendance", dedupe_key=f"late:{employee.id}:{attendance.attendance_date.isoformat()}",
        )
    return created
