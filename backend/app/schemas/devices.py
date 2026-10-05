import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import DeviceStatus
from app.services.device_keys import InvalidPublicKey, load_public_key


class DeviceRegister(BaseModel):
    device_fingerprint: str = Field(
        pattern=r"^[0-9a-f]{64}$", description="SHA-256 (hex) of the phone's ANDROID_ID"
    )
    install_id: str = Field(min_length=8, max_length=64)
    platform: str = Field("android", max_length=16)
    device_model: str | None = Field(None, max_length=100)
    os_version: str | None = Field(None, max_length=50)
    app_version: str | None = Field(None, max_length=50)
    public_key: str = Field(
        max_length=500,
        description="Base64 DER public key of the EC P-256 key pair created in the Android Keystore",
    )
    key_algorithm: Literal["EC_P256"] = "EC_P256"

    @field_validator("public_key")
    @classmethod
    def _valid_key(cls, value: str) -> str:
        try:
            load_public_key(value)
        except InvalidPublicKey as exc:
            raise ValueError(str(exc)) from None
        return value


class DeviceOut(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    employee_code: str
    status: DeviceStatus
    platform: str
    device_model: str | None
    os_version: str | None
    app_version: str | None
    requested_at: datetime
    approved_at: datetime | None
    decision_note: str | None
    last_seen_at: datetime | None


class DeviceDecision(BaseModel):
    note: str | None = Field(None, max_length=500)
