import uuid
from datetime import date, datetime

from pydantic import BaseModel


class DailyRow(BaseModel):
    employee: str
    employee_code: str
    department: str | None
    manager: str | None
    location: str | None
    check_in: str | None  # "09:07" local time
    check_out: str | None
    worked_minutes: int
    status: str
    departure_status: str | None = None  # CHECKED_OUT / EARLY_DEPARTURE / MISSING_CHECKOUT
    verification_status: str | None


class DailyReport(BaseModel):
    title: str
    date: date
    generated_at: datetime
    rows: list[DailyRow]
    totals: dict[str, int]


class EmployeePeriod(BaseModel):
    employee_id: uuid.UUID
    employee: str
    employee_code: str
    department: str | None
    manager: str | None
    location: str | None
    working_days: int
    present_days: int  # incl. late
    late_days: int
    absent_days: int
    pending_review_days: int
    leave_days: int
    holiday_days: int
    early_departure_days: int
    missing_checkout_days: int
    average_check_in: str | None  # "09:12"
    average_check_out: str | None
    average_worked_minutes: int | None
    total_worked_minutes: int
    attendance_rate: float | None  # present / working days


class GroupTotal(BaseModel):
    name: str
    employees: int
    working_days: int
    present_days: int
    late_days: int
    absent_days: int
    attendance_rate: float | None


class PeriodReport(BaseModel):
    title: str
    date_from: date
    date_to: date
    generated_at: datetime
    rows: list[EmployeePeriod]
    totals: dict[str, int | float | None]
    by_location: list[GroupTotal]
    by_department: list[GroupTotal]
    by_manager: list[GroupTotal]


class EventRow(BaseModel):
    date: date
    employee: str
    employee_code: str
    department: str | None
    location: str | None
    detail: str  # e.g. "09:42 (27 min late)", "Absent", "Outside the office radius"
    minutes: int | None = None


class ListReport(BaseModel):
    title: str
    date_from: date
    date_to: date
    generated_at: datetime
    rows: list[EventRow]
