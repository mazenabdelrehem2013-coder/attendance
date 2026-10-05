"""Phase 17: tests for branches the earlier phases didn't reach (found with the coverage report),
concentrating on security-relevant ones."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.core import security
from app.core.config import get_settings
from app.models import ReportRun, ReportSetting
from app.models.enums import ReportRunStatus
from app.services import report_schedules
from app.services.attendance import integrity
from tests.api.attendance_helpers import ann_phone, attempt, build_body, get_challenge, register, set_time  # noqa: F401
from tests.api.conftest import PASSWORD

# --- Login tokens ---------------------------------------------------------------------------


def _token(**overrides) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"iss": s.jwt_issuer, "aud": s.jwt_audience, "sub": str(uuid.uuid4()), "org": str(uuid.uuid4()),
               "role": "HR", "ver": 0, "typ": "access", "iat": now, "nbf": now, "exp": now + timedelta(minutes=5)}
    payload.update(overrides)
    return jwt.encode(payload, s.jwt_secret.get_secret_value(), algorithm="HS256")


def test_secret_rotation_accepts_tokens_signed_with_the_previous_key(monkeypatch):
    s = get_settings()
    old_secret = s.jwt_secret
    token, _ = security.create_access_token(user_id=uuid.uuid4(), organization_id=uuid.uuid4(), role="HR",
                                            token_version=0)
    monkeypatch.setattr(s, "jwt_secret", SecretStr("n" * 40))
    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(token)  # new key only: old tokens are invalid
    monkeypatch.setattr(s, "jwt_previous_secret", old_secret)
    assert security.decode_access_token(token).role == "HR"  # during rotation: still valid


@pytest.mark.parametrize("bad", [
    {"typ": "refresh"},  # a different kind of token
    {"exp": datetime.now(UTC) - timedelta(minutes=1)},  # expired
    {"aud": "someone-else"},
    {"iss": "someone-else"},
])
def test_invalid_tokens_are_refused(bad):
    with pytest.raises(security.InvalidTokenError):
        security.decode_access_token(_token(**bad))


def test_unsigned_token_is_refused(client):
    s = get_settings()
    forged = jwt.encode({"iss": s.jwt_issuer, "aud": s.jwt_audience, "sub": str(uuid.uuid4()), "typ": "access",
                         "ver": 0, "role": "ADMIN", "iat": 0, "exp": 9999999999}, key=None, algorithm="none")
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_short_jwt_secret_is_refused(monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_secret", SecretStr("too-short"))
    with pytest.raises(RuntimeError, match="32 characters"):
        security.create_access_token(user_id=uuid.uuid4(), organization_id=uuid.uuid4(), role="HR", token_version=0)


def test_broken_password_hash_never_matches():
    assert security.verify_password("anything", "not-a-real-hash") is False


# --- Passwords and sessions -----------------------------------------------------------------


def test_change_password_rules(client, world):
    h = world.h("ann")
    wrong = client.post("/api/v1/auth/change-password", headers=h,
                        json={"current_password": "Wrong-Password-1", "new_password": "Another-Good-Pass-9"})
    assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "WRONG_PASSWORD"
    same = client.post("/api/v1/auth/change-password", headers=h,
                       json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert same.status_code == 422


def test_logout_ends_the_session(client, world):
    r = client.post("/api/v1/auth/login", json={"identifier": world.users["ben"], "password": PASSWORD,
                                                 "client_type": "MOBILE"}).json()
    refresh = r["refresh_token"]
    assert client.post("/api/v1/auth/logout", json={"refresh_token": refresh}).status_code in (200, 204)
    again = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert again.status_code == 401
    assert client.post("/api/v1/auth/logout", json={}).status_code in (200, 204, 422)  # nothing to end: no error


# --- Phones ---------------------------------------------------------------------------------


def test_reject_and_deactivate_phones(client, world):
    hr = world.h("hr")
    pending = register(client, world, "ben")
    r = client.post(f"/api/v1/devices/{pending['id']}/reject", headers=hr, json={"note": "Not a company phone"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    assert client.post(f"/api/v1/devices/{pending['id']}/approve", headers=hr).status_code == 409  # already decided

    second = register(client, world, "ben")
    client.post(f"/api/v1/devices/{second['id']}/approve", headers=hr)
    off = client.post(f"/api/v1/devices/{second['id']}/deactivate", headers=hr, json={"note": "Phone lost"})
    assert off.status_code == 200 and off.json()["status"] == "DEACTIVATED"
    assert client.post(f"/api/v1/devices/{uuid.uuid4()}/approve", headers=hr).status_code == 404
    assert client.post(f"/api/v1/devices/{second['id']}/approve", headers=world.h("mgr_a")).status_code == 403


# --- Attendance -----------------------------------------------------------------------------


def test_request_id_cannot_be_reused_for_another_action(client, world, ann_phone):
    challenge = get_challenge(client, world, "ann", ann_phone).json()
    body = build_body(ann_phone, "CHECK_IN", challenge)
    assert client.post("/api/v1/attendance/check-in", headers=world.h("ann"), json=body).json()["result"] == "ACCEPTED"
    out_challenge = get_challenge(client, world, "ann", ann_phone, "CHECK_OUT").json()
    reused = build_body(ann_phone, "CHECK_OUT", out_challenge, client_request_id=body["client_request_id"])
    r = client.post("/api/v1/attendance/check-out", headers=world.h("ann"), json=reused)
    assert r.status_code == 409 and r.json()["error"]["code"] == "DUPLICATE_REQUEST"


# --- Employees ------------------------------------------------------------------------------


def test_employee_update_conflicts(client, world):
    hr = world.h("hr")
    dup = client.put(f"/api/v1/employees/{world.ids['ben']}", headers=hr, json={"email": world.users["ann"]})
    assert dup.status_code == 409
    other_org_dept = str(uuid.uuid4())
    r = client.put(f"/api/v1/employees/{world.ids['ben']}", headers=hr, json={"department_id": other_org_dept})
    assert r.status_code == 404


# --- Google Play Integrity (network calls replaced) -----------------------------------------


class _Creds:
    valid, token = False, "t"

    def refresh(self, request):
        self.valid = True


class _Response:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body


@pytest.fixture
def google(monkeypatch):
    import google.auth
    import requests

    calls = {}
    monkeypatch.setattr(google.auth, "default", lambda scopes: (_Creds(), "project"))

    def post(url, json, headers, timeout):
        calls.update(url=url, json=json, headers=headers)
        if isinstance(calls.get("answer"), Exception):
            raise calls["answer"]
        return calls["answer"]

    monkeypatch.setattr(requests, "post", post)
    return calls


def test_google_integrity_decoding(google):
    v = integrity.GooglePlayIntegrityVerifier("com.example.attendance")
    google["answer"] = _Response(200, {"tokenPayloadExternal": {"appIntegrity": {"appRecognitionVerdict": "PLAY_RECOGNIZED"}}})
    assert v.decode("abc")["appIntegrity"]["appRecognitionVerdict"] == "PLAY_RECOGNIZED"
    assert google["url"].endswith("com.example.attendance:decodeIntegrityToken")
    assert google["headers"]["Authorization"] == "Bearer t" and google["json"] == {"integrityToken": "abc"}

    google["answer"] = _Response(400)
    assert v.decode("forged") == {}  # Google: invalid token -> treated as a failed check
    google["answer"] = _Response(503)
    with pytest.raises(integrity.IntegrityUnavailable):
        v.decode("abc")
    google["answer"] = ConnectionError("no network")
    with pytest.raises(integrity.IntegrityUnavailable):
        v.decode("abc")


# --- Scheduled reports ----------------------------------------------------------------------


def test_a_broken_schedule_is_recorded_and_does_not_retry_every_minute(client, world, set_time, test_session_factory,
                                                                        monkeypatch):
    client.post("/api/v1/hr/report-schedules", headers=world.h("hr"), json={
        "name": "Breaks", "report": "weekly", "frequency": "weekly", "time": "08:00", "weekday": 0,
        "formats": ["PDF"], "recipient_roles": ["HR"]})

    def boom(db, s, fire):
        raise RuntimeError("disk full")

    monkeypatch.setattr(report_schedules, "_create", boom)
    set_time(8, 5, day=(2026, 10, 12))
    report_schedules.run_due(test_session_factory)
    report_schedules.run_due(test_session_factory)
    with test_session_factory() as db:
        s = db.scalar(select(ReportSetting).where(ReportSetting.organization_id == world.org_id))
        runs = list(db.scalars(select(ReportRun).where(ReportRun.report_setting_id == s.id)))
        assert [(r.status, r.error_message) for r in runs] == [(ReportRunStatus.FAILED, "disk full")]
        assert s.last_scheduled_for is not None


def test_new_office_assignment_starts_today_at_that_office(client, world, set_time, test_session_factory):
    from decimal import Decimal

    from app.models import EmployeeLocation, Location

    with test_session_factory.begin() as db:
        ny = Location(organization_id=world.org_id, branch_id=world.branch_id, name="New York", code="NYC",
                      latitude=Decimal("40.7128"), longitude=Decimal("-74.0060"), timezone="America/New_York",
                      work_schedule_id=world.schedule_id)
        db.add(ny)
        db.flush()
        ny_id = ny.id
    set_time(1, 0, day=(2026, 10, 6))  # Lagos 01:00 on the 6th = New York 20:00 on the 5th
    r = client.put(f"/api/v1/employees/{world.ids['ann']}/locations", headers=world.h("hr"),
                   json={"location_ids": [str(ny_id), str(world.lagos_id)]})
    assert r.status_code == 200, r.text
    with test_session_factory() as db:
        starts = {link.location_id: link.valid_from for link in db.scalars(
            select(EmployeeLocation).where(EmployeeLocation.employee_id == world.ids["ann"]))}
    assert str(starts[ny_id]) == "2026-10-05" and str(starts[world.lagos_id]) == "2026-10-06"
