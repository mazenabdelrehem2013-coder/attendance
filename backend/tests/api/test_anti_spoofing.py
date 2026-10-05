"""Phase 8 end to end: phone signatures, mock location, impossible movement, Play Integrity,
rotating QR codes, and the security events HR sees."""

import uuid

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import AttendancePolicy, SecurityEvent, VerificationSignal
from app.models.enums import AttendanceAction, PolicyAction, VerificationMode
from app.schemas.attendance import AttendanceSubmission
from app.services.attendance import integrity
from app.services.attendance.canonical import canonical_payload, request_hash
from app.services.attendance.integrity import IntegrityUnavailable
from tests.api.attendance_helpers import (  # noqa: F401  (fixtures)
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

ABUJA = (9.056300, 7.498500)


def security_events(session_factory, employee_id, event_type) -> int:
    with session_factory() as db:
        return db.scalar(select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.employee_id == employee_id, SecurityEvent.event_type == event_type))


def set_policy(session_factory, world, location="lagos_id", **fields):
    with session_factory.begin() as db:
        db.add(AttendancePolicy(organization_id=world.org_id, location_id=getattr(world, location), **fields))


def post(client, world, who, body, action="CHECK_IN"):
    path = "check-in" if action == "CHECK_IN" else "check-out"
    return client.post(f"/api/v1/attendance/{path}", headers=world.h(who), json=body).json()


# --- Phone signatures -----------------------------------------------------------------------


def test_unsigned_request_is_rejected(client, world, ann_phone, test_session_factory):
    body = attempt(client, world, "ann", ann_phone, signature="bm90LWEtc2lnbmF0dXJl").json()
    assert body["result"] == "REJECTED"
    assert body["message"] == "We couldn't verify this attendance. Please contact HR."
    assert security_events(test_session_factory, world.ids["ann"], "BAD_SIGNATURE") == 1


def test_stolen_login_used_from_another_phone_is_rejected(client, world, ann_phone):
    # The attacker has ann's token and her device id, but not the key inside her phone.
    body = attempt(client, world, "ann", ann_phone, signing_key=new_key()).json()
    assert body["result"] == "REJECTED"


def test_request_changed_after_signing_is_rejected(client, world, ann_phone):
    challenge = get_challenge(client, world, "ann", ann_phone).json()
    body = build_body(ann_phone, "CHECK_IN", challenge, (6.50, 3.50))  # signed far away...
    body["latitude"], body["longitude"] = INSIDE_LAGOS  # ...then moved "into" the office
    assert post(client, world, "ann", body)["result"] == "REJECTED"


def test_invalid_public_key_is_refused_at_registration(client, world):
    r = client.post("/api/v1/devices/register", headers=world.h("ann"), json={
        "device_fingerprint": fingerprint(), "install_id": uuid.uuid4().hex, "public_key": "bm90LWEta2V5"})
    assert r.status_code == 422


def test_new_key_on_an_approved_phone_needs_hr_approval_again(client, world, test_session_factory):
    fp = fingerprint()
    old = register(client, world, "ann", fp)
    client.post(f"/api/v1/devices/{old['id']}/approve", headers=world.h("hr"))
    new = register(client, world, "ann", fp)  # same phone, different key (reinstall or imposter)
    assert new["id"] != old["id"] and new["status"] == "PENDING_APPROVAL"
    statuses = {d["id"]: d["status"] for d in client.get("/api/v1/devices/me", headers=world.h("ann")).json()}
    assert statuses[old["id"]] == "REREGISTRATION_REQUIRED"
    assert get_challenge(client, world, "ann", old["id"]).status_code == 403
    client.post(f"/api/v1/devices/{new['id']}/approve", headers=world.h("hr"))
    assert attempt(client, world, "ann", new["id"]).json()["result"] == "ACCEPTED"


# --- Mock location --------------------------------------------------------------------------


def test_mock_location_is_flagged(client, world, ann_phone, test_session_factory):
    body = attempt(client, world, "ann", ann_phone, is_mock_location=True).json()
    assert body["result"] == "FLAGGED"
    assert security_events(test_session_factory, world.ids["ann"], "MOCK_LOCATION") == 1


def test_mock_location_rejected_without_revealing_why(client, world, ann_phone, test_session_factory):
    set_policy(test_session_factory, world, on_mock_location=PolicyAction.REJECT)
    body = attempt(client, world, "ann", ann_phone, is_mock_location=True).json()
    assert body["result"] == "REJECTED"
    assert "mock" not in body["message"].lower() and "fake" not in body["message"].lower()


# --- Clock ----------------------------------------------------------------------------------


def test_phone_clock_a_few_minutes_off_is_fine(client, world, ann_phone, set_time):
    from datetime import timedelta

    from app.core import clock
    body = attempt(client, world, "ann", ann_phone,
                   device_time=(clock.now() + timedelta(minutes=4)).isoformat()).json()
    assert body["result"] == "ACCEPTED"


# --- Impossible movement --------------------------------------------------------------------


@pytest.fixture
def two_office_ann(client, world):
    client.put(f"/api/v1/employees/{world.ids['ann']}/locations", headers=world.h("hr"),
               json={"location_ids": [str(world.lagos_id), str(world.abuja_id)]})
    return approved_device(client, world, "ann")


def test_lagos_then_abuja_15_minutes_later_is_flagged(client, world, two_office_ann, set_time,
                                                     test_session_factory):
    set_time(9, 0)
    assert attempt(client, world, "ann", two_office_ann).json()["result"] == "ACCEPTED"
    set_time(9, 5)
    attempt(client, world, "ann", two_office_ann, action="CHECK_OUT")
    set_time(9, 15)
    body = attempt(client, world, "ann", two_office_ann, at=ABUJA).json()
    assert body["result"] == "FLAGGED"
    assert security_events(test_session_factory, world.ids["ann"], "IMPOSSIBLE_TRAVEL") == 1


def test_lagos_then_abuja_after_a_flight_is_fine(client, world, two_office_ann, set_time):
    set_time(7, 0)
    attempt(client, world, "ann", two_office_ann)
    set_time(7, 5)
    attempt(client, world, "ann", two_office_ann, action="CHECK_OUT")
    set_time(11, 30)  # 530 km in 4.4 hours
    assert attempt(client, world, "ann", two_office_ann, at=ABUJA).json()["result"] == "ACCEPTED"


# --- Play Integrity -------------------------------------------------------------------------


class FakeGoogle:
    """Stands in for Google's decodeIntegrityToken endpoint."""

    def __init__(self, app="PLAY_RECOGNIZED", device=("MEETS_DEVICE_INTEGRITY",), down=False):
        self.app, self.device, self.down = app, list(device), down

    def decode(self, token: str) -> dict:
        if self.down:
            raise IntegrityUnavailable("Google unreachable")
        from app.core import clock
        hash_ = token.removeprefix("fake-token-for:")
        return {
            "requestDetails": {"requestPackageName": get_settings().play_integrity_package_name,
                               "requestHash": hash_,
                               "timestampMillis": str(int(clock.now().timestamp() * 1000))},
            "appIntegrity": {"appRecognitionVerdict": self.app},
            "deviceIntegrity": {"deviceRecognitionVerdict": self.device},
        }


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setattr(get_settings(), "play_integrity_mode", "google")

    def _use(fake):
        monkeypatch.setattr(integrity, "get_verifier", lambda: fake)
    _use(FakeGoogle())
    return _use


def integrity_body(client, world, phone, token_for=None):
    challenge = get_challenge(client, world, "ann", phone).json()
    body = build_body(phone, "CHECK_IN", challenge)
    parsed = AttendanceSubmission(**body)
    real_hash = request_hash(canonical_payload(AttendanceAction.CHECK_IN, parsed))
    body["integrity_token"] = f"fake-token-for:{token_for or real_hash}"
    return body


def test_genuine_app_and_phone_pass_integrity(client, world, ann_phone, google):
    assert post(client, world, "ann", integrity_body(client, world, ann_phone))["result"] == "ACCEPTED"


def test_missing_integrity_token_is_flagged(client, world, ann_phone, google, test_session_factory):
    assert attempt(client, world, "ann", ann_phone).json()["result"] == "FLAGGED"
    assert security_events(test_session_factory, world.ids["ann"], "INTEGRITY_FAIL") == 1


def test_rooted_phone_is_flagged(client, world, ann_phone, google):
    google(FakeGoogle(device=()))
    assert post(client, world, "ann", integrity_body(client, world, ann_phone))["result"] == "FLAGGED"


def test_modified_app_is_flagged(client, world, ann_phone, google):
    google(FakeGoogle(app="UNRECOGNIZED_VERSION"))
    assert post(client, world, "ann", integrity_body(client, world, ann_phone))["result"] == "FLAGGED"


def test_integrity_token_from_another_request_is_flagged(client, world, ann_phone, google):
    body = integrity_body(client, world, ann_phone, token_for="c" * 64)
    assert post(client, world, "ann", body)["result"] == "FLAGGED"


def test_google_outage_does_not_punish_the_employee(client, world, ann_phone, google):
    google(FakeGoogle(down=True))
    assert post(client, world, "ann", integrity_body(client, world, ann_phone))["result"] == "ACCEPTED"


# --- Rotating QR ----------------------------------------------------------------------------


@pytest.fixture
def lagos_screen(client, world, test_session_factory):
    r = client.post("/api/v1/qr-displays", headers=world.h("hr"),
                    json={"location_id": str(world.lagos_id), "display_label": "Reception"})
    assert r.status_code == 201, r.text
    set_policy(test_session_factory, world, verification_mode=VerificationMode.GPS_QR)
    return r.json()


def screen_code(client, display_key):
    headers = {"X-Display-Key": display_key} if display_key else {}
    return client.get("/api/v1/qr/current", headers=headers)


def test_only_hr_registers_screens(client, world):
    body = {"location_id": str(world.lagos_id), "display_label": "X"}
    assert client.post("/api/v1/qr-displays", headers=world.h("ann"), json=body).status_code == 403
    assert client.post("/api/v1/qr-displays", headers=world.h("mgr_a"), json=body).status_code == 403


def test_screen_needs_its_key(client, world, lagos_screen):
    assert screen_code(client, None).status_code == 401
    assert screen_code(client, "qrd_wrong").status_code == 401
    r = screen_code(client, lagos_screen["display_key"])
    assert r.status_code == 200 and r.json()["location_name"] == "Lagos"
    assert r.json()["token"].startswith("Q1.")


def test_code_changes_every_30_seconds(client, world, lagos_screen, set_time):
    first = screen_code(client, lagos_screen["display_key"]).json()["token"]
    set_time.advance(seconds=30)
    assert screen_code(client, lagos_screen["display_key"]).json()["token"] != first


def test_qr_required_and_missing_is_flagged(client, world, ann_phone, lagos_screen, test_session_factory):
    assert attempt(client, world, "ann", ann_phone).json()["result"] == "FLAGGED"
    assert security_events(test_session_factory, world.ids["ann"], "QR_MISSING") == 1


def test_valid_qr_is_accepted_and_recorded(client, world, ann_phone, lagos_screen, test_session_factory):
    token = screen_code(client, lagos_screen["display_key"]).json()["token"]
    body = attempt(client, world, "ann", ann_phone, qr_token=token).json()
    assert body["result"] == "ACCEPTED"
    with test_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(VerificationSignal)) >= 1


def test_shared_photo_of_the_code_expires(client, world, ann_phone, lagos_screen, set_time):
    token = screen_code(client, lagos_screen["display_key"]).json()["token"]
    set_time.advance(seconds=61)  # two windows later
    assert attempt(client, world, "ann", ann_phone, qr_token=token).json()["result"] == "FLAGGED"


def test_code_scanned_a_few_seconds_before_rotation_still_works(client, world, ann_phone, lagos_screen, set_time):
    token = screen_code(client, lagos_screen["display_key"]).json()["token"]
    set_time.advance(seconds=31)  # the next window: previous code still accepted
    assert attempt(client, world, "ann", ann_phone, qr_token=token).json()["result"] == "ACCEPTED"


def test_forged_code_is_flagged(client, world, ann_phone, lagos_screen, test_session_factory):
    token = screen_code(client, lagos_screen["display_key"]).json()["token"]
    forged = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    assert attempt(client, world, "ann", ann_phone, qr_token=forged).json()["result"] == "FLAGGED"
    assert security_events(test_session_factory, world.ids["ann"], "QR_INVALID") == 1


def test_code_from_an_office_the_employee_is_not_assigned_to(client, world, ann_phone, lagos_screen):
    abuja = client.post("/api/v1/qr-displays", headers=world.h("hr"),
                        json={"location_id": str(world.abuja_id), "display_label": "Abuja"}).json()
    token = screen_code(client, abuja["display_key"]).json()["token"]
    assert attempt(client, world, "ann", ann_phone, qr_token=token).json()["result"] == "FLAGGED"


def test_rotating_the_screen_key_invalidates_old_key_and_codes(client, world, ann_phone, lagos_screen):
    old_token = screen_code(client, lagos_screen["display_key"]).json()["token"]
    r = client.post(f"/api/v1/qr-displays/{lagos_screen['id']}/rotate-key", headers=world.h("hr"))
    new_key_ = r.json()["display_key"]
    assert screen_code(client, lagos_screen["display_key"]).status_code == 401
    assert attempt(client, world, "ann", ann_phone, qr_token=old_token).json()["result"] == "FLAGGED"
    attempt(client, world, "ann", ann_phone, action="CHECK_OUT")
    new_token = screen_code(client, new_key_).json()["token"]
    assert attempt(client, world, "ann", ann_phone, qr_token=new_token).json()["result"] == "ACCEPTED"


def test_disabled_screen(client, world, ann_phone, lagos_screen):
    token = screen_code(client, lagos_screen["display_key"]).json()["token"]
    client.post(f"/api/v1/qr-displays/{lagos_screen['id']}/disable", headers=world.h("hr"))
    assert screen_code(client, lagos_screen["display_key"]).status_code == 401
    assert attempt(client, world, "ann", ann_phone, qr_token=token).json()["result"] == "FLAGGED"


def test_gps_still_required_with_a_valid_code(client, world, ann_phone, lagos_screen):
    # A colleague sends a live photo of the code, but the phone is 850 m away.
    token = screen_code(client, lagos_screen["display_key"]).json()["token"]
    body = attempt(client, world, "ann", ann_phone, qr_token=token, at=(6.435750, 3.421900)).json()
    assert body["result"] == "FLAGGED"


# --- All together ---------------------------------------------------------------------------


def test_everything_genuine_passes_every_check(client, world, ann_phone, lagos_screen, google,
                                               test_session_factory):
    from app.models import AttendanceVerification
    token = screen_code(client, lagos_screen["display_key"]).json()["token"]
    challenge = get_challenge(client, world, "ann", ann_phone).json()
    body = build_body(ann_phone, "CHECK_IN", challenge, qr_token=token)
    h = request_hash(canonical_payload(AttendanceAction.CHECK_IN, AttendanceSubmission(**body)))
    body["integrity_token"] = f"fake-token-for:{h}"
    result = post(client, world, "ann", body)
    assert result["result"] == "ACCEPTED", result
    with test_session_factory() as db:
        v = db.scalar(select(AttendanceVerification).where(
            AttendanceVerification.event_id == uuid.UUID(result["event_id"])))
    checks = ["replay_check", "device_check", "geofence", "gps_accuracy", "location_age",
              "mock_location", "play_integrity", "timestamp_check", "qr_check"]
    assert {c: getattr(v, c).value for c in checks} == {c: "PASS" for c in checks}
    assert v.movement_check.value == "NOT_APPLICABLE"  # first event of the day
    assert v.risk_score == 0


def test_app_is_told_when_qr_is_required(client, world, test_session_factory):
    assert client.get("/api/v1/attendance/today", headers=world.h("ann")).json()["qr_required"] is False
    set_policy(test_session_factory, world, verification_mode=VerificationMode.GPS_QR)
    assert client.get("/api/v1/attendance/today", headers=world.h("ann")).json()["qr_required"] is True
    assert client.get("/api/v1/attendance/today", headers=world.h("cal")).json()["qr_required"] is False
