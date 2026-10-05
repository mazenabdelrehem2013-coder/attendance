"""Phase 7: geofence with GPS accuracy, poor accuracy, stale locations - end to end.

Lagos office: 6.428100, 3.421900, radius 200 m. 1 m of latitude = 1/111195 degree.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models import AttendancePolicy, AttendanceVerification
from app.models.enums import PolicyAction
from tests.api.attendance_helpers import approved_device, attempt, get_challenge, set_time  # noqa: F401

OFFICE_LAT, OFFICE_LNG = 6.428100, 3.421900


def north_of_office(meters: float) -> tuple[float, float]:
    return (round(OFFICE_LAT + meters / 111_195, 6), OFFICE_LNG)


@pytest.fixture
def phone(client, world):
    return approved_device(client, world, "ann")


def check(client, world, phone, meters, accuracy=10, fix_age_ms=2000, **kw):
    return attempt(client, world, "ann", phone, at=north_of_office(meters),
                   accuracy_m=accuracy, fix_age_ms=fix_age_ms, **kw).json()


def signals(session_factory, event_id) -> AttendanceVerification:
    with session_factory() as db:
        return db.scalar(select(AttendanceVerification).where(AttendanceVerification.event_id == uuid.UUID(event_id)))


def set_policy(session_factory, world, **fields):
    with session_factory.begin() as db:
        db.add(AttendancePolicy(organization_id=world.org_id, location_id=world.lagos_id, **fields))


# --- Geofence -------------------------------------------------------------------------------


def test_at_the_office_point(client, world, phone, test_session_factory):
    body = check(client, world, phone, 0)
    assert body["result"] == "ACCEPTED" and body["distance_meters"] == 0
    v = signals(test_session_factory, body["event_id"])
    assert (v.geofence.value, v.gps_accuracy.value, v.location_age.value, v.replay_check.value) == (
        "PASS", "PASS", "PASS", "PASS")
    assert v.final_result.value == "ACCEPTED"


def test_inside_near_the_edge(client, world, phone):
    body = check(client, world, phone, 195)
    assert body["result"] == "ACCEPTED" and 190 <= body["distance_meters"] <= 200


def test_just_outside_with_precise_gps_is_flagged(client, world, phone, test_session_factory):
    body = check(client, world, phone, 215, accuracy=5)  # 215 - 5 = 210 > 200
    assert body["result"] == "FLAGGED"
    assert signals(test_session_factory, body["event_id"]).geofence.value == "FAIL"


def test_just_outside_but_within_gps_uncertainty_is_accepted_with_a_warning(client, world, phone,
                                                                            test_session_factory):
    body = check(client, world, phone, 230, accuracy=40)  # could be inside
    assert body["result"] == "ACCEPTED"
    v = signals(test_session_factory, body["event_id"])
    assert v.geofence.value == "WARN" and v.risk_score > 0
    assert v.details["geofence"]["distance_m"] == pytest.approx(230, abs=1)


def test_far_outside(client, world, phone):
    assert check(client, world, phone, 850)["result"] == "FLAGGED"


def test_outside_rejected_by_policy(client, world, phone, test_session_factory):
    set_policy(test_session_factory, world, on_outside_geofence=PolicyAction.REJECT)
    body = check(client, world, phone, 850)
    assert body["result"] == "REJECTED"
    assert body["message"] == "You appear to be outside your assigned work location."


def test_radius_change_takes_effect_immediately(client, world, phone):
    client.put(f"/api/v1/locations/{world.lagos_id}", headers=world.h("hr"), json={"radius_m": 500})
    assert check(client, world, phone, 450)["result"] == "ACCEPTED"


def test_wrong_location_for_this_employee(client, world, phone):
    # ann is assigned only to Lagos; standing at the Abuja office doesn't help.
    body = attempt(client, world, "ann", phone, at=(9.056300, 7.498500)).json()
    assert body["result"] == "FLAGGED"


# --- GPS accuracy ---------------------------------------------------------------------------


def test_poor_accuracy_is_flagged(client, world, phone, test_session_factory):
    body = check(client, world, phone, 20, accuracy=150)
    assert body["result"] == "FLAGGED"
    v = signals(test_session_factory, body["event_id"])
    assert v.gps_accuracy.value == "FAIL"
    assert v.details["gps_accuracy"] == {"accuracy_m": 150.0, "max_accuracy_m": 100}


def test_poor_accuracy_rejected_by_policy_tells_employee_to_retry(client, world, phone,
                                                                  test_session_factory):
    set_policy(test_session_factory, world, on_poor_accuracy=PolicyAction.REJECT)
    body = check(client, world, phone, 20, accuracy=150)
    assert body["result"] == "REJECTED" and body["message_code"] == "WEAK_SIGNAL"
    # They can try again straight away with a better signal.
    assert check(client, world, phone, 20, accuracy=15)["result"] == "ACCEPTED"


def test_accuracy_limit_is_configurable(client, world, phone, test_session_factory):
    set_policy(test_session_factory, world, max_accuracy_m=30)
    assert check(client, world, phone, 20, accuracy=50)["result"] == "FLAGGED"


def test_zero_accuracy_alone_is_accepted_but_recorded(client, world, phone, test_session_factory):
    body = check(client, world, phone, 20, accuracy=0)
    assert body["result"] == "ACCEPTED"
    assert signals(test_session_factory, body["event_id"]).gps_accuracy.value == "WARN"


# --- Location age ---------------------------------------------------------------------------


def test_stale_reading_is_flagged_even_inside_the_office(client, world, phone, test_session_factory):
    body = check(client, world, phone, 10, fix_age_ms=120_000)
    assert body["result"] == "FLAGGED"
    assert signals(test_session_factory, body["event_id"]).location_age.value == "FAIL"


def test_reading_taken_before_the_challenge_is_flagged(client, world, phone, set_time):  # noqa: F811
    challenge = get_challenge(client, world, "ann", phone).json()
    set_time.advance(seconds=10)
    body = attempt(client, world, "ann", phone, challenge=challenge, at=north_of_office(10),
                   fix_age_ms=40_000).json()
    assert body["result"] == "FLAGGED"


def test_stale_reading_rejected_by_policy(client, world, phone, test_session_factory):
    set_policy(test_session_factory, world, on_stale_location=PolicyAction.REJECT)
    body = check(client, world, phone, 10, fix_age_ms=120_000)
    assert body["result"] == "REJECTED" and body["message_code"] == "WEAK_SIGNAL"


# --- Record keeping -------------------------------------------------------------------------


def test_policy_in_force_is_stored_with_the_decision(client, world, phone, test_session_factory):
    set_policy(test_session_factory, world, max_accuracy_m=80, on_poor_accuracy=PolicyAction.REJECT)
    body = check(client, world, phone, 10)
    snapshot = signals(test_session_factory, body["event_id"]).policy_snapshot
    assert snapshot["max_accuracy_m"] == 80 and snapshot["on_poor_accuracy"] == "REJECT"
