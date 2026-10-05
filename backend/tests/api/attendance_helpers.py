"""Shared helpers for attendance tests: a controllable clock, simulated phones (each with its
own EC P-256 key, like the Android Keystore), challenges and signed attempts."""

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core import clock
from app.models.enums import AttendanceAction
from app.schemas.attendance import AttendanceSubmission
from app.services.attendance.canonical import canonical_payload

INSIDE_LAGOS = (6.428500, 3.421900)  # ~44 m from the Lagos office
MONDAY = (2026, 10, 5)

# device id -> private key (stays "on the phone": only the test helpers use it)
PHONE_KEYS: dict[str, ec.EllipticCurvePrivateKey] = {}


@pytest.fixture
def set_time(monkeypatch):
    """set_time(9, 7) -> the server believes it is 09:07 Lagos time on Monday 5 Oct 2026."""
    state = {}

    def _set(hh: int, mm: int = 0, ss: int = 0, day=MONDAY):
        state["now"] = datetime(*day, hh, mm, ss, tzinfo=ZoneInfo("Africa/Lagos")).astimezone(UTC)

    def _advance(**delta):
        state["now"] += timedelta(**delta)

    _set(9, 0)
    monkeypatch.setattr(clock, "now", lambda: state["now"])
    _set.advance = _advance
    return _set


def fingerprint() -> str:
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()


def new_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def public_key_b64(key: ec.EllipticCurvePrivateKey) -> str:
    der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return base64.b64encode(der).decode()


def sign(key: ec.EllipticCurvePrivateKey, payload: str) -> str:
    return base64.b64encode(key.sign(payload.encode(), ec.ECDSA(hashes.SHA256()))).decode()


def register(client, world, who, fp=None, key=None, expect=200) -> dict:
    key = key or new_key()
    r = client.post("/api/v1/devices/register", headers=world.h(who), json={
        "device_fingerprint": fp or fingerprint(), "install_id": uuid.uuid4().hex,
        "device_model": "Pixel 8", "os_version": "Android 15", "app_version": "1.0.0",
        "public_key": public_key_b64(key),
    })
    assert r.status_code == expect, r.text
    if expect == 200:
        PHONE_KEYS[r.json()["id"]] = key
    return r.json()


def approved_device(client, world, who) -> str:
    device = register(client, world, who)
    r = client.post(f"/api/v1/devices/{device['id']}/approve", headers=world.h("hr"))
    assert r.status_code == 200, r.text
    return device["id"]


@pytest.fixture
def ann_phone(client, world):
    return approved_device(client, world, "ann")


def get_challenge(client, world, who, device_id, action="CHECK_IN"):
    return client.post("/api/v1/attendance/challenge", headers=world.h(who),
                       json={"action": action, "device_id": device_id})


def build_body(device_id, action, challenge, at=INSIDE_LAGOS, signing_key=None, **extra) -> dict:
    """The JSON a real phone would send, signed with the phone's key (unless `signature` is given)."""
    body = {
        "client_request_id": str(uuid.uuid4()),
        "challenge_id": challenge["challenge_id"], "nonce": challenge["nonce"],
        "device_id": device_id, "latitude": at[0], "longitude": at[1],
        "accuracy_m": 12.5, "fix_age_ms": 2000, "device_time": clock.now().isoformat(),
        **extra,
    }
    if "signature" not in body:
        parsed = AttendanceSubmission(**{**body, "signature": "unsigned"})
        payload = canonical_payload(AttendanceAction(action), parsed)
        body["signature"] = sign(signing_key or PHONE_KEYS[device_id], payload)
    return body


def attempt(client, world, who, device_id, action="CHECK_IN", at=INSIDE_LAGOS, challenge=None, **extra):
    if challenge is None:
        r = get_challenge(client, world, who, device_id, action)
        assert r.status_code == 200, r.text
        challenge = r.json()
    body = build_body(device_id, action, challenge, at, **extra)
    path = "check-in" if action == "CHECK_IN" else "check-out"
    return client.post(f"/api/v1/attendance/{path}", headers=world.h(who), json=body)
