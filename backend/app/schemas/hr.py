import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import PolicyAction, Severity, VerificationMode
from app.schemas.team import TeamSummary


class GroupCount(BaseModel):
    name: str
    employees: int
    present: int  # incl. late
    late: int
    absent: int
    pending_review: int
    on_leave: int


class HrOverview(BaseModel):
    date: date
    summary: TeamSummary
    suspicious_attempts: int  # flagged attempts that day
    rejected_attempts: int
    pending_reviews_total: int  # all flagged attempts still waiting for HR, any day
    by_location: list[GroupCount]
    by_department: list[GroupCount]


class TrendPoint(BaseModel):
    date: date
    present: int  # incl. late
    late: int
    absent: int
    pending_review: int
    on_leave: int
    attendance_rate: float | None = Field(description="present / (present + absent); None on days off")


class SecurityEventOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    event_type: str
    severity: Severity
    employee_code: str | None
    employee_name: str | None
    attendance_event_id: uuid.UUID | None
    details: dict


class PolicyOut(BaseModel):
    location_id: uuid.UUID | None
    location_name: str | None
    verification_mode: VerificationMode
    on_mock_location: PolicyAction
    on_integrity_fail: PolicyAction
    on_poor_accuracy: PolicyAction
    on_stale_location: PolicyAction
    on_outside_geofence: PolicyAction
    on_impossible_travel: PolicyAction
    on_clock_skew: PolicyAction
    on_qr_fail: PolicyAction
    max_accuracy_m: int
    max_fix_age_s: int
    challenge_ttl_s: int
    max_travel_speed_kmh: int
    max_clock_skew_s: int
    flagged_counts_before_review: bool


class PolicyUpdate(BaseModel):
    """Only the fields you send are changed."""

    verification_mode: VerificationMode | None = None
    on_mock_location: PolicyAction | None = None
    on_integrity_fail: PolicyAction | None = None
    on_poor_accuracy: PolicyAction | None = None
    on_stale_location: PolicyAction | None = None
    on_outside_geofence: PolicyAction | None = None
    on_impossible_travel: PolicyAction | None = None
    on_clock_skew: PolicyAction | None = None
    on_qr_fail: PolicyAction | None = None
    max_accuracy_m: int | None = Field(None, ge=5, le=2000)
    max_fix_age_s: int | None = Field(None, ge=5, le=600)
    challenge_ttl_s: int | None = Field(None, ge=15, le=600)
    max_travel_speed_kmh: int | None = Field(None, ge=10, le=2000)
    max_clock_skew_s: int | None = Field(None, ge=0, le=86400)
    flagged_counts_before_review: bool | None = None


class PolicySet(BaseModel):
    default: PolicyOut
    locations: list[PolicyOut]
