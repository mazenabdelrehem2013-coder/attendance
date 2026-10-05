"""Phase 8 signals without the database: canonical payload, integrity verdicts, movement, clock."""

import uuid
from datetime import UTC, datetime

from app.models.enums import AttendanceAction, PolicyAction, SignalResult
from app.schemas.attendance import AttendanceSubmission
from app.services.attendance.canonical import canonical_payload, request_hash
from app.services.attendance.integrity import evaluate_verdict
from app.services.attendance.verification import (
    clock_skew_signal,
    device_signature_signal,
    mock_location_signal,
    movement_signal,
)

FLAG = PolicyAction.FLAG
NOW = datetime(2026, 10, 5, 8, 0, tzinfo=UTC)


# --- Canonical payload (the mobile app must produce exactly this) -----------------------------


def test_canonical_payload_format_is_stable():
    data = AttendanceSubmission(
        client_request_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        challenge_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        nonce="abcdefghijklmnop",
        device_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        latitude=6.4283, longitude=3.422, accuracy_m=12.5, fix_age_ms=1500,
        is_mock_location=False, device_time=NOW, signature="x",
    )
    assert canonical_payload(AttendanceAction.CHECK_IN, data) == (
        "v1|CHECK_IN|22222222-2222-2222-2222-222222222222|abcdefghijklmnop|"
        "11111111-1111-1111-1111-111111111111|33333333-3333-3333-3333-333333333333|"
        "6.428300|3.422000|12.50|1500|0|1791187200000|"
    )
    assert len(request_hash("x")) == 64


# --- Device signature / mock / clock ----------------------------------------------------------


def test_device_signature_is_a_hard_rule():
    assert device_signature_signal(True, True).result == SignalResult.PASS
    for has_key, valid, reason in [(True, False, "BAD_SIGNATURE"), (False, False, "NO_DEVICE_KEY")]:
        s = device_signature_signal(has_key, valid)
        assert s.result == SignalResult.FAIL and s.reason_code == reason
        assert s.action_on_fail == PolicyAction.REJECT  # not configurable


def test_mock_location():
    assert mock_location_signal(False, FLAG).result == SignalResult.PASS
    s = mock_location_signal(True, PolicyAction.REJECT)
    assert s.result == SignalResult.FAIL and s.reason_code == "MOCK_LOCATION"


def test_clock_skew_within_limit():
    assert clock_skew_signal(240, 300, FLAG).result == SignalResult.PASS
    assert clock_skew_signal(-240, 300, FLAG).result == SignalResult.PASS


def test_clock_skew_beyond_limit_either_direction():
    assert clock_skew_signal(301, 300, FLAG).result == SignalResult.FAIL
    assert clock_skew_signal(-5700, 300, FLAG).reason_code == "CLOCK_SKEW"


# --- Impossible movement (limit 200 km/h) -----------------------------------------------------


def test_lagos_then_abuja_15_minutes_later_is_impossible():
    s = movement_signal(530_000, 10, 10, 15 * 60, 200, FLAG)
    assert s.result == SignalResult.FAIL and s.reason_code == "IMPOSSIBLE_TRAVEL"
    assert s.details["implied_speed_kmh"] > 2000


def test_lagos_then_abuja_4_hours_later_is_possible():
    assert movement_signal(530_000, 10, 10, 4 * 3600, 200, FLAG).result == SignalResult.PASS


def test_gps_jitter_is_not_travel():
    # 120 m "jump" in 10 seconds, but each reading was only accurate to 70 m.
    assert movement_signal(120, 70, 70, 10, 200, FLAG).result == SignalResult.PASS


def test_no_previous_event():
    assert movement_signal(None, 10, 0, 0, 200, FLAG).result == SignalResult.NOT_APPLICABLE


# --- Play Integrity verdicts ------------------------------------------------------------------

HASH = "a" * 64
PACKAGE = "com.example.attendance"


def verdict(**overrides):
    payload = {
        "requestDetails": {"requestPackageName": PACKAGE, "requestHash": HASH,
                           "timestampMillis": str(int(NOW.timestamp() * 1000) - 5000)},
        "appIntegrity": {"appRecognitionVerdict": "PLAY_RECOGNIZED"},
        "deviceIntegrity": {"deviceRecognitionVerdict": ["MEETS_DEVICE_INTEGRITY"]},
        "accountDetails": {"appLicensingVerdict": "LICENSED"},
    }
    for path, value in overrides.items():
        section, key = path.split("__")
        payload[section][key] = value
    return payload


def evaluate(payload):
    return evaluate_verdict(payload, HASH, PACKAGE, NOW, 120, FLAG)


def test_genuine_app_on_genuine_phone_passes():
    assert evaluate(verdict()).result == SignalResult.PASS


def test_modified_or_sideloaded_app_fails():
    s = evaluate(verdict(appIntegrity__appRecognitionVerdict="UNRECOGNIZED_VERSION"))
    assert s.result == SignalResult.FAIL and "APP_NOT_RECOGNIZED" in s.details["problems"]


def test_rooted_phone_or_emulator_fails():
    s = evaluate(verdict(deviceIntegrity__deviceRecognitionVerdict=[]))
    assert "DEVICE_INTEGRITY" in s.details["problems"]


def test_token_made_for_another_request_fails():
    s = evaluate(verdict(requestDetails__requestHash="b" * 64))
    assert "REQUEST_MISMATCH" in s.details["problems"]


def test_old_token_fails():
    old = str(int(NOW.timestamp() * 1000) - 10 * 60 * 1000)
    assert "TOKEN_TOO_OLD" in evaluate(verdict(requestDetails__timestampMillis=old)).details["problems"]


def test_token_for_another_app_fails():
    assert "WRONG_PACKAGE" in evaluate(verdict(requestDetails__requestPackageName="com.evil")).details["problems"]


def test_empty_verdict_fails():
    assert evaluate({}).result == SignalResult.FAIL


def test_device_time_milliseconds_are_exact():
    from app.services.attendance.canonical import epoch_millis
    # 0.123 s can't be stored exactly as a float; the result must still be ...123.
    moment = datetime(2026, 10, 5, 8, 0, 0, 123000, tzinfo=UTC)
    assert epoch_millis(moment) == 1791187200123
    for ms in range(1000):
        m = datetime(2026, 10, 5, 8, 0, 0, ms * 1000, tzinfo=UTC)
        assert epoch_millis(m) % 1000 == ms
