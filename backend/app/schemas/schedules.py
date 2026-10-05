"""Scheduled reports (ready to download), alert settings and in-app notifications."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import Name

ScheduledReport = Literal["daily", "weekly", "monthly", "late", "absence", "suspicious"]
Frequency = Literal["daily", "weekly", "monthly"]
RecipientRole = Literal["HR", "MANAGER", "ADMIN"]


class ScheduleIn(BaseModel):
    name: Name
    report: ScheduledReport
    frequency: Frequency
    time: str = Field("08:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="Local time HH:MM")
    days: list[int] = Field([0, 1, 2, 3, 4, 5], description="daily: weekdays to send on, 0 = Monday ... 6 = Sunday")
    weekday: int = Field(0, ge=0, le=6, description="weekly: day to send on, 0 = Monday")
    day_of_month: int = Field(1, ge=1, le=28, description="monthly: day of the month to send on")
    daily_period: Literal["today", "previous"] = Field(
        "previous", description="daily: report on today so far, or on the previous working day")
    formats: list[Literal["EXCEL", "PDF"]] = Field(["EXCEL", "PDF"], min_length=1)
    recipient_roles: list[RecipientRole] = Field(
        ["HR"], description="Who can download it. MANAGER = each manager gets a report of their own team only")
    location_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    is_enabled: bool = True

    @model_validator(mode="after")
    def _check(self):
        fixed = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}
        if self.report in fixed and self.frequency != fixed[self.report]:
            raise ValueError(f"The {self.report} report can only be sent {fixed[self.report]}.")
        if self.frequency == "daily":
            if not self.days or any(d < 0 or d > 6 for d in self.days):
                raise ValueError("Choose at least one day (0 = Monday ... 6 = Sunday).")
            self.days = sorted(set(self.days))
        if not self.recipient_roles:
            raise ValueError("Choose who the report is for.")
        self.formats = sorted(set(self.formats))
        self.recipient_roles = sorted(set(self.recipient_roles))
        return self


class ScheduleOut(ScheduleIn):
    id: uuid.UUID
    description: str  # e.g. "Every Monday at 08:00"
    next_run_at: datetime | None
    last_run_at: datetime | None
    timezone: str


class RunResult(BaseModel):
    files_created: int
    message: str


class AlertSetting(BaseModel):
    event: str
    label: str
    description: str
    enabled: bool
    roles: list[RecipientRole]
    thresholds: dict[str, int] = {}


class AlertSettingUpdate(BaseModel):
    enabled: bool
    roles: list[RecipientRole]
    thresholds: dict[Literal["absences", "days"], int] = {}

    @model_validator(mode="after")
    def _check(self):
        t = self.thresholds
        if "absences" in t and not 1 <= t["absences"] <= 31:
            raise ValueError("Absences must be between 1 and 31.")
        if "days" in t and not 7 <= t["days"] <= 92:
            raise ValueError("The period must be between 7 and 92 days.")
        return self


class NotificationOut(BaseModel):
    id: uuid.UUID
    event: str
    title: str
    body: str
    link: str | None
    created_at: datetime
    read: bool


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread: int


class ReadyReport(BaseModel):
    """A report file created by a schedule, ready to download."""

    id: uuid.UUID  # file id (use with /reports/ready/{id}/download)
    title: str
    period: str
    scope: str  # "All employees" / "Your team"
    schedule_name: str | None
    format: str  # EXCEL | PDF
    filename: str
    size_bytes: int
    rows: int | None
    created_at: datetime


class ReadyReportList(BaseModel):
    items: list[ReadyReport]
    total: int
    keep_days: int
