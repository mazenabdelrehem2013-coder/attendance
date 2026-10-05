"""Verification signals and the decision engine (no database)."""

from app.models.enums import EventResult, PolicyAction, SignalResult
from app.services.attendance.verification import (
    SignalOutcome,
    decide,
    geofence_signal,
    gps_accuracy_signal,
    location_age_signal,
)

FLAG, REJECT, ALLOW = PolicyAction.FLAG, PolicyAction.REJECT, PolicyAction.ALLOW
PASS, WARN, FAIL = SignalResult.PASS, SignalResult.WARN, SignalResult.FAIL


# --- Geofence (radius 200 m) ------------------------------------------------------------------


def test_example_from_the_spec_85_m_passes():
    assert geofence_signal(85, 200, 10, FLAG).result == PASS


def test_example_from_the_spec_850_m_fails():
    s = geofence_signal(850, 200, 10, FLAG)
    assert s.result == FAIL and s.reason_code == "OUTSIDE_LOCATION"


def test_exactly_on_the_boundary_passes():
    assert geofence_signal(200, 200, 10, FLAG).result == PASS


def test_just_outside_but_within_gps_uncertainty_warns():
    s = geofence_signal(230, 200, 40, FLAG)  # 230 - 40 = 190 <= 200: could be inside
    assert s.result == WARN and s.reason_code == "NEAR_BOUNDARY"


def test_outside_even_allowing_for_gps_uncertainty_fails():
    assert geofence_signal(260, 200, 40, FLAG).result == FAIL  # 260 - 40 = 220 > 200


def test_geofence_details_are_recorded():
    assert geofence_signal(85.04, 200, 12.3, FLAG).details == {"distance_m": 85.0, "radius_m": 200, "accuracy_m": 12.3}


# --- GPS accuracy (max 100 m) -------------------------------------------------------------------


def test_good_accuracy_passes():
    assert gps_accuracy_signal(12, 100, FLAG).result == PASS


def test_accuracy_at_the_limit_passes():
    assert gps_accuracy_signal(100, 100, FLAG).result == PASS


def test_poor_accuracy_fails():
    s = gps_accuracy_signal(150, 100, FLAG)
    assert s.result == FAIL and s.reason_code == "POOR_ACCURACY"


def test_zero_accuracy_is_suspicious():
    s = gps_accuracy_signal(0, 100, FLAG)
    assert s.result == WARN and s.reason_code == "ZERO_ACCURACY"


# --- Location age (max 60 s) ------------------------------------------------------------------


def test_fresh_reading_passes():
    assert location_age_signal(2_000, seconds_since_challenge=8, max_fix_age_s=60, on_fail=FLAG).result == PASS


def test_old_reading_fails():
    s = location_age_signal(120_000, seconds_since_challenge=200, max_fix_age_s=60, on_fail=FLAG)
    assert s.result == FAIL and s.reason_code == "STALE_LOCATION"


def test_reading_taken_before_the_challenge_fails():
    # Challenge issued 10 s ago, but the reading is 40 s old: it was captured earlier and reused.
    s = location_age_signal(40_000, seconds_since_challenge=10, max_fix_age_s=60, on_fail=FLAG)
    assert s.result == FAIL and s.details["taken_before_challenge"] is True


def test_small_clock_differences_are_tolerated():
    assert location_age_signal(13_000, seconds_since_challenge=10, max_fix_age_s=60, on_fail=FLAG).result == PASS


# --- Decision ---------------------------------------------------------------------------------


def _s(signal, result, action=FLAG, reason=None):
    return SignalOutcome(signal, result, action, reason)


def test_all_pass_is_accepted():
    d = decide([_s("replay_check", PASS), _s("geofence", PASS)], "CHECK_IN_OK")
    assert d.result == EventResult.ACCEPTED and d.message_code == "CHECK_IN_OK" and d.risk_score == 0


def test_a_flag_failure_is_flagged():
    d = decide([_s("geofence", FAIL, FLAG, "OUTSIDE_LOCATION")], "OK")
    assert d.result == EventResult.FLAGGED and d.reason_code == "OUTSIDE_LOCATION"
    assert d.message_code == "PENDING_REVIEW"


def test_reject_wins_over_flag():
    d = decide([_s("geofence", FAIL, FLAG, "OUTSIDE_LOCATION"),
                _s("gps_accuracy", FAIL, REJECT, "POOR_ACCURACY")], "OK")
    assert d.result == EventResult.REJECTED and d.reason_code == "POOR_ACCURACY"


def test_allow_policy_ignores_the_failure_but_keeps_the_record():
    d = decide([_s("gps_accuracy", FAIL, ALLOW, "POOR_ACCURACY")], "OK")
    assert d.result == EventResult.ACCEPTED
    assert d.signals["gps_accuracy"] == FAIL and d.risk_score > 0


def test_one_warning_is_accepted_two_are_flagged():
    one = decide([_s("geofence", WARN, reason="NEAR_BOUNDARY")], "OK")
    assert one.result == EventResult.ACCEPTED
    two = decide([_s("geofence", WARN, reason="NEAR_BOUNDARY"), _s("gps_accuracy", WARN, reason="ZERO_ACCURACY")], "OK")
    assert two.result == EventResult.FLAGGED and two.reason_code == "MULTIPLE_WARNINGS"
    assert two.details["warnings"] == ["NEAR_BOUNDARY", "ZERO_ACCURACY"]


def test_employee_messages_never_reveal_the_security_check():
    for reason in ("MOCK_LOCATION", "INTEGRITY_FAIL", "IMPOSSIBLE_TRAVEL", "REPLAY"):
        d = decide([_s("mock_location", FAIL, REJECT, reason)], "OK")
        assert d.message_code == "VERIFICATION_FAILED"


def test_fixable_rejections_get_helpful_messages():
    assert decide([_s("gps_accuracy", FAIL, REJECT, "POOR_ACCURACY")], "OK").message_code == "WEAK_SIGNAL"
    assert decide([_s("location_age", FAIL, REJECT, "STALE_LOCATION")], "OK").message_code == "WEAK_SIGNAL"
    assert decide([_s("geofence", FAIL, REJECT, "OUTSIDE_LOCATION")], "OK").message_code == "OUTSIDE_LOCATION"


def test_unused_signals_are_recorded_as_not_applicable():
    d = decide([_s("geofence", PASS)], "OK")
    assert d.signals["qr_check"] == SignalResult.NOT_APPLICABLE
