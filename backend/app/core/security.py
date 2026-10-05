"""Passwords (Argon2id), access tokens (JWT) and refresh tokens (random, stored hashed)."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_hasher = PasswordHash.recommended()  # Argon2id with current recommended parameters

# Used when the login name doesn't exist, so the response takes as long as a real check
# (otherwise response timing would reveal which accounts exist).
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

JWT_ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str | None) -> bool:
    if hashed is None:
        _hasher.verify(plain, _DUMMY_HASH)
        return False
    try:
        return _hasher.verify(plain, hashed)
    except Exception:  # malformed hash in the database
        return False


# --- Access tokens -------------------------------------------------------------------------


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    token_version: int


class InvalidTokenError(Exception):
    pass


def create_access_token(
    *, user_id: uuid.UUID, organization_id: uuid.UUID, role: str, token_version: int
) -> tuple[str, int]:
    """Returns (token, lifetime in seconds)."""
    settings = get_settings()
    now = datetime.now(UTC)
    lifetime = timedelta(minutes=settings.access_token_minutes)
    payload = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": str(user_id),
        "org": str(organization_id),
        "role": role,
        "ver": token_version,
        "typ": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "nbf": now,
        "exp": now + lifetime,
    }
    token = jwt.encode(payload, _signing_key(), algorithm=JWT_ALGORITHM)
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str) -> AccessTokenClaims:
    settings = get_settings()
    keys = [_signing_key()]
    if settings.jwt_previous_secret and settings.jwt_previous_secret.get_secret_value():
        keys.append(settings.jwt_previous_secret.get_secret_value())

    last_error: Exception | None = None
    for key in keys:
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=[JWT_ALGORITHM],  # never accept "none" or other algorithms
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
                options={"require": ["exp", "iat", "sub", "aud", "iss", "typ", "ver"]},
                leeway=10,
            )
            if payload.get("typ") != "access":
                raise InvalidTokenError("wrong token type")
            return AccessTokenClaims(
                user_id=uuid.UUID(payload["sub"]),
                organization_id=uuid.UUID(payload["org"]),
                role=payload["role"],
                token_version=int(payload["ver"]),
            )
        except jwt.InvalidSignatureError as exc:
            last_error = exc
            continue  # try the previous key
        except (jwt.PyJWTError, KeyError, ValueError) as exc:
            raise InvalidTokenError(str(exc)) from exc
    raise InvalidTokenError(str(last_error))


def _signing_key() -> str:
    key = get_settings().jwt_secret.get_secret_value()
    if len(key) < 32:
        raise RuntimeError("JWT_SECRET is missing or shorter than 32 characters.")
    return key


# --- Refresh tokens ------------------------------------------------------------------------


def new_refresh_token() -> tuple[str, str]:
    """Returns (raw token for the client, SHA-256 hash for the database)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
