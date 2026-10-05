"""Shared FastAPI dependencies: who is calling, and are they allowed to?

Usage in a route:
    def endpoint(user: User = Depends(require_roles(Role.HR))): ...
ADMIN is always allowed (full system access).
"""

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models import User
from app.models.enums import Role
from app.services.audit import Actor, RequestInfo
from app.services.auth_service import _account_usable

_bearer = HTTPBearer(auto_error=False, description="Access token from /auth/login")

_AUTH_HEADERS = {"WWW-Authenticate": "Bearer"}


def request_info(request: Request) -> RequestInfo:
    return RequestInfo(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )


def get_user_allow_pending_password_change(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Valid login required. Used only by the few endpoints a user may call while they still
    have to change a temporary password (/auth/me, /auth/change-password)."""
    if credentials is None:
        raise AppError(401, "NOT_AUTHENTICATED", "Please log in.", headers=_AUTH_HEADERS)
    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise AppError(
            401, "INVALID_TOKEN", "Your session has expired. Please log in again.", _AUTH_HEADERS
        ) from None

    user = db.get(User, claims.user_id)
    if (
        user is None
        or user.token_version != claims.token_version  # password changed / forced logout
        or user.role.value != claims.role  # role changed since login
        or not _account_usable(user, db)  # deactivated, suspended or terminated
    ):
        raise AppError(
            401, "INVALID_TOKEN", "Your session has expired. Please log in again.", _AUTH_HEADERS
        )
    request.state.user_id = user.id
    return user


def get_current_user(user: User = Depends(get_user_allow_pending_password_change)) -> User:
    """Valid login required, and no pending forced password change."""
    if user.must_change_password:
        raise AppError(
            403, "PASSWORD_CHANGE_REQUIRED", "Please change your password before continuing."
        )
    return user


def require_roles(*roles: Role):
    allowed = set(roles) | {Role.ADMIN}

    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
        return user

    return _check


def actor_with_roles(*roles: Role):
    """Like require_roles, but returns an Actor (user + IP/user agent) for audit logging."""
    check = require_roles(*roles)

    def _actor(user: User = Depends(check), info: RequestInfo = Depends(request_info)) -> Actor:
        return Actor(user=user, info=info)

    return _actor
