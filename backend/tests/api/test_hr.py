"""Phase 12A: HR review of flagged attendance, HR overview/trend, security events, policies."""

from sqlalchemy import select

from app.models import AttendanceEvent, AuditLog
from tests.api.attendance_helpers import (  # noqa: F401  (fixtures)
    approved_device,
    attempt,
    set_time,
)

OUTSIDE = (6.435750, 3.421900)  # ~850 m from the Lagos office


def flagged_check_in(client, world, who="ann", hh=9, mm=0, set_time=None):
    phone = approved_device(client, world, who)
    if set_time:
        set_time(hh, mm)
    body = attempt(client, world, who, phone, at=OUTSIDE).json()
    assert body["result"] == "FLAGGED"
    return phone, body["event_id"]


def queue(client, world, **params):
    r = client.get("/api/v1/hr/review", headers=world.h("hr"), params=params)
    assert r.status_code == 200, r.text
    return r.json()


def review(client, world, event_id, decision, note=None, who="hr"):
    return client.post(f"/api/v1/hr/review/{event_id}", headers=world.h(who),
                       json={"decision": decision, "note": note})


def today_status(client, world, who="ann"):
    return client.get("/api/v1/attendance/today", headers=world.h(who)).json()


# --- Review queue ---------------------------------------------------------------------------


def test_flagged_attempt_appears_in_queue_with_the_real_reason(client, world, set_time):
    _, event_id = flagged_check_in(client, world, set_time=set_time)
    items = queue(client, world)["items"]
    item = next(i for i in items if i["event_id"] == event_id)
    assert item["employee_name"] == "Ann" and item["reason_code"] == "OUTSIDE_LOCATION"
    assert "geofence" in item["failed_checks"] and item["distance_m"] > 800

    detail = client.get(f"/api/v1/hr/review/{event_id}", headers=world.h("hr")).json()
    assert detail["checks"]["geofence"] == "FAIL" and detail["checks"]["device_check"] == "PASS"
    assert detail["details"]["geofence"]["radius_m"] == 200
    assert detail["policy"]["on_outside_geofence"] == "FLAG"
    assert detail["device_model"] == "Pixel 8"
    assert any(s["type"] == "OUTSIDE_GEOFENCE" for s in detail["security_events"])


def test_approving_a_flagged_check_in_makes_it_count(client, world, set_time, test_session_factory):
    phone, event_id = flagged_check_in(client, world, set_time=set_time)
    assert today_status(client, world)["attendance"]["day_status"] == "PENDING_REVIEW"

    r = review(client, world, event_id, "APPROVED", "Was at a client visit")
    assert r.status_code == 200 and r.json()["review_decision"] == "APPROVED"
    day = today_status(client, world)["attendance"]
    assert day["day_status"] == "PRESENT"  # original time 09:00 counts
    assert day["verification_status"] == "VERIFIED"

    set_time(17, 0)
    attempt(client, world, "ann", phone, action="CHECK_OUT")
    assert today_status(client, world)["attendance"]["worked_minutes"] == 8 * 60
    assert queue(client, world)["total"] == 0
    with test_session_factory() as db:
        entry = db.scalar(select(AuditLog).where(AuditLog.action == "ATTENDANCE_EVENT_REVIEWED"))
        assert entry.new_value["decision"] == "APPROVED" and entry.actor_role == "HR"


def test_rejecting_a_flagged_check_in_means_it_never_counts(client, world, set_time):
    phone, event_id = flagged_check_in(client, world, set_time=set_time)
    assert review(client, world, event_id, "REJECTED", "Not at the office").status_code == 200
    today = today_status(client, world)
    assert today["attendance"]["day_status"] is None
    assert today["state"] == "CHECKED_OUT"  # the rejected session is closed; the person may check in again
    assert attempt(client, world, "ann", phone).json()["result"] == "ACCEPTED"


def test_rejecting_a_flagged_check_out_keeps_arrival_but_not_hours(client, world, set_time):
    phone = approved_device(client, world, "ann")
    set_time(9, 0)
    attempt(client, world, "ann", phone)
    set_time(18, 0)
    out = attempt(client, world, "ann", phone, action="CHECK_OUT", at=OUTSIDE).json()
    assert out["result"] == "FLAGGED"
    review(client, world, out["event_id"], "REJECTED", "Left from home")
    day = today_status(client, world)["attendance"]
    assert day["day_status"] == "PRESENT"
    assert day["worked_minutes"] == 0 and day["departure_status"] == "MISSING_CHECKOUT"


def test_rejection_needs_a_reason(client, world, set_time):
    _, event_id = flagged_check_in(client, world, set_time=set_time)
    assert review(client, world, event_id, "REJECTED").status_code == 422


def test_each_attempt_is_reviewed_only_once(client, world, set_time):
    _, event_id = flagged_check_in(client, world, set_time=set_time)
    assert review(client, world, event_id, "APPROVED").status_code == 200
    assert review(client, world, event_id, "REJECTED", "changed my mind").status_code == 409


def test_accepted_attempts_are_not_reviewable(client, world, set_time):
    phone = approved_device(client, world, "ann")
    event_id = attempt(client, world, "ann", phone).json()["event_id"]
    assert review(client, world, event_id, "APPROVED").status_code == 409


def test_hr_cannot_review_their_own_attendance(client, world, set_time):
    _, event_id = flagged_check_in(client, world, who="hr", set_time=set_time)
    assert review(client, world, event_id, "APPROVED").status_code == 403
    assert review(client, world, event_id, "APPROVED", who="admin").status_code == 200


def test_managers_and_employees_cannot_review(client, world, set_time):
    _, event_id = flagged_check_in(client, world, set_time=set_time)
    for who in ("mgr_a", "ann"):
        assert review(client, world, event_id, "APPROVED", who=who).status_code == 403
        assert client.get("/api/v1/hr/review", headers=world.h(who)).status_code == 403


def test_reviewed_and_rejected_lists(client, world, set_time, test_session_factory):
    _, event_id = flagged_check_in(client, world, set_time=set_time)
    review(client, world, event_id, "APPROVED")
    reviewed = queue(client, world, state="REVIEWED")["items"]
    assert reviewed[0]["reviewed_by"] == world.users["hr"]
    ben = approved_device(client, world, "ben")
    attempt(client, world, "ben", ben, action="CHECK_OUT")  # not checked in -> REJECTED
    rejected = queue(client, world, state="REJECTED_ATTEMPTS")["items"]
    assert [i["reason_code"] for i in rejected] == ["NOT_CHECKED_IN"]


def test_attendance_events_stay_unchanged_after_review(client, world, set_time, test_session_factory):
    _, event_id = flagged_check_in(client, world, set_time=set_time)
    review(client, world, event_id, "APPROVED")
    with test_session_factory() as db:
        assert db.scalar(select(AttendanceEvent.result).where(AttendanceEvent.id == event_id)).value == "FLAGGED"


# --- Overview & trend -----------------------------------------------------------------------


def test_overview_numbers(client, world, set_time):
    ann = approved_device(client, world, "ann")
    set_time(9, 0)
    attempt(client, world, "ann", ann)
    flagged_check_in(client, world, who="ben")
    set_time(19, 0)
    data = client.get("/api/v1/hr/overview", headers=world.h("hr"), params={"date": "2026-10-05"}).json()
    s = data["summary"]
    assert s["total_employees"] == 6 and s["present"] == 1 and s["suspicious"] == 1
    assert data["suspicious_attempts"] == 1 and data["pending_reviews_total"] == 1
    lagos = next(g for g in data["by_location"] if g["name"] == "Lagos")
    assert lagos["present"] == 1 and lagos["pending_review"] == 1
    assert {g["name"] for g in data["by_department"]} == {"Ops"}


def test_trend(client, world, set_time):
    ann = approved_device(client, world, "ann")
    set_time(9, 0)
    attempt(client, world, "ann", ann)
    set_time(12, 0, day=(2026, 10, 6))
    points = client.get("/api/v1/hr/trend", headers=world.h("hr"),
                        params={"from": "2026-10-04", "to": "2026-10-05"}).json()
    assert [p["date"] for p in points] == ["2026-10-04", "2026-10-05"]
    sunday, monday = points
    assert sunday["attendance_rate"] is None  # nobody works on Sunday
    assert monday["present"] == 1 and monday["absent"] == 5
    assert monday["attendance_rate"] == round(1 / 6, 4)
    r = client.get("/api/v1/hr/trend", headers=world.h("hr"), params={"from": "2026-01-01", "to": "2026-10-05"})
    assert r.status_code == 422


def test_overview_is_hr_only(client, world, set_time):
    assert client.get("/api/v1/hr/overview", headers=world.h("mgr_a")).status_code == 403


# --- Security events ------------------------------------------------------------------------


def test_security_events_list(client, world, set_time):
    ann = approved_device(client, world, "ann")
    attempt(client, world, "ann", ann, is_mock_location=True)
    data = client.get("/api/v1/security-events", headers=world.h("hr"),
                      params={"event_type": "MOCK_LOCATION"}).json()
    assert data["total"] == 1
    assert data["items"][0]["employee_name"] == "Ann" and data["items"][0]["severity"] == "HIGH"
    assert client.get("/api/v1/security-events", headers=world.h("mgr_a")).status_code == 403


# --- Policies -------------------------------------------------------------------------------


def test_policies_default_and_per_location(client, world, set_time, test_session_factory):
    data = client.get("/api/v1/settings/attendance-policies", headers=world.h("hr")).json()
    assert data["default"]["on_outside_geofence"] == "FLAG" and data["locations"] == []

    r = client.put(f"/api/v1/settings/attendance-policies/locations/{world.lagos_id}", headers=world.h("hr"),
                   json={"verification_mode": "GPS_QR", "on_outside_geofence": "REJECT"})
    assert r.status_code == 200
    assert r.json()["location_name"] == "Lagos" and r.json()["verification_mode"] == "GPS_QR"

    # The rule is used immediately.
    ann = approved_device(client, world, "ann")
    assert attempt(client, world, "ann", ann, at=OUTSIDE).json()["result"] == "REJECTED"

    with test_session_factory() as db:
        entry = db.scalar(select(AuditLog).where(AuditLog.action == "SECURITY_POLICY_CHANGED")
                          .order_by(AuditLog.seq.desc()))
        assert entry.new_value["on_outside_geofence"] == "REJECT"

    assert client.delete(f"/api/v1/settings/attendance-policies/locations/{world.lagos_id}",
                         headers=world.h("hr")).status_code == 204
    assert client.get("/api/v1/settings/attendance-policies", headers=world.h("hr")).json()["locations"] == []


def test_policy_change_is_audited_with_old_and_new(client, world, test_session_factory):
    client.put("/api/v1/settings/attendance-policies/default", headers=world.h("hr"), json={"max_accuracy_m": 80})
    client.put("/api/v1/settings/attendance-policies/default", headers=world.h("hr"), json={"max_accuracy_m": 60})
    with test_session_factory() as db:
        entry = db.scalar(select(AuditLog).where(AuditLog.action == "SECURITY_POLICY_CHANGED")
                          .order_by(AuditLog.seq.desc()))
        assert entry.old_value == {"max_accuracy_m": 80} and entry.new_value == {"max_accuracy_m": 60}


def test_policy_validation_and_permissions(client, world):
    r = client.put("/api/v1/settings/attendance-policies/default", headers=world.h("hr"), json={"max_accuracy_m": 1})
    assert r.status_code == 422
    r = client.put("/api/v1/settings/attendance-policies/default", headers=world.h("mgr_a"), json={"max_accuracy_m": 50})
    assert r.status_code == 403
