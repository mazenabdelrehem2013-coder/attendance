"""Attendance core.

attendance              one summary row per employee per day
attendance_sessions     each check-in/check-out pair within that day
attendance_events       every check-in/check-out ATTEMPT (accepted, flagged or rejected) - append-only
attendance_verification the individual security signals for one event - append-only
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, Timestamps, UUIDPk, str_enum
from app.models.enums import (
    ArrivalStatus,
    AttendanceAction,
    DayStatus,
    DepartureStatus,
    EventResult,
    PolicyAction,
    ReviewDecision,
    SessionStatus,
    SignalResult,
    SignalType,
    VerificationMode,
    VerificationStatus,
)


def _policy_action(name: str):
    return mapped_column(
        str_enum(PolicyAction, name), default=PolicyAction.FLAG, server_default=PolicyAction.FLAG.value
    )


def _signal(name: str):
    return mapped_column(
        str_enum(SignalResult, name),
        default=SignalResult.NOT_APPLICABLE,
        server_default=SignalResult.NOT_APPLICABLE.value,
    )


class AttendancePolicy(UUIDPk, Timestamps, Base):
    """Security rules. location_id NULL = organization default; a row per location overrides it."""

    __tablename__ = "attendance_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "location_id", postgresql_nulls_not_distinct=True),
        CheckConstraint("max_accuracy_m BETWEEN 5 AND 2000", name="max_accuracy_range"),
        CheckConstraint("max_fix_age_s BETWEEN 5 AND 600", name="max_fix_age_range"),
        CheckConstraint("challenge_ttl_s BETWEEN 15 AND 600", name="challenge_ttl_range"),
        CheckConstraint("max_travel_speed_kmh BETWEEN 10 AND 2000", name="max_speed_range"),
        CheckConstraint("max_clock_skew_s BETWEEN 0 AND 86400", name="max_clock_skew_range"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    verification_mode: Mapped[VerificationMode] = mapped_column(
        str_enum(VerificationMode, "verification_mode"),
        default=VerificationMode.GPS_ONLY,
        server_default=VerificationMode.GPS_ONLY.value,
    )
    on_mock_location: Mapped[PolicyAction] = _policy_action("on_mock_location")
    on_integrity_fail: Mapped[PolicyAction] = _policy_action("on_integrity_fail")
    on_poor_accuracy: Mapped[PolicyAction] = _policy_action("on_poor_accuracy")
    on_stale_location: Mapped[PolicyAction] = _policy_action("on_stale_location")
    on_outside_geofence: Mapped[PolicyAction] = _policy_action("on_outside_geofence")
    on_impossible_travel: Mapped[PolicyAction] = _policy_action("on_impossible_travel")
    on_clock_skew: Mapped[PolicyAction] = _policy_action("on_clock_skew")
    on_qr_fail: Mapped[PolicyAction] = _policy_action("on_qr_fail")
    max_accuracy_m: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    max_fix_age_s: Mapped[int] = mapped_column(Integer, default=60, server_default="60")
    challenge_ttl_s: Mapped[int] = mapped_column(Integer, default=90, server_default="90")
    max_travel_speed_kmh: Mapped[int] = mapped_column(Integer, default=200, server_default="200")
    max_clock_skew_s: Mapped[int] = mapped_column(Integer, default=300, server_default="300")
    # Decision 11.6: flagged events do not count until HR approves.
    flagged_counts_before_review: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class AttendanceChallenge(UUIDPk, CreatedAt, Base):
    """Single-use server nonce. Must be fetched right before a check-in/out."""

    __tablename__ = "attendance_challenges"
    __table_args__ = (
        Index("ix_attendance_challenges_expires_at", "expires_at"),
        CheckConstraint("expires_at > issued_at", name="expiry_after_issue"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), index=True)
    device_registration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("device_registrations.id"))
    action: Mapped[AttendanceAction] = mapped_column(str_enum(AttendanceAction, "action"))
    nonce_hash: Mapped[str] = mapped_column(String(64), unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(INET)


class Attendance(UUIDPk, Timestamps, Base):
    """Daily summary for one employee. Recomputed from sessions; never typed in by hand
    (HR corrections go through attendance_adjustments)."""

    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("employee_id", "attendance_date"),
        Index("ix_attendance_location_date", "location_id", "attendance_date"),
        Index(
            "ix_attendance_needs_attention",
            "verification_status",
            postgresql_where=text("verification_status <> 'VERIFIED'"),
        ),
        CheckConstraint("worked_minutes >= 0", name="worked_minutes_positive"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    attendance_date: Mapped[date] = mapped_column(Date, index=True)  # local date at the location
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    # Copy of the schedule that applied that day, so later schedule edits don't rewrite history.
    scheduled_start: Mapped[time | None] = mapped_column(Time)
    scheduled_end: Mapped[time | None] = mapped_column(Time)
    grace_minutes: Mapped[int | None] = mapped_column(Integer)
    early_departure_minutes: Mapped[int | None] = mapped_column(Integer)
    first_check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    arrival_status: Mapped[ArrivalStatus | None] = mapped_column(
        str_enum(ArrivalStatus, "arrival_status")
    )
    departure_status: Mapped[DepartureStatus | None] = mapped_column(
        str_enum(DepartureStatus, "departure_status")
    )
    day_status: Mapped[DayStatus | None] = mapped_column(str_enum(DayStatus, "day_status"))
    verification_status: Mapped[VerificationStatus | None] = mapped_column(
        str_enum(VerificationStatus, "verification_status")
    )
    is_manually_adjusted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )


class AttendanceEvent(UUIDPk, CreatedAt, Base):
    """One check-in or check-out attempt with the evidence sent by the phone. Append-only."""

    __tablename__ = "attendance_events"
    __table_args__ = (
        UniqueConstraint("employee_id", "client_request_id"),  # duplicate/retry protection
        Index("ix_attendance_events_employee_time", "employee_id", "server_received_at"),
        Index("ix_attendance_events_location_time", "location_id", "server_received_at"),
        Index("ix_attendance_events_result", "result"),
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude_range"
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180", name="longitude_range"
        ),
        CheckConstraint("accuracy_m IS NULL OR accuracy_m >= 0", name="accuracy_positive"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    attendance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attendance.id"), index=True
    )  # NULL for rejected attempts
    event_type: Mapped[AttendanceAction] = mapped_column(str_enum(AttendanceAction, "event_type"))
    client_request_id: Mapped[uuid.UUID]
    challenge_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attendance_challenges.id"), unique=True
    )
    device_registration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("device_registrations.id")
    )
    # Authoritative time is the server's. The phone's clock is kept only as evidence.
    server_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    device_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    fix_age_ms: Mapped[int | None] = mapped_column(Integer)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    distance_m: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    app_version: Mapped[str | None] = mapped_column(String(50))
    os_version: Mapped[str | None] = mapped_column(String(50))
    ip_address: Mapped[str | None] = mapped_column(INET)
    result: Mapped[EventResult] = mapped_column(str_enum(EventResult, "result"))
    reason_code: Mapped[str | None] = mapped_column(String(50))  # internal, e.g. OUTSIDE_LOCATION
    employee_message_code: Mapped[str | None] = mapped_column(String(50))  # safe for the employee


class AttendanceSession(UUIDPk, Timestamps, Base):
    """A check-in/check-out pair, built from ACCEPTED or FLAGGED events (never REJECTED ones)."""

    __tablename__ = "attendance_sessions"
    __table_args__ = (
        # An employee can have only one open session at a time.
        Index(
            "uq_attendance_sessions_one_open",
            "employee_id",
            unique=True,
            postgresql_where=text("status = 'OPEN'"),
        ),
        CheckConstraint(
            "check_out_at IS NULL OR check_out_at >= check_in_at", name="out_after_in"
        ),
        CheckConstraint("worked_minutes >= 0", name="worked_minutes_positive"),
    )

    attendance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attendance.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    check_in_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attendance_events.id"), unique=True
    )
    check_out_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attendance_events.id"), unique=True
    )
    check_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[SessionStatus] = mapped_column(
        str_enum(SessionStatus, "session_status"),
        default=SessionStatus.OPEN,
        server_default=SessionStatus.OPEN.value,
    )
    # True while its check-in or check-out is FLAGGED and not yet approved by HR.
    # Such sessions don't count towards worked hours or arrival status (decision 11.6).
    pending_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class AttendanceVerification(UUIDPk, CreatedAt, Base):
    """Every security signal for one event, plus the policy in force. Append-only."""

    __tablename__ = "attendance_verification"
    __table_args__ = (
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="risk_score_range"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attendance_events.id"), unique=True)
    geofence: Mapped[SignalResult] = _signal("geofence")
    gps_accuracy: Mapped[SignalResult] = _signal("gps_accuracy")
    mock_location: Mapped[SignalResult] = _signal("mock_location")
    play_integrity: Mapped[SignalResult] = _signal("play_integrity")
    location_age: Mapped[SignalResult] = _signal("location_age")
    timestamp_check: Mapped[SignalResult] = _signal("timestamp_check")
    replay_check: Mapped[SignalResult] = _signal("replay_check")
    movement_check: Mapped[SignalResult] = _signal("movement_check")
    qr_check: Mapped[SignalResult] = _signal("qr_check")
    device_check: Mapped[SignalResult] = _signal("device_check")
    details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    risk_score: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    policy_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    final_result: Mapped[EventResult] = mapped_column(str_enum(EventResult, "final_result"))


class VerificationSignal(UUIDPk, CreatedAt, Base):
    """Extra verification methods (QR now; NFC, BLE beacon, selfie later). Append-only."""

    __tablename__ = "verification_signals"

    verification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attendance_verification.id"), index=True
    )
    signal_type: Mapped[SignalType] = mapped_column(str_enum(SignalType, "signal_type"))
    result: Mapped[SignalResult] = mapped_column(str_enum(SignalResult, "result"))
    details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class AttendanceEventReview(UUIDPk, CreatedAt, Base):
    """HR decision on a FLAGGED event. Kept separate so events stay unchanged. Append-only."""

    __tablename__ = "attendance_event_reviews"

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attendance_events.id"), unique=True)
    decision: Mapped[ReviewDecision] = mapped_column(str_enum(ReviewDecision, "decision"))
    reviewed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)


class AttendanceAdjustment(UUIDPk, CreatedAt, Base):
    """A manual correction by HR, with reason. Append-only."""

    __tablename__ = "attendance_adjustments"

    attendance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attendance.id"), index=True)
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    field_name: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)


class QrSession(UUIDPk, Timestamps, Base):
    """A QR display screen at a location. The token secret is derived on the server from a
    master key in Secret Manager + location + key_version; it is never stored here."""

    __tablename__ = "qr_sessions"
    __table_args__ = (
        CheckConstraint("rotation_seconds BETWEEN 15 AND 86400", name="rotation_range"),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), index=True)
    display_label: Mapped[str] = mapped_column(String(100))
    # Hash of the credential the display screen uses to fetch tokens.
    display_credential_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    key_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    rotation_seconds: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
