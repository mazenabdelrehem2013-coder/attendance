import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AttendanceAction, EventResult, ReviewDecision


class ReviewItem(BaseModel):
    """One flagged (or rejected) check-in/out attempt, as HR sees it."""

    event_id: uuid.UUID
    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    event_type: AttendanceAction
    server_time: datetime
    result: EventResult
    reason_code: str | None  # the real reason (never shown to the employee)
    location: str | None
    distance_m: float | None
    accuracy_m: float | None
    risk_score: int | None
    failed_checks: list[str]
    review_decision: ReviewDecision | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None


class ReviewPage(BaseModel):
    items: list[ReviewItem]
    total: int


class ReviewDetail(ReviewItem):
    latitude: float | None
    longitude: float | None
    fix_age_ms: int | None
    device_reported_at: datetime | None
    app_version: str | None
    device_model: str | None
    device_status: str | None
    checks: dict[str, str]  # signal -> PASS / WARN / FAIL / NOT_APPLICABLE
    details: dict  # numbers behind each check
    policy: dict  # rules in force at that moment
    security_events: list[dict]


class ReviewRequest(BaseModel):
    decision: ReviewDecision
    note: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _note_for_rejection(self):
        if self.decision == ReviewDecision.REJECTED and len((self.note or "").strip()) < 3:
            raise ValueError("Please give a reason when rejecting.")
        return self


class ReviewFilters(BaseModel):
    state: Literal["PENDING", "REVIEWED", "REJECTED_ATTEMPTS"] = "PENDING"
    date_from: date | None = None
    date_to: date | None = None
    employee_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    reason: str | None = None
