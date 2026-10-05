"""Rotating office QR codes (decision 11.7: new code every 30 seconds).

- Each office screen ("QR display") is registered by HR and gets a secret display key, entered
  once on the screen. The screen uses it to fetch the current code from the server every few
  seconds - the signing secret itself never leaves the server, so nobody can create codes.
- Code = Q1.<display id>.<time window>.<HMAC signature>. The time window changes every
  `rotation_seconds`; the server accepts the current and the previous window only (~60 s max).
- A photo of the code shared on WhatsApp stops working within a minute, and the person still
  has to pass the GPS checks at the same office.
"""

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Location, QrSession
from app.services.audit import Actor, audit
from app.services.org_service import get_in_org

TOKEN_PREFIX = "Q1"


def _master_key() -> bytes:
    key = get_settings().qr_master_key.get_secret_value()
    if len(key) < 32:
        raise RuntimeError("QR_MASTER_KEY is missing or shorter than 32 characters.")
    return key.encode()


def _display_secret(display: QrSession) -> bytes:
    """Per-display signing key, derived from the master key. Changing key_version invalidates
    every code made with the old one."""
    return hmac.new(_master_key(), f"qr|{display.id}|{display.key_version}".encode(), hashlib.sha256).digest()


def _window(now: datetime, rotation_seconds: int) -> int:
    return int(now.timestamp() // rotation_seconds)


def _mac(display: QrSession, window: int) -> str:
    digest = hmac.new(_display_secret(display), f"{display.location_id}|{window}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:16]).decode().rstrip("=")


def make_token(display: QrSession, now: datetime) -> tuple[str, datetime]:
    window = _window(now, display.rotation_seconds)
    token = f"{TOKEN_PREFIX}.{display.id.hex}.{window}.{_mac(display, window)}"
    expires = datetime.fromtimestamp((window + 1) * display.rotation_seconds, UTC)
    return token, expires


@dataclass(frozen=True)
class QrCheck:
    ok: bool
    reason: str | None
    display: QrSession | None


def verify_token(db: Session, token: str, now: datetime) -> QrCheck:
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != TOKEN_PREFIX:
        return QrCheck(False, "QR_MALFORMED", None)
    try:
        display_id, window = uuid.UUID(hex=parts[1]), int(parts[2])
    except ValueError:
        return QrCheck(False, "QR_MALFORMED", None)
    display = db.get(QrSession, display_id)
    if display is None or not display.is_active:
        return QrCheck(False, "QR_UNKNOWN_DISPLAY", display)
    current = _window(now, display.rotation_seconds)
    if window not in (current, current - 1):
        return QrCheck(False, "QR_EXPIRED", display)
    if not hmac.compare_digest(parts[3], _mac(display, window)):
        return QrCheck(False, "QR_FORGED", display)
    return QrCheck(True, None, display)


# --- Display management (HR) ----------------------------------------------------------------


def _new_display_key() -> tuple[str, str]:
    raw = "qrd_" + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def list_displays(db: Session, org_id: uuid.UUID) -> list[tuple[QrSession, Location]]:
    return list(
        db.execute(
            select(QrSession, Location)
            .join(Location, Location.id == QrSession.location_id)
            .where(Location.organization_id == org_id)
            .order_by(Location.name, QrSession.display_label)
        ).all()
    )


def create_display(
    db: Session, actor: Actor, location_id: uuid.UUID, label: str, rotation_seconds: int
) -> tuple[QrSession, Location, str]:
    location = get_in_org(db, Location, location_id, actor.user.organization_id, "Location")
    raw, key_hash = _new_display_key()
    display = QrSession(
        location_id=location.id, display_label=label, rotation_seconds=rotation_seconds,
        display_credential_hash=key_hash, created_by=actor.user.id,
    )
    db.add(display)
    db.flush()
    audit(db, actor, "QR_DISPLAY_CREATED", "qr_display", display.id,
          new_value={"location_id": str(location.id), "label": label, "rotation_seconds": rotation_seconds})
    db.commit()
    return display, location, raw


def _get_display(db: Session, actor: Actor, display_id: uuid.UUID) -> tuple[QrSession, Location]:
    row = db.execute(
        select(QrSession, Location)
        .join(Location, Location.id == QrSession.location_id)
        .where(QrSession.id == display_id, Location.organization_id == actor.user.organization_id)
    ).first()
    if row is None:
        raise AppError(404, "NOT_FOUND", "QR display not found.")
    return row[0], row[1]


def rotate_key(db: Session, actor: Actor, display_id: uuid.UUID) -> tuple[QrSession, Location, str]:
    """New display key (e.g. the screen was stolen) - old key and all old codes stop working."""
    display, location = _get_display(db, actor, display_id)
    raw, key_hash = _new_display_key()
    display.display_credential_hash = key_hash
    display.key_version += 1
    audit(db, actor, "QR_DISPLAY_KEY_ROTATED", "qr_display", display.id,
          {"key_version": display.key_version - 1}, {"key_version": display.key_version})
    db.commit()
    return display, location, raw


def set_active(db: Session, actor: Actor, display_id: uuid.UUID, active: bool) -> tuple[QrSession, Location]:
    display, location = _get_display(db, actor, display_id)
    if display.is_active != active:
        audit(db, actor, "QR_DISPLAY_ENABLED" if active else "QR_DISPLAY_DISABLED", "qr_display",
              display.id, {"is_active": display.is_active}, {"is_active": active})
        display.is_active = active
        db.commit()
    return display, location


def current_code(db: Session, display_key: str | None) -> tuple[QrSession, Location, str, datetime]:
    """Called by the office screen every few seconds."""
    if not display_key:
        raise AppError(401, "NOT_AUTHENTICATED", "Display key required.")
    key_hash = hashlib.sha256(display_key.encode()).hexdigest()
    row = db.execute(
        select(QrSession, Location)
        .join(Location, Location.id == QrSession.location_id)
        .where(QrSession.display_credential_hash == key_hash)
    ).first()
    if row is None or not row[0].is_active or not row[1].is_active:
        raise AppError(401, "NOT_AUTHENTICATED", "This display key is not valid or the display is disabled.")
    display, location = row
    now = clock.now()
    display.last_heartbeat_at = now
    db.commit()
    token, expires = make_token(display, now)
    return display, location, token, expires
