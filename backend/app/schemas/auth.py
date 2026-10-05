import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import ClientType, Role

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=320)]
Password = Annotated[str, Field(min_length=1, max_length=128)]


class LoginRequest(BaseModel):
    identifier: Identifier = Field(description="Email address or employee ID (e.g. EMP-0101)")
    password: Password
    client_type: ClientType = Field(
        ClientType.MOBILE,
        description="MOBILE: refresh token returned in the body. "
        "WEB: refresh token set as an HttpOnly cookie.",
    )


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(
        None, max_length=200, description="Mobile only. The web dashboard sends the cookie."
    )


class ChangePasswordRequest(BaseModel):
    current_password: Password
    new_password: Password
    client_type: ClientType = ClientType.MOBILE


class EmployeeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    full_name: str


class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    must_change_password: bool
    employee: EmployeeSummary | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")
    refresh_token: str | None = Field(None, description="Only for MOBILE clients")
    refresh_expires_at: datetime
    user: UserSummary
