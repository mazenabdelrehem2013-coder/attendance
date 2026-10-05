"""Phase 6: phones, challenge, check-in/out, attendance rules, today/history, holidays, leave.

World: Lagos office (6.4281, 3.4219, radius 200 m) and Abuja office; schedule Mon-Sat
09:00-18:00, 15 min grace. ann/ben work in Lagos (manager mgr_a), cal in Abuja (mgr_b).
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.core import clock
from app.models import AttendanceEvent, AttendancePolicy, SecurityEvent
from app.models.enums import PolicyAction
from tests.api.attendance_helpers import (  # noqa: F401  (set_time, ann_phone are fixtures)
    INSIDE_LAGOS,
    ann_phone,
    approved_device,
    attempt,
    build_body,
    fingerprint,
    get_challenge,
    new_key,
    register,
    set_time,
)

LAGOS = (6.428100, 3.421900)
OUTSIDE_LAGOS = (6.435750, 3.421900)  # ~850 m away
ABUJA = (9.056300, 7.498500)


# --- Helpers --------------------------------------------------------------------------------


def security_events(session_factory, employee_id, event_type) -> int:
    with session_factory() as db:
        return db.scalar(select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.employee_id == employee_id, SecurityEvent.event_type == event_type))


# --- Phones ---------------------------------------------------------------------------------


def test_new_phone_needs_hr_approval(client, world, set_time):
    device = register(client, world, "ann")
    assert device["status"] == "PENDING_APPROVAL"
    r = get_challenge(client, world, "ann", device["id"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "DEVICE_PENDING_APPROVAL"

    pending = client.get("/api/v1/devices?status=PENDING_APPROVAL", headers=world.h("hr")).json()
    assert device["id"] in [d["id"] for d in pending["items"]]
    client.post(f"/api/v1/devices/{device['id']}/approve", headers=world.h("hr"))
    assert get_challenge(client, world, "ann", device["id"]).status_code == 200


def test_one_phone_cannot_be_used_by_two_employees(client, world, test_session_factory):
    fp = fingerprint()
    register(client, world, "ann", fp)
    r = register(client, world, "ben", fp, expect=409)
    assert r["error"]["code"] == "DEVICE_IN_USE"
    assert security_events(test_session_factory, world.ids["ben"], "DEVICE_SHARED") == 1


def test_registering_the_same_phone_again_returns_the_same_registration(client, world):
    fp, key = fingerprint(), new_key()
    assert register(client, world, "ann", fp, key)["id"] == register(client, world, "ann", fp, key)["id"]


def test_approving_a_new_phone_deactivates_the_old_one(client, world):
    old = approved_device(client, world, "ann")
    new = approved_device(client, world, "ann")
    statuses = {d["id"]: d["status"] for d in client.get("/api/v1/devices/me", headers=world.h("ann")).json()}
    assert statuses == {old: "DEACTIVATED", new: "ACTIVE"}
    assert get_challenge(client, world, "ann", old).status_code == 403


@pytest.mark.parametrize("who", ["ann", "mgr_a"])
def test_only_hr_approves_phones(client, world, who):
    device = register(client, world, "ann")
    assert client.post(f"/api/v1/devices/{device['id']}/approve", headers=world.h(who)).status_code == 403


def test_someone_elses_phone_cannot_be_used(client, world, ann_phone):
    r = get_challenge(client, world, "ben", ann_phone)
    assert r.status_code == 403 and r.json()["error"]["code"] == "DEVICE_NOT_REGISTERED"


# --- Check-in basics ------------------------------------------------------------------------


def test_check_in_inside_the_office_on_time(client, world, ann_phone, set_time):
    set_time(9, 7)
    r = attempt(client, world, "ann", ann_phone)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["result"] == "ACCEPTED"
    assert body["status"] == "PRESENT"
    assert body["verification_status"] == "VERIFIED"
    assert body["location"] == "Lagos"
    assert 30 <= body["distance_meters"] <= 60
    assert body["message"] == "Check-in successful."
    assert datetime.fromisoformat(body["server_time"]) == clock.now()


def test_check_in_after_grace_is_late(client, world, ann_phone, set_time):
    set_time(9, 25)
    assert attempt(client, world, "ann", ann_phone).json()["status"] == "LATE"


def test_phone_clock_is_ignored_and_a_wrong_clock_is_flagged(client, world, ann_phone, set_time,
                                                               test_session_factory):
    set_time(9, 30)  # really late; the phone pretends it is 07:55
    r = attempt(client, world, "ann", ann_phone, device_time="2026-10-05T07:55:00+01:00")
    assert r.json()["result"] == "FLAGGED"  # clock 95 minutes off -> HR review
    with test_session_factory() as db:
        event = db.get(AttendanceEvent, uuid.UUID(r.json()["event_id"]))
        assert event.server_received_at == clock.now()  # the attendance time is the server's
        assert event.device_reported_at.astimezone(UTC).hour == 6  # kept as evidence only
        assert event.reason_code == "CLOCK_SKEW"


def test_phone_cannot_claim_to_be_inside(client, world, ann_phone):
    r = attempt(client, world, "ann", ann_phone, at=OUTSIDE_LAGOS, isInside=True, signature="x")
    assert r.status_code == 422  # unknown fields are refused outright


def test_outside_the_radius_is_flagged_and_does_not_count(client, world, ann_phone, set_time,
                                                          test_session_factory):
    set_time(9, 5)
    body = attempt(client, world, "ann", ann_phone, at=OUTSIDE_LAGOS).json()
    assert body["result"] == "FLAGGED" and body["success"] is False
    assert body["verification_status"] == "PENDING_REVIEW"
    assert body["status"] == "PENDING_REVIEW"  # not PRESENT until HR approves (decision 11.6)
    assert body["distance_meters"] is None
    assert body["message"] == "Your attendance was recorded and is waiting for HR review."
    assert security_events(test_session_factory, world.ids["ann"], "OUTSIDE_GEOFENCE") == 1


def test_outside_the_radius_rejected_when_policy_says_reject(client, world, ann_phone,
                                                             test_session_factory):
    with test_session_factory.begin() as db:
        db.add(AttendancePolicy(organization_id=world.org_id, location_id=world.lagos_id,
                                on_outside_geofence=PolicyAction.REJECT))
    body = attempt(client, world, "ann", ann_phone, at=OUTSIDE_LAGOS).json()
    assert body["result"] == "REJECTED"
    assert body["attendance_id"] is None
    assert body["message"] == "You appear to be outside your assigned work location."
    today = client.get("/api/v1/attendance/today", headers=world.h("ann")).json()
    assert today["state"] == "NOT_CHECKED_IN"
    assert today["attempts"][0]["result"] == "REJECTED"  # but the attempt is visible


def test_far_away_location_measured_against_nearest_assigned_office(client, world, set_time):
    # cal works in Abuja only; checking in from Lagos is ~530 km away.
    phone = approved_device(client, world, "cal")
    assert attempt(client, world, "cal", phone, at=ABUJA).json()["result"] == "ACCEPTED"
    attempt(client, world, "cal", phone, action="CHECK_OUT", at=ABUJA)
    set_time(9, 30)
    assert attempt(client, world, "cal", phone, at=LAGOS).json()["result"] == "FLAGGED"


def test_employee_with_several_locations_can_use_either(client, world):
    client.put(f"/api/v1/employees/{world.ids['ann']}/locations", headers=world.h("hr"),
               json={"location_ids": [str(world.lagos_id), str(world.abuja_id)]})
    phone = approved_device(client, world, "ann")
    body = attempt(client, world, "ann", phone, at=ABUJA).json()
    assert body["result"] == "ACCEPTED" and body["location"] == "Abuja"


def test_no_assigned_location(client, world, test_session_factory):
    phone = approved_device(client, world, "ann")
    client.put(f"/api/v1/locations/{world.lagos_id}", headers=world.h("hr"), json={"is_active": False})
    body = attempt(client, world, "ann", phone).json()
    assert body["result"] == "REJECTED" and body["message_code"] == "NO_ASSIGNED_LOCATION"


def test_account_without_employee_record_cannot_check_in(client, world):
    r = client.post("/api/v1/attendance/challenge", headers=world.h("admin"),
                    json={"action": "CHECK_IN", "device_id": str(uuid.uuid4())})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NO_EMPLOYEE_RECORD"


# --- Replay & duplicates --------------------------------------------------------------------


def test_reusing_a_challenge_is_rejected_as_replay(client, world, ann_phone, test_session_factory):
    challenge = get_challenge(client, world, "ann", ann_phone).json()
    first = attempt(client, world, "ann", ann_phone, challenge=challenge)
    assert first.json()["result"] == "ACCEPTED"
    attempt(client, world, "ann", ann_phone, action="CHECK_OUT")
    again = attempt(client, world, "ann", ann_phone, challenge=challenge)  # new request id, old challenge
    assert again.json()["result"] == "REJECTED"
    assert again.json()["message_code"] == "REQUEST_EXPIRED"
    assert security_events(test_session_factory, world.ids["ann"], "REPLAY") == 1


def test_retrying_the_same_request_returns_the_same_result(client, world, ann_phone,
                                                           test_session_factory):
    challenge = get_challenge(client, world, "ann", ann_phone).json()
    body = build_body(ann_phone, "CHECK_IN", challenge, INSIDE_LAGOS)
    first = client.post("/api/v1/attendance/check-in", headers=world.h("ann"), json=body).json()
    second = client.post("/api/v1/attendance/check-in", headers=world.h("ann"), json=body).json()
    assert first["event_id"] == second["event_id"] and second["result"] == "ACCEPTED"
    with test_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent).where(
            AttendanceEvent.employee_id == world.ids["ann"])) == 1


def test_expired_challenge_is_rejected(client, world, ann_phone, set_time):
    challenge = get_challenge(client, world, "ann", ann_phone).json()
    set_time.advance(minutes=5)
    body = attempt(client, world, "ann", ann_phone, challenge=challenge).json()
    assert body["result"] == "REJECTED" and body["message_code"] == "REQUEST_EXPIRED"


def test_challenge_for_another_action_or_wrong_nonce_is_rejected(client, world, ann_phone):
    out_challenge = get_challenge(client, world, "ann", ann_phone, "CHECK_OUT").json()
    assert attempt(client, world, "ann", ann_phone, challenge=out_challenge).json()["result"] == "REJECTED"
    challenge = get_challenge(client, world, "ann", ann_phone).json()
    challenge["nonce"] = "x" * 43
    assert attempt(client, world, "ann", ann_phone, challenge=challenge).json()["result"] == "REJECTED"


def test_someone_elses_challenge_cannot_be_used(client, world, ann_phone):
    ben_phone = approved_device(client, world, "ben")
    ben_challenge = get_challenge(client, world, "ben", ben_phone).json()
    body = attempt(client, world, "ann", ann_phone, challenge=ben_challenge).json()
    assert body["result"] == "REJECTED"


# --- Sequence -------------------------------------------------------------------------------


def test_cannot_check_in_twice_or_check_out_without_check_in(client, world, ann_phone):
    out = attempt(client, world, "ann", ann_phone, action="CHECK_OUT").json()
    assert out["result"] == "REJECTED" and out["message_code"] == "NOT_CHECKED_IN"
    assert attempt(client, world, "ann", ann_phone).json()["result"] == "ACCEPTED"
    again = attempt(client, world, "ann", ann_phone).json()
    assert again["result"] == "REJECTED" and again["message_code"] == "ALREADY_CHECKED_IN"


def test_full_day_with_lunch_break(client, world, ann_phone, set_time):
    for hh, mm, action in [(9, 0, "CHECK_IN"), (12, 30, "CHECK_OUT"), (13, 15, "CHECK_IN"), (18, 5, "CHECK_OUT")]:
        set_time(hh, mm)
        assert attempt(client, world, "ann", ann_phone, action=action).json()["result"] == "ACCEPTED"

    today = client.get("/api/v1/attendance/today", headers=world.h("ann")).json()
    assert today["state"] == "CHECKED_OUT"
    day = today["attendance"]
    assert day["worked_minutes"] == 210 + 290
    assert day["arrival_status"] == "PRESENT" and day["departure_status"] == "CHECKED_OUT"
    assert len(day["sessions"]) == 2
    assert len(today["attempts"]) == 4

    history = client.get("/api/v1/attendance/history?from=2026-10-01&to=2026-10-31",
                         headers=world.h("ann")).json()
    assert [d["date"] for d in history] == ["2026-10-05"]


def test_leaving_early(client, world, ann_phone, set_time):
    set_time(9, 0)
    attempt(client, world, "ann", ann_phone)
    set_time(16, 30)
    body = attempt(client, world, "ann", ann_phone, action="CHECK_OUT").json()
    assert body["result"] == "ACCEPTED"
    today = client.get("/api/v1/attendance/today", headers=world.h("ann")).json()
    assert today["attendance"]["departure_status"] == "EARLY_DEPARTURE"


def test_flagged_check_out_keeps_the_day_pending(client, world, ann_phone, set_time):
    set_time(9, 0)
    attempt(client, world, "ann", ann_phone)
    set_time(18, 0)
    assert attempt(client, world, "ann", ann_phone, action="CHECK_OUT", at=OUTSIDE_LAGOS).json()["result"] == "FLAGGED"
    day = client.get("/api/v1/attendance/today", headers=world.h("ann")).json()["attendance"]
    assert day["verification_status"] == "PENDING_REVIEW"
    assert day["worked_minutes"] == 0  # the flagged session doesn't count yet


# --- Today ----------------------------------------------------------------------------------


def test_today_before_any_check_in(client, world, set_time):
    set_time(8, 30)
    today = client.get("/api/v1/attendance/today", headers=world.h("ann")).json()
    assert today["state"] == "NOT_CHECKED_IN" and today["next_action"] == "CHECK_IN"
    assert today["day_type"] == "WORKING_DAY"
    assert today["scheduled_start"] == "09:00:00" and today["scheduled_end"] == "18:00:00"


def test_today_while_checked_in(client, world, ann_phone):
    attempt(client, world, "ann", ann_phone)
    today = client.get("/api/v1/attendance/today", headers=world.h("ann")).json()
    assert today["state"] == "CHECKED_IN" and today["next_action"] == "CHECK_OUT"


def test_sunday_is_not_a_working_day(client, world, set_time):
    set_time(10, 0, day=(2026, 10, 4))
    assert client.get("/api/v1/attendance/today", headers=world.h("ann")).json()["day_type"] == "NON_WORKING_DAY"


def test_saturday_is_a_working_day(client, world, set_time):
    set_time(10, 0, day=(2026, 10, 3))
    assert client.get("/api/v1/attendance/today", headers=world.h("ann")).json()["day_type"] == "WORKING_DAY"


# --- Holidays & leave -----------------------------------------------------------------------


def test_holidays(client, world, set_time):
    body = {"holiday_date": "2026-10-05", "name": "Company Day"}
    assert client.post("/api/v1/holidays", headers=world.h("ann"), json=body).status_code == 403
    created = client.post("/api/v1/holidays", headers=world.h("hr"), json=body)
    assert created.status_code == 201
    assert client.post("/api/v1/holidays", headers=world.h("hr"), json=body).status_code == 409

    today = client.get("/api/v1/attendance/today", headers=world.h("ann")).json()
    assert today["day_type"] == "HOLIDAY" and today["day_description"] == "Company Day"
    assert [h["name"] for h in client.get("/api/v1/holidays?year=2026", headers=world.h("ann")).json()] == ["Company Day"]

    assert client.delete(f"/api/v1/holidays/{created.json()['id']}", headers=world.h("hr")).status_code == 204
    assert client.get("/api/v1/attendance/today", headers=world.h("ann")).json()["day_type"] == "WORKING_DAY"


def test_leave(client, world, set_time):
    body = {"employee_id": str(world.ids["ann"]), "leave_type": "SICK",
            "start_date": "2026-10-05", "end_date": "2026-10-07"}
    assert client.post("/api/v1/leave", headers=world.h("mgr_a"), json=body).status_code == 403
    r = client.post("/api/v1/leave", headers=world.h("hr"), json=body)
    assert r.status_code == 201
    overlap = {**body, "start_date": "2026-10-07", "end_date": "2026-10-09"}
    assert client.post("/api/v1/leave", headers=world.h("hr"), json=overlap).status_code == 409

    today = client.get("/api/v1/attendance/today", headers=world.h("ann")).json()
    assert today["day_type"] == "ON_LEAVE" and today["day_description"] == "SICK"

    # Managers see their own team's leave only; employees their own.
    assert len(client.get("/api/v1/leave", headers=world.h("mgr_a")).json()) == 1
    assert client.get("/api/v1/leave", headers=world.h("mgr_b")).json() == []
    assert len(client.get("/api/v1/leave", headers=world.h("ann")).json()) == 1
    assert client.get("/api/v1/leave", headers=world.h("ben")).json() == []

    cancelled = client.post(f"/api/v1/leave/{r.json()['id']}/cancel", headers=world.h("hr")).json()
    assert cancelled["status"] == "CANCELLED"
    assert client.get("/api/v1/attendance/today", headers=world.h("ann")).json()["day_type"] == "WORKING_DAY"


def test_invalid_leave_range(client, world):
    body = {"employee_id": str(world.ids["ann"]), "leave_type": "ANNUAL",
            "start_date": "2026-10-09", "end_date": "2026-10-05"}
    assert client.post("/api/v1/leave", headers=world.h("hr"), json=body).status_code == 422
