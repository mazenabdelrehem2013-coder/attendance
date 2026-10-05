"""Authentication & authorization tests (Phase 4)."""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import get_current_user, require_roles
from app.core.config import get_settings
from app.main import create_app
from app.models import RefreshToken, SecurityEvent, User
from app.models.enums import EmploymentStatus, Role
from tests.api.conftest import PASSWORD, auth_header, login

# --- Login ----------------------------------------------------------------------------------


def test_login_with_email(client, make_user):
    user = make_user()
    r = login(client, user)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().access_token_minutes * 60
    assert body["refresh_token"]
    assert body["user"]["email"] == user.email
    assert body["user"]["employee"]["employee_code"] == user.employee_code


def test_login_with_employee_id_any_case(client, make_user):
    user = make_user()
    r = client.post(
        "/api/v1/auth/login",
        json={"identifier": f"  {user.employee_code.lower()} ", "password": PASSWORD},
    )
    assert r.status_code == 200


def test_wrong_password_and_unknown_user_get_the_same_answer(client, make_user):
    user = make_user()
    wrong = client.post("/api/v1/auth/login", json={"identifier": user.email, "password": "nope"})
    unknown = client.post(
        "/api/v1/auth/login", json={"identifier": "nobody@example.com", "password": "nope"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_deactivated_user_cannot_log_in(client, make_user):
    user = make_user(is_active=False)
    assert login(client, user).status_code == 401


def test_terminated_employee_cannot_log_in(client, make_user):
    user = make_user(employment_status=EmploymentStatus.TERMINATED)
    assert login(client, user).status_code == 401


def test_account_locks_after_repeated_failures(client, make_user, test_session_factory):
    user = make_user()
    attempts = get_settings().max_failed_logins
    for _ in range(attempts):
        r = client.post("/api/v1/auth/login", json={"identifier": user.email, "password": "bad"})
        assert r.status_code == 401
    # Now even the correct password is refused until the lock expires.
    r = login(client, user)
    assert r.status_code == 423
    assert r.json()["error"]["code"] == "ACCOUNT_LOCKED"
    with test_session_factory() as db:
        events = db.scalar(
            select(func.count()).select_from(SecurityEvent).where(
                SecurityEvent.user_id == user.id, SecurityEvent.event_type == "LOGIN_FAILED"
            )
        )
    assert events == attempts


def test_lock_expires(client, make_user, test_session_factory):
    user = make_user()
    with test_session_factory.begin() as db:
        db.get(User, user.id).locked_until = datetime.now(UTC) - timedelta(seconds=1)
    assert login(client, user).status_code == 200


def test_ip_with_many_failures_is_throttled(migrated_test_db, make_user):
    client = TestClient(create_app(), raise_server_exceptions=False, client=("10.9.8.7", 5000))
    for i in range(get_settings().ip_failed_login_limit):
        client.post("/api/v1/auth/login", json={"identifier": f"x{i}@example.com", "password": "x"})
    user = make_user()
    r = login(client, user)
    assert r.status_code == 429
    # Other IP addresses are not affected.
    other = TestClient(create_app(), raise_server_exceptions=False, client=("10.1.1.1", 5000))
    assert login(other, user).status_code == 200


def test_login_input_is_validated(client):
    r = client.post("/api/v1/auth/login", json={"identifier": "", "password": "x"})
    assert r.status_code == 422


# --- Access tokens ----------------------------------------------------------------------------


def test_me_requires_a_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "NOT_AUTHENTICATED"


def test_me_returns_current_user(client, make_user):
    user = make_user(Role.HR)
    token = login(client, user).json()["access_token"]
    r = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert r.status_code == 200
    assert r.json()["role"] == "HR"


def test_garbage_token_is_rejected(client):
    r = client.get("/api/v1/auth/me", headers=auth_header("not.a.jwt"))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_TOKEN"


def _forge(user, *, secret=None, algorithm="HS256", **overrides):
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "iss": s.jwt_issuer, "aud": s.jwt_audience, "sub": str(user.id),
        "org": str(user.organization_id), "role": "ADMIN", "ver": 1, "typ": "access",
        "jti": "x", "iat": now, "nbf": now, "exp": now + timedelta(minutes=5),
    }
    payload.update(overrides)
    key = secret if secret is not None else s.jwt_secret.get_secret_value()
    return jwt.encode(payload, key, algorithm=algorithm)


def test_expired_token_is_rejected(client, make_user):
    user = make_user(Role.ADMIN)
    old = datetime.now(UTC) - timedelta(hours=1)
    token = _forge(user, iat=old, nbf=old, exp=old + timedelta(minutes=15))
    assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 401


def test_token_signed_with_another_key_is_rejected(client, make_user):
    user = make_user(Role.ADMIN)
    token = _forge(user, secret="attacker-secret-attacker-secret-attacker-secret")
    assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 401


def test_unsigned_none_algorithm_token_is_rejected(client, make_user):
    user = make_user(Role.ADMIN)
    token = _forge(user, secret="", algorithm="none")
    assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 401


def test_token_with_elevated_role_claim_is_rejected(client, make_user):
    """Even a correctly signed token is refused if its role doesn't match the database."""
    user = make_user(Role.EMPLOYEE)
    token = _forge(user, role="ADMIN")
    assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 401


def test_token_stops_working_when_user_is_deactivated(client, make_user, test_session_factory):
    user = make_user()
    token = login(client, user).json()["access_token"]
    with test_session_factory.begin() as db:
        db.get(User, user.id).is_active = False
    assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 401


# --- Refresh tokens ---------------------------------------------------------------------------


def _refresh(client, token):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": token})


def test_refresh_rotates_the_token(client, make_user):
    user = make_user()
    first = login(client, user).json()["refresh_token"]
    r = _refresh(client, first)
    assert r.status_code == 200
    second = r.json()["refresh_token"]
    assert second and second != first
    assert _refresh(client, second).status_code == 200


def test_reusing_an_old_refresh_token_revokes_the_whole_session(
    client, make_user, test_session_factory
):
    settings = get_settings()
    user = make_user()
    first = login(client, user).json()["refresh_token"]
    second = _refresh(client, first).json()["refresh_token"]

    original_grace = settings.refresh_reuse_grace_seconds
    settings.refresh_reuse_grace_seconds = -1  # treat any reuse as theft for this test
    try:
        assert _refresh(client, first).status_code == 401  # attacker replays the stolen token
    finally:
        settings.refresh_reuse_grace_seconds = original_grace

    assert _refresh(client, second).status_code == 401  # the legitimate chain is now dead too
    with test_session_factory() as db:
        assert db.scalar(
            select(func.count()).select_from(SecurityEvent).where(
                SecurityEvent.user_id == user.id, SecurityEvent.event_type == "REFRESH_TOKEN_REUSE"
            )
        ) == 1


def test_quick_double_refresh_is_not_treated_as_theft(client, make_user):
    user = make_user()
    first = login(client, user).json()["refresh_token"]
    second = _refresh(client, first).json()["refresh_token"]
    assert _refresh(client, first).status_code == 401  # within the grace period
    assert _refresh(client, second).status_code == 200  # session still alive


def test_expired_refresh_token_is_rejected(client, make_user, test_session_factory):
    user = make_user()
    token = login(client, user).json()["refresh_token"]
    with test_session_factory.begin() as db:
        for row in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)):
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert _refresh(client, token).status_code == 401


def test_unknown_refresh_token_is_rejected(client):
    assert _refresh(client, "made-up-token").status_code == 401


def test_logout_ends_the_session(client, make_user):
    user = make_user()
    token = login(client, user).json()["refresh_token"]
    r = client.post("/api/v1/auth/logout", json={"refresh_token": token})
    assert r.status_code == 204
    assert _refresh(client, token).status_code == 401


# --- Web dashboard (cookie) -------------------------------------------------------------------


def test_web_login_uses_httponly_cookie(client, make_user):
    user = make_user(Role.HR)
    r = login(client, user, client_type="WEB")
    assert r.status_code == 200
    assert r.json()["refresh_token"] is None  # never visible to JavaScript
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api/v1/auth" in cookie

    refreshed = client.post("/api/v1/auth/refresh")  # cookie sent automatically
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] is None

    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401


# --- Password change --------------------------------------------------------------------------


def _change(client, token, current, new):
    return client.post(
        "/api/v1/auth/change-password",
        headers=auth_header(token),
        json={"current_password": current, "new_password": new},
    )


def test_change_password_logs_out_other_sessions(client, make_user):
    user = make_user()
    phone_a = login(client, user).json()
    phone_b = login(client, user).json()

    r = _change(client, phone_a["access_token"], PASSWORD, "A-much-better-Passw0rd")
    assert r.status_code == 200
    new_tokens = r.json()

    # Old tokens everywhere stop working; the fresh ones returned keep this device logged in.
    assert client.get("/api/v1/auth/me", headers=auth_header(phone_b["access_token"])).status_code == 401
    assert _refresh(client, phone_b["refresh_token"]).status_code == 401
    assert client.get("/api/v1/auth/me", headers=auth_header(new_tokens["access_token"])).status_code == 200

    old = client.post("/api/v1/auth/login", json={"identifier": user.email, "password": PASSWORD})
    assert old.status_code == 401
    new = client.post(
        "/api/v1/auth/login", json={"identifier": user.email, "password": "A-much-better-Passw0rd"}
    )
    assert new.status_code == 200


def test_change_password_requires_current_password(client, make_user):
    user = make_user()
    token = login(client, user).json()["access_token"]
    r = _change(client, token, "wrong-current", "A-much-better-Passw0rd")
    assert r.status_code == 400


def test_weak_new_passwords_are_refused(client, make_user):
    user = make_user()
    token = login(client, user).json()["access_token"]
    for weak in ["short", "password123", "aaaaaaaaaaaaa", user.employee_code + "xyz123"]:
        r = _change(client, token, PASSWORD, weak)
        assert r.status_code == 422, weak
        assert r.json()["error"]["code"] in ("WEAK_PASSWORD", "VALIDATION_ERROR")


# --- Roles ------------------------------------------------------------------------------------


def _app_with_protected_routes():
    app = create_app()

    @app.get("/test/hr-only")
    def hr_only(user=Depends(require_roles(Role.HR))):
        return {"ok": True}

    @app.get("/test/managers")
    def managers(user=Depends(require_roles(Role.MANAGER, Role.HR))):
        return {"ok": True}

    @app.get("/test/any-user")
    def any_user(user=Depends(get_current_user)):
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_role_permissions(make_user, migrated_test_db):
    client = _app_with_protected_routes()
    tokens = {
        role: login(client, make_user(role)).json()["access_token"] for role in Role
    }
    expected = {
        "/test/hr-only": {Role.HR, Role.ADMIN},
        "/test/managers": {Role.MANAGER, Role.HR, Role.ADMIN},
        "/test/any-user": set(Role),
    }
    for path, allowed in expected.items():
        for role, token in tokens.items():
            status = client.get(path, headers=auth_header(token)).status_code
            assert status == (200 if role in allowed else 403), f"{role} on {path}"


def test_unauthorized_manager_and_hr_access_is_refused(make_user, migrated_test_db):
    client = _app_with_protected_routes()
    employee = login(client, make_user(Role.EMPLOYEE)).json()["access_token"]
    manager = login(client, make_user(Role.MANAGER)).json()["access_token"]
    assert client.get("/test/managers", headers=auth_header(employee)).status_code == 403
    assert client.get("/test/hr-only", headers=auth_header(manager)).status_code == 403


def test_forced_password_change_blocks_everything_else(make_user, migrated_test_db):
    client = _app_with_protected_routes()
    user = make_user(must_change_password=True)
    token = login(client, user).json()["access_token"]

    blocked = client.get("/test/any-user", headers=auth_header(token))
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 200

    new_token = _change(client, token, PASSWORD, "Brand-New-Secure-77")
    assert new_token.status_code == 200
    fresh = new_token.json()["access_token"]
    assert client.get("/test/any-user", headers=auth_header(fresh)).status_code == 200
