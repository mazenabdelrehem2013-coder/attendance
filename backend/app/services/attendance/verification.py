"""Verification engine: independent checks ("signals") -> policy -> one decision.

Each signal returns PASS / WARN / FAIL / NOT_APPLICABLE. For a FAIL, the location's policy
decides what happens: ALLOW, FLAG (HR review) or REJECT. The final decision is the strictest
action of all failed signals. A risk score is stored for sorting HR's review queue, but it
never decides anything by itself.

Phase 6-7: replay, geofence (accuracy-aware), GPS accuracy, location age. Phase 8 adds mock
location, Play Integrity, clock skew, impossible movement, QR and device signature.
"""

from dataclasses import dataclass, field

from app.models.enums import EventResult, PolicyAction, SignalResult

# Column names on attendance_verification, in the order reasons are reported.
SIGNALS = (
    "replay_check",
    "device_check",
    "geofence",
    "gps_accuracy",
    "location_age",
    "mock_location",
    "play_integrity",
    "timestamp_check",
    "movement_check",
    "qr_check",
)

_RISK_WEIGHTS = {"FAIL": 30, "WARN": 10}


@dataclass(frozen=True)
class SignalOutcome:
    signal: str  # one of SIGNALS
    result: SignalResult
    action_on_fail: PolicyAction = PolicyAction.REJECT
    reason_code: str | None = None  # internal reason, e.g. OUTSIDE_LOCATION
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    result: EventResult
    reason_code: str | None
    message_code: str
    signals: dict[str, SignalResult]
    details: dict
    risk_score: int
    failures: tuple[tuple[str, str], ...] = ()  # (signal, reason) for every FAIL, any action


# Several "uncertain" signals together are treated like one failure and sent to HR.
WARNINGS_BEFORE_FLAG = 2

# Messages for rejections the employee can fix themselves; everything else stays general.
_REJECT_MESSAGES = {
    "OUTSIDE_LOCATION": "OUTSIDE_LOCATION",
    "POOR_ACCURACY": "WEAK_SIGNAL",
    "STALE_LOCATION": "WEAK_SIGNAL",
}


def decide(outcomes: list[SignalOutcome], success_message: str) -> Decision:
    signals = {name: SignalResult.NOT_APPLICABLE for name in SIGNALS}
    details: dict = {}
    for o in outcomes:
        signals[o.signal] = o.result
        if o.details:
            details[o.signal] = o.details

    ordered = sorted(outcomes, key=lambda o: SIGNALS.index(o.signal))
    failed = [o for o in ordered if o.result == SignalResult.FAIL]
    warnings = [o for o in ordered if o.result == SignalResult.WARN]
    rejects = [o for o in failed if o.action_on_fail == PolicyAction.REJECT]
    flags = [o for o in failed if o.action_on_fail == PolicyAction.FLAG]

    risk = min(100, sum(_RISK_WEIGHTS.get(o.result.value, 0) for o in outcomes))
    failures = tuple((o.signal, o.reason_code or o.signal) for o in failed)

    if rejects:
        reason = rejects[0].reason_code
        message = _REJECT_MESSAGES.get(reason, "VERIFICATION_FAILED")
        return Decision(EventResult.REJECTED, reason, message, signals, details, risk, failures)
    if flags:
        return Decision(EventResult.FLAGGED, flags[0].reason_code, "PENDING_REVIEW", signals, details,
                        risk, failures)
    if len(warnings) >= WARNINGS_BEFORE_FLAG:
        reason = "MULTIPLE_WARNINGS"
        details["warnings"] = [o.reason_code or o.signal for o in warnings]
        return Decision(EventResult.FLAGGED, reason, "PENDING_REVIEW", signals, details, risk, failures)
    return Decision(EventResult.ACCEPTED, None, success_message, signals, details, risk, failures)


# --- Signals --------------------------------------------------------------------------------


def geofence_signal(
    distance_m: float, radius_m: int, accuracy_m: float, on_fail: PolicyAction
) -> SignalOutcome:
    """Server-side geofence that takes GPS accuracy into account.

    A GPS fix means "the phone is somewhere within accuracy_m of this point":
      distance <= radius                 -> PASS  (the reported point is inside)
      distance - accuracy <= radius      -> WARN  (could be inside; the signal is too vague to be sure)
      distance - accuracy  > radius      -> FAIL  (outside even in the most favourable case)
    The phone never tells us whether it is inside.
    """
    details = {"distance_m": round(distance_m, 1), "radius_m": radius_m, "accuracy_m": round(accuracy_m, 1)}
    if distance_m <= radius_m:
        return SignalOutcome("geofence", SignalResult.PASS, on_fail, None, details)
    if distance_m - accuracy_m <= radius_m:
        return SignalOutcome("geofence", SignalResult.WARN, on_fail, "NEAR_BOUNDARY", details)
    return SignalOutcome("geofence", SignalResult.FAIL, on_fail, "OUTSIDE_LOCATION", details)


def gps_accuracy_signal(accuracy_m: float, max_accuracy_m: int, on_fail: PolicyAction) -> SignalOutcome:
    """Poor accuracy (e.g. indoors, network-only location) can't prove where someone is.
    An accuracy of exactly 0 never happens with real GPS and is typical of faked locations."""
    details = {"accuracy_m": round(accuracy_m, 1), "max_accuracy_m": max_accuracy_m}
    if accuracy_m > max_accuracy_m:
        return SignalOutcome("gps_accuracy", SignalResult.FAIL, on_fail, "POOR_ACCURACY", details)
    if accuracy_m == 0:
        return SignalOutcome("gps_accuracy", SignalResult.WARN, on_fail, "ZERO_ACCURACY", details)
    return SignalOutcome("gps_accuracy", SignalResult.PASS, on_fail, None, details)


CLOCK_TOLERANCE_S = 5


def location_age_signal(
    fix_age_ms: int, seconds_since_challenge: float, max_fix_age_s: int, on_fail: PolicyAction
) -> SignalOutcome:
    """The GPS reading must be fresh AND taken after the server issued the challenge - an old
    reading doesn't prove where someone is now, even if its coordinates are inside the office.

    fix_age_ms is measured by the phone between taking the reading and sending it (both on the
    phone's own clock, so changing the phone's time doesn't help). seconds_since_challenge is
    measured by the server.
    """
    fix_age_s = fix_age_ms / 1000
    details = {
        "fix_age_s": round(fix_age_s, 1),
        "max_fix_age_s": max_fix_age_s,
        "seconds_since_challenge": round(seconds_since_challenge, 1),
    }
    if fix_age_s > max_fix_age_s:
        return SignalOutcome("location_age", SignalResult.FAIL, on_fail, "STALE_LOCATION", details)
    if fix_age_s > seconds_since_challenge + CLOCK_TOLERANCE_S:
        details["taken_before_challenge"] = True
        return SignalOutcome("location_age", SignalResult.FAIL, on_fail, "STALE_LOCATION", details)
    return SignalOutcome("location_age", SignalResult.PASS, on_fail, None, details)


def device_signature_signal(has_key: bool, signature_valid: bool) -> SignalOutcome:
    """The request must be signed by the key held in this phone's secure hardware. This is a
    hard rule (always REJECT): an unsigned or wrongly signed request didn't come from the
    approved phone, or was changed after signing."""
    if not has_key:
        return SignalOutcome("device_check", SignalResult.FAIL, PolicyAction.REJECT, "NO_DEVICE_KEY")
    if not signature_valid:
        return SignalOutcome("device_check", SignalResult.FAIL, PolicyAction.REJECT, "BAD_SIGNATURE")
    return SignalOutcome("device_check", SignalResult.PASS)


def mock_location_signal(is_mock: bool, on_fail: PolicyAction) -> SignalOutcome:
    """Android marks locations that come from a 'mock location' app. Many fake-GPS apps are
    caught this way - but NOT all (rooted phones can hide the flag), which is why this is only
    one of several signals."""
    if is_mock:
        return SignalOutcome("mock_location", SignalResult.FAIL, on_fail, "MOCK_LOCATION", {"is_mock": True})
    return SignalOutcome("mock_location", SignalResult.PASS)


def clock_skew_signal(skew_s: float, max_skew_s: int, on_fail: PolicyAction) -> SignalOutcome:
    """Phones set their clock automatically; a big difference from the server suggests the
    clock was changed by hand. The recorded attendance time is always the server's anyway."""
    details = {"skew_s": round(skew_s, 1), "max_skew_s": max_skew_s}
    if abs(skew_s) > max_skew_s:
        return SignalOutcome("timestamp_check", SignalResult.FAIL, on_fail, "CLOCK_SKEW", details)
    return SignalOutcome("timestamp_check", SignalResult.PASS, on_fail, None, details)


def movement_signal(
    distance_m: float | None,
    accuracy_now_m: float,
    accuracy_before_m: float,
    seconds_between: float,
    max_speed_kmh: int,
    on_fail: PolicyAction,
) -> SignalOutcome:
    """Impossible movement: compared with the employee's previous accepted attendance event.
    The GPS uncertainty of both readings is subtracted first, so normal GPS jitter is never
    mistaken for travel. Example: verified in Lagos at 09:00, then Abuja (~530 km) at 09:15
    = ~2,100 km/h -> FAIL."""
    if distance_m is None:
        return SignalOutcome("movement_check", SignalResult.NOT_APPLICABLE)
    travelled_m = max(0.0, distance_m - accuracy_now_m - accuracy_before_m)
    hours = max(seconds_between, 1) / 3600
    speed = travelled_m / 1000 / hours
    details = {
        "distance_km": round(distance_m / 1000, 2),
        "minutes_between": round(seconds_between / 60, 1),
        "implied_speed_kmh": round(speed),
        "max_speed_kmh": max_speed_kmh,
    }
    if speed > max_speed_kmh:
        return SignalOutcome("movement_check", SignalResult.FAIL, on_fail, "IMPOSSIBLE_TRAVEL", details)
    return SignalOutcome("movement_check", SignalResult.PASS, on_fail, None, details)
