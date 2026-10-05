"""Login, token refresh/rotation, logout and password change."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.models import Employee, RefreshToken, SecurityEvent, User
from app.models.enums import ClientType, EmploymentStatus, Severity
from app.services.audit import RequestInfo, clean_ip, write_audit, write_security_event

INVALID_LOGIN = "Invalid login details."
INVALID_SESSION = "Your session has expired. Please log in again."


@dataclass
class IssuedTokens:
    user: User
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


def find_user_by_identifier(db: Session, identifier: str) -> User | None:
    """Employees may log in with their email or their employee ID (e.g. EMP-0101)."""
    identifier = identifier.strip()
    if "@" in identifier:
        return db.scalar(select(User).where(func.lower(User.email) == identifier.lower()))
    return db.scalar(
        select(User)
        .join(Employee, Employee.user_id == User.id)
        .where(func.upper(Employee.employee_code) == identifier.upper())
    )


def _ip_is_throttled(db: Session, ip: str | None) -> bool:
    if not ip:
        return False
    settings = get_settings()
    since = _now() - timedelta(minutes=settings.ip_failed_login_window_minutes)
    failures = db.scalar(
        select(func.count())
        .select_from(SecurityEvent)
        .where(
            SecurityEvent.event_type == "LOGIN_FAILED",
            SecurityEvent.ip_address == ip,
            SecurityEvent.created_at >= since,
        )
    )
    return failures >= settings.ip_failed_login_limit


def _issue_tokens(
    db: Session,
    user: User,
    client_type: ClientType,
    info: RequestInfo,
    family_id: uuid.UUID | None = None,
) -> tuple[IssuedTokens, RefreshToken]:
    settings = get_settings()
    access, expires_in = create_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role.value,
        token_version=user.token_version,
    )
    raw, token_hash = new_refresh_token()
    lifetime = (
        timedelta(days=settings.refresh_token_days_mobile)
        if client_type == ClientType.MOBILE
        else timedelta(hours=settings.refresh_token_hours_web)
    )
    row = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        family_id=family_id or uuid.uuid4(),
        client_type=client_type,
        expires_at=_now() + lifetime,
        ip_address=clean_ip(info.ip_address),
        user_agent=(info.user_agent or "")[:500] or None,
    )
    db.add(row)
    db.flush()
    return IssuedTokens(user, access, expires_in, raw, row.expires_at), row


def _account_usable(user: User, db: Session) -> bool:
    if not user.is_active:
        return False
    employee = db.scalar(select(Employee).where(Employee.user_id == user.id))
    return employee is None or employee.employment_status == EmploymentStatus.ACTIVE


def login(
    db: Session, identifier: str, password: str, client_type: ClientType, info: RequestInfo
) -> IssuedTokens:
    settings = get_settings()

    if _ip_is_throttled(db, clean_ip(info.ip_address)):
        raise AppError(429, "TOO_MANY_REQUESTS", "Too many failed attempts. Please wait and try again.")

    user = find_user_by_identifier(db, identifier)
    now = _now()

    if user is not None and user.locked_until and user.locked_until > now:
        # Don't even check the password while locked.
        verify_password(password, None)
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise AppError(
            423, "ACCOUNT_LOCKED", f"Too many failed attempts. Try again in {minutes} minute(s)."
        )

    password_ok = verify_password(password, user.password_hash if user else None)

    if not password_ok or user is None or not _account_usable(user, db):
        details = {"identifier_type": "email" if "@" in identifier else "employee_id"}
        if user is not None and password_ok:
            details["reason"] = "inactive_account"
        elif user is not None:
            user.failed_login_count += 1
            details["failed_count"] = user.failed_login_count
            if user.failed_login_count >= settings.max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_login_count = 0
                details["locked"] = True
        else:
            details["reason"] = "unknown_identifier"
        write_security_event(
            db,
            event_type="LOGIN_FAILED",
            severity=Severity.MEDIUM if details.get("locked") else Severity.LOW,
            organization_id=user.organization_id if user else None,
            user_id=user.id if user else None,
            ip_address=info.ip_address,
            details=details,
        )
        db.commit()  # keep the failure count even though the request fails
        raise AppError(401, "INVALID_CREDENTIALS", INVALID_LOGIN)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    tokens, _ = _issue_tokens(db, user, client_type, info)
    db.commit()
    return tokens


def refresh(db: Session, raw_token: str | None, info: RequestInfo) -> IssuedTokens:
    """Exchanges a refresh token for new tokens. The old refresh token stops working.
    Presenting an already-used token means it was probably stolen: the whole chain is revoked."""
    if not raw_token:
        raise AppError(401, "INVALID_SESSION", INVALID_SESSION)
    settings = get_settings()
    now = _now()

    # Lock the row so two simultaneous refreshes with the same token can't both succeed.
    token = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
        .with_for_update()
    )
    if token is None:
        raise AppError(401, "INVALID_SESSION", INVALID_SESSION)

    user = db.get(User, token.user_id)

    if token.revoked_at is not None:
        # Only a token that was already exchanged ("rotated") indicates theft. Tokens ended by
        # logout or a password change are simply no longer valid.
        reused_after_rotation = (
            token.revoke_reason == "rotated"
            and (now - token.revoked_at).total_seconds() > settings.refresh_reuse_grace_seconds
        )
        if reused_after_rotation:
            revoke_family(db, token.family_id, "reuse_detected")
            write_security_event(
                db,
                event_type="REFRESH_TOKEN_REUSE",
                severity=Severity.HIGH,
                organization_id=user.organization_id if user else None,
                user_id=token.user_id,
                ip_address=info.ip_address,
                details={"family_id": str(token.family_id), "revoke_reason": token.revoke_reason},
            )
            db.commit()
        raise AppError(401, "INVALID_SESSION", INVALID_SESSION)

    if token.expires_at <= now or user is None or not _account_usable(user, db):
        raise AppError(401, "INVALID_SESSION", INVALID_SESSION)

    tokens, new_row = _issue_tokens(db, user, token.client_type, info, family_id=token.family_id)
    token.revoked_at = now
    token.revoke_reason = "rotated"
    token.replaced_by_id = new_row.id
    db.commit()
    return tokens


def revoke_family(db: Session, family_id: uuid.UUID, reason: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now(), revoke_reason=reason)
    )


def revoke_all_for_user(db: Session, user_id: uuid.UUID, reason: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now(), revoke_reason=reason)
    )


def logout(db: Session, raw_token: str | None) -> None:
    """Ends this login session (this device/browser). Always succeeds."""
    if not raw_token:
        return
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    )
    if token is not None:
        revoke_family(db, token.family_id, "logout")
        db.commit()


def validate_new_password(user: User, new_password: str, db: Session) -> None:
    settings = get_settings()
    problems = []
    if len(new_password) < settings.password_min_length:
        problems.append(f"must be at least {settings.password_min_length} characters")
    if len(new_password) > 128:
        problems.append("must be at most 128 characters")
    lowered = new_password.lower()
    names = [user.email.split("@")[0].lower()]
    employee = db.scalar(select(Employee).where(Employee.user_id == user.id))
    if employee:
        names.append(employee.employee_code.lower())
    if any(n and n in lowered for n in names):
        problems.append("must not contain your email name or employee ID")
    if lowered in _COMMON_PASSWORDS or len(set(new_password)) < 4:
        problems.append("is too easy to guess")
    if problems:
        raise AppError(422, "WEAK_PASSWORD", "New password " + "; ".join(problems) + ".")


def change_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    client_type: ClientType,
    info: RequestInfo,
) -> IssuedTokens:
    """Changes the password, logs out every other session, and returns fresh tokens so the
    person stays logged in on the device they used."""
    if not verify_password(current_password, user.password_hash):
        raise AppError(400, "WRONG_PASSWORD", "Your current password is not correct.")
    if current_password == new_password:
        raise AppError(422, "WEAK_PASSWORD", "New password must be different from the current one.")
    validate_new_password(user, new_password, db)

    user.password_hash = hash_password(new_password)
    user.password_changed_at = _now()
    user.must_change_password = False
    user.token_version += 1  # logs out every other device/browser immediately
    revoke_all_for_user(db, user.id, "password_changed")
    write_audit(
        db,
        action="USER_PASSWORD_CHANGED",
        organization_id=user.organization_id,
        actor_user_id=user.id,
        actor_role=user.role.value,
        object_type="user",
        object_id=user.id,
        ip_address=info.ip_address,
        user_agent=info.user_agent,
        request_id=info.request_id,
    )
    tokens, _ = _issue_tokens(db, user, client_type, info)
    db.commit()
    return tokens


_COMMON_PASSWORDS = {
    "password", "password1", "password123", "1234567890", "12345678910", "qwertyuiop",
    "qwerty1234", "iloveyou12", "welcome123", "admin12345", "letmein123", "abcdefghij",
    "abc1234567", "password12", "passw0rd12", "changeme123", "company123",
}
