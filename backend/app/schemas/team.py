import uuid
from datetime import date, datetime

from pydantic import BaseModel


class TeamRow(BaseModel):
    employee_id: uuid.UUID
    employee_code: str
    full_name: str
    department: str | None
    location: str | None
    check_in: datetime | None
    check_out: datetime | None
    worked_minutes: int
    # PRESENT / LATE / PENDING_REVIEW / NOT_CHECKED_IN / ABSENT / ON_LEAVE / HOLIDAY / NON_WORKING_DAY
    status: str
    arrival_status: str | None
    departure_status: str | None  # CHECKED_OUT / EARLY_DEPARTURE / MISSING_CHECKOUT
    checked_in_now: bool
    verification_status: str | None  # VERIFIED / PENDING_REVIEW
    note: str | None  # e.g. leave type


class TeamSummary(BaseModel):
    total_employees: int
    present: int  # PRESENT + LATE
    late: int
    absent: int
    not_checked_in: int
    checked_in_now: int
    missing_checkout: int
    suspicious: int  # pending HR review
    on_leave: int


class TeamAttendance(BaseModel):
    date: date
    generated_at: datetime
    summary: TeamSummary
    rows: list[TeamRow]
