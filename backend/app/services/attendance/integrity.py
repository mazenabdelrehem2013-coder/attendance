"""Google Play Integrity (Standard API), verified on OUR server.

The phone asks Google for an integrity token bound to the request hash (see canonical.py) and
sends it with the check-in. We send the token to Google's decodeIntegrityToken endpoint and
check the verdict ourselves. Nothing the phone says about its own integrity is trusted.

What it can detect: modified/re-signed copies of our app, apps not installed from Google Play,
emulators and many rooted or compromised phones. What it can't: it doesn't look at the
location itself, and well-hidden rooting may pass on some phones - so it's one signal of many.
"""

import logging
from datetime import datetime
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.models.enums import PolicyAction, SignalResult
from app.services.attendance.verification import SignalOutcome

log = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/playintegrity"
DECODE_URL = "https://playintegrity.googleapis.com/v1/{package}:decodeIntegrityToken"


class IntegrityUnavailable(Exception):
    """Google couldn't be reached or refused the request (not the phone's fault)."""


class IntegrityVerifier(Protocol):
    def decode(self, token: str) -> dict: ...


class GooglePlayIntegrityVerifier:
    """Uses the Cloud Run service account (no key files). Set up in Phase 18-19."""

    def __init__(self, package_name: str):
        self.package_name = package_name
        self._credentials = None

    def decode(self, token: str) -> dict:
        import google.auth
        import requests
        from google.auth.transport.requests import Request

        try:
            if self._credentials is None:
                self._credentials, _ = google.auth.default(scopes=[SCOPE])
            if not self._credentials.valid:
                self._credentials.refresh(Request())
            response = requests.post(
                DECODE_URL.format(package=self.package_name),
                json={"integrityToken": token},
                headers={"Authorization": f"Bearer {self._credentials.token}"},
                timeout=5,
            )
        except Exception as exc:  # network, credentials
            raise IntegrityUnavailable(str(exc)) from exc
        if response.status_code == 400:
            return {}  # Google says the token itself is invalid -> evaluated as a failure
        if response.status_code != 200:
            raise IntegrityUnavailable(f"HTTP {response.status_code}")
        return response.json().get("tokenPayloadExternal", {})


@lru_cache
def get_verifier() -> IntegrityVerifier:
    return GooglePlayIntegrityVerifier(get_settings().play_integrity_package_name)


def evaluate_verdict(
    payload: dict, expected_hash: str, package_name: str, now: datetime, max_age_s: int,
    on_fail: PolicyAction,
) -> SignalOutcome:
    """Turn Google's decoded verdict into PASS / FAIL with the reasons recorded."""
    request = payload.get("requestDetails", {})
    app = payload.get("appIntegrity", {})
    device = payload.get("deviceIntegrity", {})
    account = payload.get("accountDetails", {})

    problems = []
    if not payload:
        problems.append("TOKEN_INVALID")
    if request.get("requestHash") != expected_hash:
        problems.append("REQUEST_MISMATCH")  # token made for a different request
    if request.get("requestPackageName") != package_name:
        problems.append("WRONG_PACKAGE")
    try:
        age_s = (now.timestamp() * 1000 - int(request.get("timestampMillis", 0))) / 1000
    except (TypeError, ValueError):
        age_s = float("inf")
    if not -30 <= age_s <= max_age_s:
        problems.append("TOKEN_TOO_OLD")
    if app.get("appRecognitionVerdict") != "PLAY_RECOGNIZED":
        problems.append("APP_NOT_RECOGNIZED")  # modified app or not installed from Play
    device_verdicts = device.get("deviceRecognitionVerdict") or []
    if "MEETS_DEVICE_INTEGRITY" not in device_verdicts:
        problems.append("DEVICE_INTEGRITY")  # rooted, emulator, compromised

    details = {
        "app_verdict": app.get("appRecognitionVerdict"),
        "device_verdict": device_verdicts,
        "licensing": account.get("appLicensingVerdict"),
        "problems": problems,
    }
    if problems:
        return SignalOutcome("play_integrity", SignalResult.FAIL, on_fail, "INTEGRITY_FAIL", details)
    return SignalOutcome("play_integrity", SignalResult.PASS, on_fail, None, details)


def integrity_signal(
    token: str | None, expected_hash: str, now: datetime, on_fail: PolicyAction
) -> SignalOutcome:
    settings = get_settings()
    if settings.play_integrity_mode != "google":
        return SignalOutcome("play_integrity", SignalResult.NOT_APPLICABLE)
    if not token:
        return SignalOutcome("play_integrity", SignalResult.FAIL, on_fail, "INTEGRITY_MISSING")
    try:
        payload = get_verifier().decode(token)
    except IntegrityUnavailable as exc:
        # Google is down: don't punish the employee, but record the doubt.
        log.warning("Play Integrity unavailable: %s", exc)
        return SignalOutcome("play_integrity", SignalResult.WARN, on_fail, "INTEGRITY_UNAVAILABLE")
    return evaluate_verdict(
        payload, expected_hash, settings.play_integrity_package_name, now,
        settings.play_integrity_max_age_s, on_fail,
    )
