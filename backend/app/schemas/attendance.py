import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.enums import (
    ArrivalStatus,
    AttendanceAction,
    DayStatus,
    DepartureStatus,
    EventResult,
    SessionStatus,
    VerificationStatus,
)


class ChallengeRequest(BaseModel):
    action: AttendanceAction
    device_id: uuid.UUID = Field(description="id of the phone's approved device registration")


class ChallengeResponse(BaseModel):
    challenge_id: uuid.UUID
    nonce: str
    expires_at: datetime
    server_time: datetime


class AttendanceSubmission(BaseModel):
    """Evidence from the phone. The server decides everything - there is deliberately no
    'is inside' field, and the phone's clock is only recorded, never used."""

    model_config = ConfigDict(extra="forbid")

    client_request_id: uuid.UUID = Field(description="New random UUID per attempt; reuse it when retrying")
    challenge_id: uuid.UUID
    nonce: str = Field(min_length=10, max_length=100)
    device_id: uuid.UUID
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(ge=0, le=100_000, description="GPS accuracy radius in meters")
    fix_age_ms: int = Field(ge=0, le=86_400_000, description="Age of the GPS reading in ms")
    is_mock_location: bool = Field(False, description="Android Location.isMock() / isFromMockProvider()")
    device_time: AwareDatetime = Field(description="Phone clock (recorded and compared, never trusted)")
    app_version: str | None = Field(None, max_length=50)
    os_version: str | None = Field(None, max_length=50)
    qr_token: str | None = Field(None, max_length=200, description="Scanned office QR code, if required")
    integrity_token: str | None = Field(
        None, max_length=10_000, description="Play Integrity token for the request hash"
    )
    signature: str = Field(
        max_length=200, description="Base64 ECDSA signature of the canonical payload (device key)"
    )


class CheckResult(BaseModel):
    success: bool
    result: EventResult
    event_type: AttendanceAction
    event_id: uuid.UUID
    attendance_id: uuid.UUID | None
    server_time: datetime
    status: DayStatus | None = Field(description="Day status after this event")
    verification_status: VerificationStatus
    location: str | None
    distance_meters: int | None = Field(description="Only for accepted events")
    message_code: str
    message: str


class SessionOut(BaseModel):
    check_in_at: datetime
    check_out_at: datetime | None
    worked_minutes: int
    status: SessionStatus
    pending_review: bool


class AttendanceDay(BaseModel):
    attendance_id: uuid.UUID
    date: date
    location: str | None
    first_check_in_at: datetime | None
    last_check_out_at: datetime | None
    worked_minutes: int
    arrival_status: ArrivalStatus | None
    departure_status: DepartureStatus | None
    day_status: DayStatus | None
    verification_status: VerificationStatus | None
    sessions: list[SessionOut]


class AttemptOut(BaseModel):
    event_type: AttendanceAction
    server_time: datetime
    result: EventResult
    message: str


class TodayResponse(BaseModel):
    date: date
    timezone: str
    day_type: Literal["WORKING_DAY", "NON_WORKING_DAY", "HOLIDAY", "ON_LEAVE"]
    day_description: str | None = Field(description="Holiday name or leave type")
    scheduled_start: time | None
    scheduled_end: time | None
    state: Literal["NOT_CHECKED_IN", "CHECKED_IN", "CHECKED_OUT"]
    next_action: AttendanceAction
    qr_required: bool = Field(description="An office QR code must be scanned at your location(s)")
    attendance: AttendanceDay | None
    attempts: list[AttemptOut]
