"""Login, token refresh, logout, current user, password change."""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_user_allow_pending_password_change, request_info
from app.core.config import get_settings
from app.db.session import get_db
from app.models import Employee, User
from app.models.enums import ClientType
from app.schemas.auth import (
    ChangePasswordRequest,
    EmployeeSummary,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserSummary,
)
from app.services import auth_service
from app.services.audit import RequestInfo
from app.services.auth_service import IssuedTokens

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_PATH = "/api/v1/auth"


def user_summary(db: Session, user: User) -> UserSummary:
    employee = db.scalar(select(Employee).where(Employee.user_id == user.id))
    return UserSummary(
        id=user.id,
        email=user.email,
        role=user.role,
        must_change_password=user.must_change_password,
        employee=EmployeeSummary.model_validate(employee) if employee else None,
    )


def _token_response(
    db: Session, tokens: IssuedTokens, client_type: ClientType, response: Response
) -> TokenResponse:
    refresh_in_body = tokens.refresh_token
    if client_type == ClientType.WEB:
        # Browser: keep the refresh token where JavaScript can't read it.
        settings = get_settings()
        response.set_cookie(
            settings.refresh_cookie_name,
            tokens.refresh_token,
            max_age=settings.refresh_token_hours_web * 3600,
            path=_COOKIE_PATH,
            secure=settings.cookie_secure,
            httponly=True,
            samesite="strict",
        )
        refresh_in_body = None
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        refresh_token=refresh_in_body,
        refresh_expires_at=tokens.refresh_expires_at,
        user=user_summary(db, tokens.user),
    )


@router.post("/login", response_model=TokenResponse, summary="Log in with email or employee ID")
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    info: RequestInfo = Depends(request_info),
):
    tokens = auth_service.login(db, body.identifier, body.password, body.client_type, info)
    return _token_response(db, tokens, body.client_type, response)


@router.post("/refresh", response_model=TokenResponse, summary="Get a new access token")
def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: Session = Depends(get_db),
    info: RequestInfo = Depends(request_info),
):
    from_body = body.refresh_token if body else None
    raw = from_body or request.cookies.get(get_settings().refresh_cookie_name)
    tokens = auth_service.refresh(db, raw, info)
    client_type = ClientType.MOBILE if from_body else ClientType.WEB
    return _token_response(db, tokens, client_type, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Log out this device")
def logout(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    raw = (body.refresh_token if body else None) or request.cookies.get(
        settings.refresh_cookie_name
    )
    auth_service.logout(db, raw)
    response.delete_cookie(
        settings.refresh_cookie_name, path=_COOKIE_PATH, secure=settings.cookie_secure,
        httponly=True, samesite="strict",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserSummary, summary="Who am I?")
def me(
    user: User = Depends(get_user_allow_pending_password_change), db: Session = Depends(get_db)
):
    return user_summary(db, user)


@router.post(
    "/change-password",
    response_model=TokenResponse,
    summary="Change my password (logs out all other devices)",
)
def change_password(
    body: ChangePasswordRequest,
    response: Response,
    user: User = Depends(get_user_allow_pending_password_change),
    db: Session = Depends(get_db),
    info: RequestInfo = Depends(request_info),
):
    tokens = auth_service.change_password(
        db, user, body.current_password, body.new_password, body.client_type, info
    )
    return _token_response(db, tokens, body.client_type, response)
